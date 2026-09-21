"""edge-tts 合成客户端（docs/06 §8：默认 edge-tts）。

- 逐句合成（POC-1 实测：单句 ≈1.34s 网络往返 —— 见 docs/06 §8 延迟表，
  因此设计为「首句到达即合成 + 后续句并发预热」，并配合开场/常用句预合成缓存）；
- 延迟导入 edge_tts（保持轻量测试环境可用）。
- 生命周期（docs/44 P0-B）：``is_available`` 提前探测 + ``synthesize`` 超时/单发重试，
  edge-tts 受限/改协议/断网时不静默、不挂死，失败明确上抛供调用方降级。

**本模块只放引擎**。缓存/键/裁剪/预热在 :mod:`app.audio.tts_cache`，
时长估算在 :mod:`app.audio.duration`（重构前它们全部挤在本文件里）。
"""

from __future__ import annotations

import asyncio
import logging

from app.audio.base import TTSClient
from app.audio.registry import TTS as _TTS
from app.audio.registry import ProviderSpec, register

logger = logging.getLogger("vocalverse.tts")

#: 单句合成超时（秒）。edge-tts 断网/受限时防挂死（docs/audit:128 「无超时/熔断/重试」→ 补上）。
_DEFAULT_TIMEOUT_S = 30.0

#: 合成失败重试次数（初试 + 重试 = 2；单发重试，参考 VS「明确失败而非循环」思路）。
_MAX_ATTEMPTS = 2


class EdgeTTSClient(TTSClient):
    """edge-tts（微软 Edge 在线朗读服务）客户端。"""

    provider_id = "edge"
    media_type = "audio/mpeg"
    ext = "mp3"
    is_local = False
    langs = ("en",)

    def __init__(
        self,
        voice: str = "en-US-JennyNeural",
        rate: str = "+0%",
        timeout_s: float = _DEFAULT_TIMEOUT_S,
    ):
        self._voice = voice
        self._rate = rate
        self._timeout_s = timeout_s

    def is_available(self) -> tuple[bool, str]:
        try:
            import edge_tts  # noqa: F401

            return True, "ready"
        except Exception as exc:  # pragma: no cover - 轻量测试环境走 Fake
            return False, f"edge-tts import failed: {exc}"

    def ensure_ready(self) -> None:
        # edge-tts 无本地模型/预热；连接惰性建立，无需 LOAD 预算分离。
        return None

    def unload(self) -> None:
        # edge-tts 是网络客户端，无进程内模型可释放；保持契约幂等 no-op。
        return None

    async def _stream_audio(self, text: str, voice: str, rate: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(text, voice or self._voice, rate=rate or self._rate)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        if not chunks:
            raise RuntimeError(f"edge-tts 返回空音频: {text[:40]!r}")
        return b"".join(chunks)

    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        last: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                return await asyncio.wait_for(
                    self._stream_audio(text, voice or self._voice, rate or self._rate),
                    timeout=self._timeout_s,
                )
            except Exception as exc:  # noqa: BLE001 — 网络/受限/超时均可单发重试
                last = exc
                logger.warning(
                    "edge-tts 合成失败 (attempt %d/%d): %s | %r",
                    attempt,
                    _MAX_ATTEMPTS,
                    exc,
                    text[:40],
                )
        raise RuntimeError(
            f"edge-tts 合成失败（已重试 {_MAX_ATTEMPTS} 次）: {text[:40]!r}"
        ) from last


class AzureNotWiredClient(TTSClient):
    """Azure 备胎占位（docs/44 P0-C）：显式报告未接线，调用方据此干净降级。

    config 里 ``tts_provider='azure'``/``azure_tts_key`` 有字段但无实现（docs/audit:135 K02）——
    本类让「存在即切」不再是承诺：``is_available()`` 返回可读原因，
    ``synthesize`` 抛明确的未接线错误。
    P0-C 接线 azure-cognitiveservices-speech 后替换为真实 ``AzureTTSClient``。
    """

    provider_id = "azure"
    media_type = "audio/mpeg"
    ext = "mp3"
    is_local = False

    def is_available(self) -> tuple[bool, str]:
        return False, "Azure TTS 未接线（见 docs/44 P0-C）"

    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        raise RuntimeError("Azure TTS 未接线（见 docs/44 P0-C）")


# ── 注册表登记 ────────────────────────────────────────────────────────────────
register(
    ProviderSpec(
        name="edge",
        kind=_TTS,
        label="edge-tts（在线 · 微软 Edge 朗读）",
        factory=lambda settings: EdgeTTSClient(
            voice=getattr(settings, "tts_voice", "en-US-JennyNeural"),
            rate=getattr(settings, "tts_rate", "+0%"),
        ),
        priority=30,  # auto 链：本地引擎优先，edge 作为通用兜底
        is_local=False,
        ext="mp3",
        media_type="audio/mpeg",
    )
)
register(
    ProviderSpec(
        name="azure",
        kind=_TTS,
        label="Azure Speech（未接线占位 · docs/44 P0-C）",
        factory=lambda _settings: AzureNotWiredClient(),
        priority=90,
        is_local=False,
        ext="mp3",
        media_type="audio/mpeg",
    )
)
