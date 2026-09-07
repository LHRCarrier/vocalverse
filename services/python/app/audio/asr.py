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
import threading
from pathlib import Path

from app.audio.base import ASRClient, ASRResult
from app.audio.ffmpeg_utils import run_ffmpeg

# docs/06 §8：模型侧信号量（whisper 并发 2）；多请求排队不雪崩
_ASR_CONCURRENCY = 2
_ASR_SEM = asyncio.Semaphore(_ASR_CONCURRENCY)

#: 转写墙钟超时（vasr-01：whisper 线程挂起 → 槽位永不释放 → 全站 ASR 死锁）。
_ASR_TRANSCRIBE_TIMEOUT_S = 300.0


class FasterWhisperClient(ASRClient):
    def __init__(self, model: str = "small", device: str = "cpu", compute_type: str = "int8"):
        self._model_name = model
        self._device = device
        self._compute_type = compute_type
        self._model = None  # 延迟加载（首次调用 ≈10~30s；lifespan 预热见 main.py）
        self._load_lock = threading.Lock()  # vasr-09：并发首请求只加载一次（双重检查）

    def _get_model(self):
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    from faster_whisper import WhisperModel

                    self._model = WhisperModel(
                        self._model_name, device=self._device, compute_type=self._compute_type
                    )
        return self._model

    def warm(self) -> None:
        """显式预热（vasr-09：替代 getattr(client, '_get_model', None) 的脆弱探针）。"""
        self._get_model()

    def transcribe_sync(self, wav_path: str, language: str = "en") -> ASRResult:
        model = self._get_model()
        # word_timestamps=True：词级时间戳（流利度时间戳特征数据源，docs/06 §9.3）；
        # vad_filter=True：Silero VAD（docs/06 §8:116 承诺，审计 R-09 / 拷问 vasr-07）——
        # 静音/噪声段前置裁剪，稳定词界 + 降带 BGM 录音的 CER；空段由 no_speech_prob 判别。
        # 注意 transcribe 返回**生成器**，先 list() 物化一次——重复迭代同一生成器
        # 第二次永远为空（旧代码 segments 恒空、2026-09-04 联调发现 words 恒空的根因）
        segments, info = model.transcribe(
            wav_path,
            language=language,
            beam_size=5,
            word_timestamps=True,
            vad_filter=True,
            # 2026-09-07 真链路实测：whisper-small 被噪声/口音干扰时会幻觉重复
            # （"Uh, I heard, uh, …"）并顺着上文延续（condition_on_previous_text=True 默认）。
            # 关掉 = 每段独立解码，幻觉大幅抑制（与 VAD 配合，无声段判别也更干净）。
            condition_on_previous_text=False,
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
        no_speech_prob = float(getattr(info, "no_speech_prob", 0.0) or 0.0)
        return ASRResult(
            text=text,
            language=info.language or language,
            confidence=float(getattr(info, "language_probability", 0.0) or 0.0),
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segments],
            words=words,
            duration=float(getattr(info, "duration", 0.0) or 0.0),
            # vasr-10 判别位：静音/无话语（>0.7 或 VAD 后空文本）与「失败」区分，
            # 前端提示从「听不清重说」变成「似乎没说话，请再试」而非反复重试。
            no_speech=no_speech_prob > 0.7 or (not text),
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
                # vasr-01：转写本体墙钟超时 —— whisper 线程挂起时 signal 槽位可释放，
                # 避免「挂 2 次 = 全站 ASR 永久死亡」；超时按失败处理（可降级/重试）。
                return await asyncio.wait_for(
                    asyncio.to_thread(self.transcribe_sync, wav, language),
                    timeout=_ASR_TRANSCRIBE_TIMEOUT_S,
                )
            finally:
                for p in (src, wav):
                    Path(p).unlink(missing_ok=True)


async def _run_ffmpeg_async(src: str, wav: str, timeout_s: float = 15.0) -> None:
    """ffmpeg 转码（async + 超时强制 kill；docs/19 P0-2 / P1-3：外部依赖超时分层）。

    统一护栏见 app.audio.ffmpeg_utils.run_ffmpeg（va-01：单真源，避免与 ise 漂移）。
    """
    await run_ffmpeg(
        ["-y", "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", wav],
        timeout_s=timeout_s,
    )
