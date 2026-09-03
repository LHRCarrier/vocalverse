"""faster-whisper ASR 客户端（docs/06 §8：small/int8/CPU；ffmpeg 转 16k wav）。

- 延迟导入 faster_whisper/torch（重依赖，轻量测试环境走 Fake）；
- CPU 工作必须进线程（anyio.to_thread 由编排器包装）——本类仅同步接口；
- ffmpeg 是本服务唯一硬依赖（WebM/opus → 16k mono wav），生产镜像已装。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from app.audio.base import ASRClient, ASRResult

_FFMPEG = "ffmpeg"


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
        segments, info = model.transcribe(wav_path, language=language, beam_size=5)
        text = "".join(s.text for s in segments).strip()
        return ASRResult(
            text=text,
            language=info.language or language,
            confidence=float(getattr(info, "language_probability", 0.0) or 0.0),
            segments=[{"start": s.start, "end": s.end, "text": s.text} for s in segments],
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
            return await asyncio.to_thread(self.transcribe_sync, wav, language)
        finally:
            for p in (src, src + ".wav"):
                Path(p).unlink(missing_ok=True)
