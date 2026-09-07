"""edge-tts 合成客户端（docs/06 §8：默认 edge-tts，Azure 备胎）。

- 逐句合成（POC-1 实测：单句 ≈1.34s 网络往返 —— 见 docs/06 §8 延迟表，
  因此设计为「首句到达即合成 + 后续句并发预热」，并配合开场/常用句预合成缓存）；
- 延迟导入 edge_tts（保持轻量测试环境可用）。
- 生命周期（docs/44 P0-B）：``is_available`` 提前探测 + ``synthesize`` 超时/单发重试，
  edge-tts 受限/改协议/断网时不静默、不挂死，失败明确上抛供调用方降级。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.audio.base import TTSClient

logger = logging.getLogger("vocalverse.tts")

#: 单句合成超时（秒）。edge-tts 断网/受限时防挂死（docs/audit:128 「无超时/熔断/重试」→ 补上）。
_DEFAULT_TIMEOUT_S = 30.0

#: 合成失败重试次数（初试 + 重试 = 2；单发重试，参考 VS「明确失败而非循环」思路）。
_MAX_ATTEMPTS = 2

# ── MP3 时长估算（docs/44 P1-C / vtts-04）──────────────────────────────────────
# 纯函数、绝不抛错：非 MP3 / 定位不到帧头 / 非法帧头 → None。
# 适用 CBR（Microsoft edge-tts 默认 'audio-24khz-48kbitrate-mono-mp3' 为 CBR）；
# VBR 文件为近似值，ID3v2 头被跳过。

#: MPEG 版本 → 位率表（Layer III，单位 kbps；索引 0 = free，15 = 非法，不进表）。
_MPEG_L3_BITRATES: dict[int, tuple[int, ...]] = {
    3: (32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320),  # MPEG1
    2: (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),  # MPEG2
    0: (8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160),  # MPEG2.5
}


def mp3_duration_seconds(data: bytes) -> float | None:
    """估算 MP3 音频时长（秒）。CBR 下精度 ≈±1 帧（6ms 级）；任何异常 → None。

    计算：跳过 ID3v2 标签 → 定位首个合法同步帧（0xFFE + 版本/位率/采样率索引校验）→
    ``剩余字节 × 8 / 位率``。不解析解码，零依赖、零 IO。
    """
    if not data:
        return None
    offset = 0
    if data[:3] == b"ID3":
        if len(data) < 10:
            return None
        size = (
            ((data[6] & 0x7F) << 21)
            | ((data[7] & 0x7F) << 14)
            | ((data[8] & 0x7F) << 7)
            | (data[9] & 0x7F)
        )
        offset = 10 + size
        if offset >= len(data):
            return None
    i = offset
    header: tuple[int, int, int] | None = None
    limit = len(data) - 4
    while i <= limit:
        if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
            version = (data[i + 1] >> 3) & 0x03  # 0b11=MPEG1, 0b10=MPEG2, 0b00=MPEG2.5
            layer = (data[i + 1] >> 1) & 0x03  # 0b01 = Layer III
            br_idx = (data[i + 2] >> 4) & 0x0F
            sr_idx = (data[i + 2] >> 2) & 0x03
            if version != 1 and layer == 1 and 0 < br_idx < 15 and sr_idx != 3:
                header = (i, version, br_idx)
                break
        i += 1
    if header is None:
        return None
    pos, version, br_idx = header
    br_kbps = _MPEG_L3_BITRATES[version][br_idx - 1]
    payload_bytes = len(data) - pos
    if payload_bytes <= 0:
        return None
    duration = payload_bytes * 8.0 / (br_kbps * 1000.0)
    return duration if duration > 0 else None


class EdgeTTSClient(TTSClient):
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

    def is_available(self) -> tuple[bool, str]:
        return False, "Azure TTS 未接线（见 docs/44 P0-C）"

    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        raise RuntimeError("Azure TTS 未接线（见 docs/44 P0-C）")


async def synthesize_concurrent(
    client: TTSClient, sentences: list[str], voice: str = "", rate: str = ""
) -> list[bytes]:
    """并发合成（每句一轮网络往返，并发摊薄总时长——POC-1 结论）。"""
    results = await asyncio.gather(
        *(client.synthesize(s, voice=voice, rate=rate) for s in sentences)
    )
    return list(results)


def cached_audio_path(cache_dir: Path, key: str) -> Path:
    """预合成缓存路径（开场白/常用句；demo 保底，docs/06 §8）。"""
    path = cache_dir / f"{key}.tts.mp3"
    return path


def atomic_write_cache(path: Path, data: bytes) -> None:
    """原子写缓存（tmp + os.replace）：并发同句合成/半文件都可防 —— 不产生脏缓存。

    Windows/Linux 均原子；同 key 同参数 → 内容一致，重复覆盖无副作用（docs/19 P0-5 健壮性）。
    """
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def tts_cache_key(voice: str, rate: str, text: str) -> str:
    """缓存键：voice/rate/文本归一（同一句不同参数互不串用）。"""
    import hashlib

    return hashlib.sha1(f"{voice}|{rate}|{text.strip()}".encode()).hexdigest()[:24]
