"""edge-tts 合成客户端（docs/06 §8：默认 edge-tts，Azure 备胎）。

- 逐句合成（POC-1 实测：单句 ≈1.34s 网络往返 —— 见 docs/06 §8 延迟表，
  因此设计为「首句到达即合成 + 后续句并发预热」，并配合开场/常用句预合成缓存）；
- 延迟导入 edge_tts（保持轻量测试环境可用）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.audio.base import TTSClient


class EdgeTTSClient(TTSClient):
    def __init__(self, voice: str = "en-US-JennyNeural", rate: str = "+0%"):
        self._voice = voice
        self._rate = rate

    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        try:
            import edge_tts
        except ImportError as exc:  # pragma: no cover - 环境未装（轻量测试走 Fake）
            raise RuntimeError("edge-tts 未安装（生产镜像已含；轻量环境请用 Fake）") from exc

        communicate = edge_tts.Communicate(text, voice or self._voice, rate=rate or self._rate)
        chunks: list[bytes] = []
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        if not chunks:
            raise RuntimeError(f"edge-tts 返回空音频: {text[:40]!r}")
        return b"".join(chunks)


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
