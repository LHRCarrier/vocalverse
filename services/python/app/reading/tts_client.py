"""读书域 · 听书 TTS provider 依赖注入（docs/45 §5）。

与 ``app.audio.base.get_tts_client`` **分离**（拷问 M-10：不扩既有热路径客户端的
provider 链，避免触碰 practice 缓存语义）：

- 选择链：显式 provider（edge|kitten）→ 按配置；``auto`` → kitten 可用则 kitten，
  否则 edge（断网/未装依赖的自然降级，无静默错误）；
- ``APP_TESTING=true`` → ``FakeTTSClient``（CI 零真实 Key，与 base.py 同款三档）。
"""

from __future__ import annotations

import logging

from app.audio.base import TTSClient
from app.audio.tts import EdgeTTSClient
from app.core.config import get_settings

logger = logging.getLogger("vocalverse.reading.tts")


def get_reading_tts_client(provider: str | None = None) -> TTSClient:
    settings = get_settings()
    if settings.testing:
        from app.audio.stubs import FakeTTSClient

        return FakeTTSClient()
    chosen = (provider or settings.reading_tts_provider or "auto").lower()
    if chosen not in ("auto", "edge", "kitten"):
        chosen = "auto"  # 配置漂移兜底（只校验枚举不 fail-fast，docs/46 B-7）
    if chosen in ("kitten", "auto"):
        from app.audio.tts_local import KittenTTSClient

        kitten = KittenTTSClient(settings.voice_models_dir)
        available, reason = kitten.is_available()
        if chosen == "kitten" and not available:
            # 显式 kitten 但不可用：上抛可读错误（路由 → 503 45007），不静默换 edge
            raise RuntimeError(f"kitten TTS unavailable: {reason}")
        if available:
            return kitten
        if chosen == "auto":
            logger.info("reading_tts auto: kitten 不可用（%s）→ 降级 edge", reason)
    return EdgeTTSClient(voice=settings.tts_voice, rate=settings.tts_rate)


__all__ = ["get_reading_tts_client"]
