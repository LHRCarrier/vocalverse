"""音频容器时长估算（纯函数 · 零依赖 · 绝不抛错）。

为什么需要它：前端排播要求 ``AudioChunk.duration``（docs/44 P1-C / vtts-04），而
TTSEngine 的输出容器**不止 MP3**——本地引擎（KittenTTS / OmniVoice）出的是 24 kHz
WAV。重构前热路径只调 ``mp3_duration_seconds``，换本地引擎后时长恒为 ``None``，
前端 gap-less 排播静默退化成「等 onended」（本地 WAV 短句上偶发不触发）。
本模块把「按容器选估算器」收敛到一处。

约定：任何异常/未知容器 → ``None``（调用方按「时长未知」降级，绝不因此失败）。
"""

from __future__ import annotations

import struct

# ── MP3（MPEG Layer III，CBR）────────────────────────────────────────────────
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


def wav_duration_seconds(data: bytes) -> float | None:
    """PCM WAV 时长（秒）：读 RIFF 头 → ``data_bytes / (rate × channels × width)``。

    只处理 fmt 块为 PCM(1)/IEEE float(3) 且能找到 data 块的常规布局；异常 → None。
    """
    try:
        if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
            return None
        pos = 12
        fmt: tuple[int, int, int, int] | None = None  # (channels, rate, bits, audio_format)
        data_bytes: int | None = None
        while pos + 8 <= len(data):
            chunk_id = data[pos : pos + 4]
            (chunk_size,) = struct.unpack_from("<I", data, pos + 4)
            body = pos + 8
            if chunk_id == b"fmt " and body + 16 <= len(data):
                audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack_from(
                    "<HHIIHH", data, body
                )
                fmt = (channels, rate, bits, audio_format)
            elif chunk_id == b"data":
                data_bytes = min(chunk_size, max(0, len(data) - body))
                break
            pos = body + chunk_size + (chunk_size & 1)
        if fmt is None or data_bytes is None:
            return None
        channels, rate, bits, audio_format = fmt
        if audio_format not in (1, 3) or channels <= 0 or rate <= 0 or bits <= 0:
            return None
        frame_bytes = channels * (bits // 8)
        if frame_bytes <= 0:
            return None
        duration = data_bytes / float(rate * frame_bytes)
        return duration if duration > 0 else None
    except Exception:  # noqa: BLE001 — 纯函数：任何畸形输入都退化为 None
        return None


def audio_duration_seconds(data: bytes) -> float | None:
    """按容器嗅探选择估算器（WAV → WAV 解析；其余 → MP3 帧头）；未知 → None。"""
    if not data:
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return wav_duration_seconds(data)
    return mp3_duration_seconds(data)


__all__ = [
    "audio_duration_seconds",
    "mp3_duration_seconds",
    "wav_duration_seconds",
]
