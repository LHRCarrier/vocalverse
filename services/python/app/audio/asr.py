"""faster-whisper ASR 客户端（docs/06 §8：small/int8/CPU；ffmpeg 转 16k wav）。

- 延迟导入 faster_whisper/torch（重依赖，轻量测试环境走 Fake）；
- CPU 工作必须进线程（anyio.to_thread 由编排器包装）——本类仅同步接口；
- ffmpeg 是本服务唯一硬依赖（WebM/opus → 16k mono wav），生产镜像已装。
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from app.audio.audio_quality import has_speech, load_audio_16k_mono
from app.audio.base import ASRClient, ASRResult
from app.core.response import BizError

logger = logging.getLogger("vocalverse")

_FFMPEG = "ffmpeg"


def _reject_if_silent(wav_path: str) -> None:
    """有效性前置过滤（docs/19-M2 §2）：空录音/纯静音 → 40002 硬拒绝，不送 whisper + ISE。

    读取音频失败只告警不阻断（fail-open），避免误拒正常音频导致题目卡死。
    """
    try:
        pcm = load_audio_16k_mono(wav_path)
        if not has_speech(pcm):
            raise BizError(http_status=400, code=40002, message="audio has no speech")
    except BizError:
        raise
    except Exception as exc:  # noqa: BLE001 - 读取异常不误拒，仅记录
        logger.warning("speech check failed for %s: %s", wav_path, exc)


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
        import asyncio
        import os

        os.makedirs("data/audio/tmp", exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".in", delete=False, dir="data/audio/tmp") as tmp:
            tmp.write(audio_bytes)
            src = tmp.name
        try:
            wav = src + ".wav"
            subprocess.run(
                [_ffmpeg_bin(), "-y", "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", wav],
                check=True,
                capture_output=True,
            )
            # 有效性前置过滤（docs/19 §2）：空录音/纯静音 → 40002 硬拒绝，不送 whisper + ISE
            _reject_if_silent(wav)
            return await asyncio.to_thread(self.transcribe_sync, wav, language)
        finally:
            for p in (src, src + ".wav"):
                Path(p).unlink(missing_ok=True)
