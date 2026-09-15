"""上传音频的公共校验（大小上下界）+ 容器嗅探（BUG-5）。

上界 41301 见 docs/06 §7；下界 40002 用于挡住「空/近空音频」——
前端录音停止键修好后，误触会产生 ~0ms 的 webm 容器（几百字节），
而 placement/practice 收下即推进题目或回合且**不可重来**，还会白白消耗
ASR/ISE 限流额度。故这两条链路在扣额度之前先做下界校验。

`/api/v1/asr`、`/api/v1/score` 是无状态的管线端点（不消耗可耗尽资源），
沿用 min_bytes=0 的历史行为，只共用上界实现。

**容器嗅探（2026-09-10 · BUG-5）**：浏览器 MediaRecorder 录的是 `audio/webm;codecs=opus`，
而历史实现把**所有**用户录音一律存成 `<sha1>.mp3` → `GET /api/v1/audio/{name}` 按扩展名
给出 `Content-Type: audio/mpeg`，与内容不符（严格客户端可能拒播；实测 4 段历史录音魔数
均为 EBML/WebM）。修复：保存时按魔数决定扩展名，回放时按魔数决定 Content-Type
（老文件无需迁移——嗅探优先于扩展名）。
"""

from __future__ import annotations

from app.core.response import BizError

#: 扩展名 → MIME（单一真源；routes 侧复用）
AUDIO_MEDIA_TYPE: dict[str, str] = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "webm": "audio/webm",
}
DEFAULT_AUDIO_EXT = "mp3"


def validate_audio_bytes(data: bytes | None, *, min_bytes: int, max_bytes: int) -> bytes:
    """校验音频字节数，越界抛 BizError；通过则原样返回。"""
    if data is None or len(data) < min_bytes:
        raise BizError(
            http_status=400,
            code=40002,
            message="audio empty or too short",
        )
    if len(data) > max_bytes:
        raise BizError(http_status=413, code=41301, message="audio too large")
    return data


def sniff_audio_ext(data: bytes | None) -> str | None:
    """魔数嗅探容器类型 → 扩展名（mp3/webm/ogg/wav/m4a）；无法识别 → None。

    纯函数（可单测）。只认**容器/帧同步**层面的确定特征，不做编解码判断：
    - ``1A 45 DF A3`` EBML → webm（Matroska；浏览器 MediaRecorder 默认容器）
    - ``OggS`` → ogg；``RIFF....WAVE`` → wav；``ID3`` 或 MPEG 帧同步 ``FF Ex`` → mp3
    - ``....ftyp`` ISO BMFF → m4a（Safari MediaRecorder 的 audio/mp4）
    """
    if not data:
        return None
    head = bytes(data[:16])
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "webm"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"ID3"):
        return "mp3"
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:
        return "mp3"  # MPEG-1/2/2.5 audio frame sync
    if len(head) >= 8 and head[4:8] == b"ftyp":
        return "m4a"
    return None


def resolve_media_type(head: bytes | None, ext: str | None) -> str:
    """回放 Content-Type：**嗅探优先**（修正扩展名与内容不符），不可识别才按扩展名。

    ``head`` 只需文件前 16 字节（调用方读 64B 足够）。
    """
    sniffed = sniff_audio_ext(head)
    key = sniffed or (ext or "").lstrip(".").lower() or DEFAULT_AUDIO_EXT
    return AUDIO_MEDIA_TYPE.get(key, AUDIO_MEDIA_TYPE[DEFAULT_AUDIO_EXT])
