"""faster-whisper ASR 客户端（docs/06 §8：small/int8/CPU；ffmpeg 转 16k wav）。

- 延迟导入 faster_whisper/torch（重依赖，轻量测试环境走 Fake）；
- CPU 工作必须进线程（anyio.to_thread 由编排器包装）——本类仅同步接口；
- ffmpeg 是本服务唯一硬依赖（WebM/opus → 16k mono wav），生产镜像已装；
- 并发护栏：模块级信号量 2（docs/06 §8 并发决策：whisper 并发 2，与讯飞 ISE 一致；
  docs/19 P1-4 / 审计 R-10——此前全仓 0 个 Semaphore，10 人并发直涌线程池）。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.audio.base import ASRClient, ASRResult

_FFMPEG = "ffmpeg"

# docs/06 §8：模型侧信号量（whisper 并发 2）；多请求排队不雪崩
_ASR_CONCURRENCY = 2
_ASR_SEM = asyncio.Semaphore(_ASR_CONCURRENCY)


def _ffmpeg_bin() -> str:
    """ffmpeg 路径：① env FFMPEG_BIN → ② PATH 中 ffmpeg → ③ imageio-ffmpeg 自带二进制
    （pip/uv 附带、免管理员，README 登记）→ ④ 兜底 "ffmpeg"（让 subprocess 报可读错误）。"""
    import os
    import shutil

    if os.environ.get("FFMPEG_BIN"):
        return os.environ["FFMPEG_BIN"]
    if shutil.which("ffmpeg"):
        return _FFMPEG
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return _FFMPEG


class FasterWhisperClient(ASRClient):
    def __init__(self, model: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._model = None  # 延迟加载（首次调用 ≈10~30s；lifespan 预热见 main.py）

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self._model_name, device=self._device, compute_type=self._compute_type
            )
        return self._model

    def transcribe_sync(self, wav_path: str, language: str = "en") -> ASRResult:
        model = self._get_model()
        # word_timestamps=True：词级时间戳（流利度时间戳特征数据源，docs/06 §9.3）；
        # 注意 transcribe 返回**生成器**，先 list() 物化一次——重复迭代同一生成器
        # 第二次永远为空（旧代码 segments 恒空、2026-09-04 联调发现 words 恒空的根因）
        segments, info = model.transcribe(
            wav_path, language=language, beam_size=5, word_timestamps=True
        )
        segments = list(segments)
        text = "".join(s.text for s in segments).strip()
        words: list[dict] = []
        for s in segments:
            for w in s.words or []:
                words.append(
                    {
                        "word": w.word,
                        "start": float(w.start),
                        "end": float(w.end),
                        "probability": float(getattr(w, "probability", 0.0) or 0.0),
                    }
                )
        return ASRResult(
            text=text,
            language=info.language or language,
            confidence=float(getattr(info, "language_probability", 0.0) or 0.0),
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segments],
            words=words,
            duration=float(getattr(info, "duration", 0.0) or 0.0),
        )

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        import os

        # docs/06 §8 信号量护栏：限并发转写（排队不雪崩）；也在 /asr 裸端点与 /turns 热路径同时生效
        async with _ASR_SEM:
            os.makedirs("data/audio/tmp", exist_ok=True)
            with tempfile.NamedTemporaryFile(
                suffix=".in", delete=False, dir="data/audio/tmp"
            ) as tmp:
                tmp.write(audio_bytes)
                src = tmp.name
            wav = src + ".wav"
            try:
                # docs/19 P0-2：ffmpeg 同步 subprocess 阻塞事件循环（音频卡死→整个进程停摆）。
                # 改 async 子进程 + 15s 超时（超时 kill，防占资源/僵尸进程）。
                await _run_ffmpeg_async(src, wav)
                return await asyncio.to_thread(self.transcribe_sync, wav, language)
            finally:
                for p in (src, wav):
                    Path(p).unlink(missing_ok=True)


async def _run_ffmpeg_async(src: str, wav: str, timeout_s: float = 15.0) -> None:
    """ffmpeg 转码（async + 超时强制 kill；docs/19 P0-2 / P1-3：外部依赖超时分层）。"""
    try:
        proc = await asyncio.create_subprocess_exec(
            _ffmpeg_bin(),
            "-y",
            "-i",
            src,
            "-ar",
            "16000",
            "-ac",
            "1",
            "-f",
            "wav",
            wav,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"ffmpeg 未找到: {_ffmpeg_bin()}") from exc
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RuntimeError(f"ffmpeg 转码超时（{timeout_s}s）: {src}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg 转码失败（exit={proc.returncode}）: {stderr or b''}")
