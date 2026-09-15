"""本地 TTS 引擎：KittenTTS（KittenML/kitten-tts-mini-0.8 · Apache-2.0 · 78MB ONNX）。

- 模型权重**不入库**（红线）：运行时按 ``APP_VOICE_MODELS_DIR`` 引用 VoiceStudio 缓存目录
  （HF cache 结构 ``models--KittenML--kitten-tts-mini-0.8/snapshots/...``）；
- ``is_available()`` 三要素探测（docs/46 B 系列）：模型目录非空且存在 + ``kittentts``
  包可导入 + onnxruntime 可导入；不满足 → (False, 可读原因)，provider 链降级 edge；
- ``kittentts`` 为可选依赖（``pip install kittentts``，docs/45 §5）；HF_HOME 注入发生在
  **首次导入前**（kittentts/huggingface_hub 惰性解析缓存路径）；
- 输出 24kHz mono 16-bit WAV bytes；``rate`` 参数不接受（音色倍速由前端 playbackRate
  承担，docs/45 §5 拍板：免多档重合成）。
"""

from __future__ import annotations

import asyncio
import logging
import os
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

from app.audio.base import TTSClient

logger = logging.getLogger("vocalverse.tts.local")

#: 内置音色（KittenTTS mini 内置 8 个英文音色，README 核实）
KITTEN_VOICES: tuple[str, ...] = (
    "Bella",
    "Jasper",
    "Luna",
    "Bruno",
    "Rosie",
    "Hugo",
    "Kiki",
    "Leo",
)

KITTEN_SAMPLE_RATE = 24000


def _numpy_to_wav_bytes(audio: Any) -> bytes:
    """float32 [-1,1] → 24kHz mono 16-bit WAV bytes（无 soundfile 依赖手写）。"""
    import numpy as np

    data = np.asarray(audio, dtype=np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767).astype(np.int16)
    buf = BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(KITTEN_SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class KittenTTSClient(TTSClient):
    """KittenTTS 本地引擎客户端（TTSClient 契约：is_available 先行探测 + 生命周期幂等）。"""

    def __init__(self, model_dir: str = "", voice: str = "Jasper") -> None:
        self._model_dir = model_dir
        self._voice = voice
        self._model: Any | None = None

    # -- 探测 ----------------------------------------------------------------
    def is_available(self) -> tuple[bool, str]:
        if not self._model_dir:
            return False, "APP_VOICE_MODELS_DIR 未配置（本地引擎模型目录为空）"
        snapshots = Path(self._model_dir) / "models--KittenML--kitten-tts-mini-0.8" / "snapshots"
        if not snapshots.exists():
            return False, f"KittenTTS 模型目录不存在: {snapshots}"
        try:
            import kittentts  # noqa: F401
            import onnxruntime  # noqa: F401
        except Exception as exc:  # pragma: no cover - 环境未装可选依赖
            return False, f"kittentts/onnxruntime 未安装（pip install kittentts）: {exc}"
        return True, "ready"

    def ensure_ready(self) -> None:
        # 模型加载按需 + 缓存到实例（synthesize 首句 ~数秒，其后复用）
        if self._model is None:
            self._model = self._load_model()
        return None

    def _load_model(self) -> Any:
        if not self._model_dir:
            raise RuntimeError("APP_VOICE_MODELS_DIR 未配置")
        # HF_HOME 注入必须在 kittentts/huggingface_hub 首次解析缓存路径之前
        os.environ.setdefault("HF_HOME", self._model_dir)
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        from kittentts import KittenTTS

        logger.info("KittenTTS 加载中（目录 %s）", self._model_dir)
        return KittenTTS("KittenML/kitten-tts-mini-0.8")

    def unload(self) -> None:
        self._model = None  # 无显式释放 API；幂等 no-op 语义保持

    # -- 合成 ----------------------------------------------------------------
    async def synthesize(self, text: str, voice: str = "Jasper", rate: str = "+0%") -> bytes:
        if self._model is None:
            self.ensure_ready()
        voice = voice if voice in KITTEN_VOICES else self._voice
        audio = await asyncio.to_thread(self._model.generate, text, voice=voice)
        return _numpy_to_wav_bytes(audio)


__all__ = ["KittenTTSClient", "KITTEN_VOICES", "KITTEN_SAMPLE_RATE"]
