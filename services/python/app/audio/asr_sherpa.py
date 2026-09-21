"""sherpa-onnx 本地 ASR 引擎（Apache-2.0 · k2-fsa）—— 第二本地引擎 / 降级路径。

定位（docs/28 §3.2 P0-B）：faster-whisper 是主引擎，但依赖重（CTranslate2 + PyAV）、
冷启与内存敏感。sherpa-onnx 基于 onnxruntime，模型小、离线、跨平台，适合做：

- ``APP_ASR_PROVIDER=auto`` 时的**第二顺位**（本地 whisper 不可用时自动接管）；
- 移动端「原生离线 ASR」的前置技术验证（docs/27）；
- 低配机器的轻量选择。

**能力边界（诚实声明）**：本引擎走 sherpa-onnx 的 offline recognizer，默认不开
词级时间戳，因此 ``ASRResult.words`` 恒为空 → 流利度时间戳特征（wpm/停顿）不可用。
下游已有「无时间戳 → wpm=None」的既有降级路径（见 tests/test_shadow.py），
不会因此报错。需要词级时间戳的链路请继续用 whisper。

依赖为**可选**：``uv sync --extra local-asr`` 或 ``pip install sherpa-onnx``；
未安装时 ``is_available()`` 返回可读原因，``auto`` 链自动跳过本引擎。
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import threading
import wave
from pathlib import Path
from typing import Any

from app.audio.base import ASRClient, ASRResult
from app.audio.ffmpeg_utils import run_ffmpeg
from app.audio.registry import ASR as _ASR
from app.audio.registry import ProviderSpec, register

logger = logging.getLogger("vocalverse.asr.sherpa")

SAMPLE_RATE = 16000

#: 支持的模型族 → 需要的文件（缺一即视为未就绪）
_REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "transducer": ("encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt"),
    "sense_voice": ("model.onnx", "tokens.txt"),
    "paraformer": ("model.onnx", "tokens.txt"),
    "whisper": ("encoder.onnx", "decoder.onnx", "tokens.txt"),
}


def _pick_required(model_type: str) -> tuple[str, ...]:
    return _REQUIRED_FILES.get(model_type, _REQUIRED_FILES["sense_voice"])


def missing_model_files(model_dir: str, model_type: str) -> list[str]:
    """返回缺失的模型文件名（纯函数，可单测；目录为空 → 要求清单全缺）。"""
    if not model_dir:
        return list(_pick_required(model_type))
    base = Path(model_dir)
    if not base.is_dir():
        return list(_pick_required(model_type))
    return [name for name in _pick_required(model_type) if not (base / name).exists()]


class SherpaOnnxASRClient(ASRClient):
    """sherpa-onnx 离线识别（整段音频；不做流式端点检测）。"""

    provider_id = "sherpa"
    is_local = True

    def __init__(self, model_dir: str = "", model_type: str = "sense_voice", num_threads: int = 2):
        self._model_dir = model_dir
        self._model_type = (model_type or "sense_voice").lower()
        self._num_threads = max(1, int(num_threads or 2))
        self._recognizer: Any | None = None
        self._load_lock = threading.Lock()

    # -- 探测 / 生命周期 ------------------------------------------------------
    def is_available(self) -> tuple[bool, str]:
        if not self._model_dir:
            return False, "APP_ASR_SHERPA_MODEL_DIR 未配置（本地 sherpa 模型目录为空）"
        try:
            import numpy  # noqa: F401
            import sherpa_onnx  # noqa: F401
        except Exception as exc:  # pragma: no cover - 可选依赖未装
            return False, f"sherpa-onnx 未安装（uv sync --extra local-asr）: {exc}"
        missing = missing_model_files(self._model_dir, self._model_type)
        if missing:
            return False, f"sherpa 模型文件缺失于 {self._model_dir}: {', '.join(missing)}"
        return True, "ready"

    def ensure_ready(self) -> None:
        self._get_recognizer()

    def unload(self) -> None:
        self._recognizer = None  # onnxruntime session 随引用释放；幂等

    def _get_recognizer(self) -> Any:
        if self._recognizer is None:
            with self._load_lock:
                if self._recognizer is None:
                    self._recognizer = self._build_recognizer()
        return self._recognizer

    def _build_recognizer(self) -> Any:
        import sherpa_onnx

        base = Path(self._model_dir)
        common = {
            "tokens": str(base / "tokens.txt"),
            "num_threads": self._num_threads,
            "provider": "cpu",
        }
        logger.info("sherpa-onnx 加载中（%s · %s）", self._model_type, self._model_dir)
        if self._model_type == "transducer":
            return sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(base / "encoder.onnx"),
                decoder=str(base / "decoder.onnx"),
                joiner=str(base / "joiner.onnx"),
                **common,
            )
        if self._model_type == "sense_voice":
            return sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(base / "model.onnx"),
                use_itn=True,
                **common,
            )
        if self._model_type == "paraformer":
            return sherpa_onnx.OfflineRecognizer.from_paraformer(
                paraformer=str(base / "model.onnx"),
                **common,
            )
        return sherpa_onnx.OfflineRecognizer.from_whisper(
            encoder=str(base / "encoder.onnx"),
            decoder=str(base / "decoder.onnx"),
            **common,
        )

    # -- 转写 ----------------------------------------------------------------
    def transcribe_sync(self, wav_path: str, language: str = "en") -> ASRResult:
        """同步转写 16k mono wav（CPU 重活，调用方须进线程）。"""
        import numpy as np

        recognizer = self._get_recognizer()
        with wave.open(wav_path, "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate() or SAMPLE_RATE
            raw = wf.readframes(frames)
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        stream = recognizer.create_stream()
        stream.accept_waveform(rate, samples)
        recognizer.decode_stream(stream)
        text = (getattr(stream.result, "text", "") or "").strip()
        return ASRResult(
            text=text,
            language=language,
            confidence=0.0,
            segments=[{"start": 0.0, "end": frames / float(rate or SAMPLE_RATE), "text": text}],
            words=[],  # 见模块 docstring：sherpa 离线路径不产出词级时间戳
            duration=frames / float(rate or SAMPLE_RATE),
            no_speech=not text,
        )

    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        import os

        tmp_dir = os.path.join("data", "audio", "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        with tempfile.NamedTemporaryFile(suffix=".in", delete=False, dir=tmp_dir) as tmp:
            tmp.write(audio_bytes)
            src = tmp.name
        wav = src + ".wav"
        try:
            await run_ffmpeg(
                ["-y", "-i", src, "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "wav", wav],
                timeout_s=15.0,
            )
            return await asyncio.to_thread(self.transcribe_sync, wav, language)
        finally:
            for path in (src, wav):
                Path(path).unlink(missing_ok=True)


# ── 注册表登记 ────────────────────────────────────────────────────────────────
register(
    ProviderSpec(
        name="sherpa",
        kind=_ASR,
        label="sherpa-onnx（本地 · onnxruntime 轻量）",
        factory=lambda settings: SherpaOnnxASRClient(
            model_dir=getattr(settings, "asr_sherpa_model_dir", ""),
            model_type=getattr(settings, "asr_sherpa_model_type", "sense_voice"),
            num_threads=getattr(settings, "asr_sherpa_num_threads", 2),
        ),
        priority=20,
        is_local=True,
        aliases=("sherpa-onnx", "sherpa_onnx"),
    )
)
