"""音频容器嗅探与回放 Content-Type 测试（BUG-5 · docs/06 §8 音频存储）。

覆盖：
- `sniff_audio_ext` 魔数嗅探（WebM/EBML、MP3(ID3 与帧同步)、WAV、OGG、M4A、未知/空）；
- `resolve_media_type` 嗅探优先于扩展名（**老文件**：`.mp3` 扩展名 + WebM 内容 → audio/webm）；
- `save_audio_bytes` 按内容定扩展名（webm 字节 → `.webm` 文件名；未知容器回落 `.mp3`）。
"""

from __future__ import annotations

from app.audio.upload import resolve_media_type, sniff_audio_ext
from app.practice.orchestrator import save_audio_bytes

# 各容器的最小可辨识头（真实样本取自本轮实测：浏览器录音 = EBML/WebM）
EBML_WEBM = b"\x1aE\xdf\xa3\x9fB\x86\x81\x01B\xf7\x81\x01B\xf2\x81\x04"
MP3_ID3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\x00" * 6
MP3_FRAME = b"\xff\xfb\x90\x00" + b"\x00" * 12
WAV_RIFF = b"RIFF\x24\x08\x00\x00WAVEfmt " + b"\x00" * 4
OGG = b"OggS\x00\x02\x00\x00" + b"\x00" * 8
M4A = b"\x00\x00\x00\x20ftypM4A " + b"\x00" * 4


def test_sniff_audio_ext_known_containers():
    assert sniff_audio_ext(EBML_WEBM) == "webm"
    assert sniff_audio_ext(MP3_ID3) == "mp3"
    assert sniff_audio_ext(MP3_FRAME) == "mp3"
    assert sniff_audio_ext(WAV_RIFF) == "wav"
    assert sniff_audio_ext(OGG) == "ogg"
    assert sniff_audio_ext(M4A) == "m4a"


def test_sniff_audio_ext_unknown():
    assert sniff_audio_ext(None) is None
    assert sniff_audio_ext(b"") is None
    assert sniff_audio_ext(b"not-an-audio-file-at-all") is None
    assert sniff_audio_ext(b"RIFF\x00\x00\x00\x00AVI ") is None  # RIFF 但非 WAVE


def test_resolve_media_type_sniff_beats_extension():
    """**BUG-5 核心回归**：历史录音是 `.mp3` 扩展名 + WebM 内容
    → 回放必须给 `audio/webm`（修复前恒 `audio/mpeg`，严格客户端可能拒播）。"""
    assert resolve_media_type(EBML_WEBM, "mp3") == "audio/webm"
    assert resolve_media_type(MP3_ID3, "mp3") == "audio/mpeg"
    # 嗅探不出（如参考旋律 wav 被截断读取）→ 按扩展名
    assert resolve_media_type(b"", "wav") == "audio/wav"
    assert resolve_media_type(b"", "webm") == "audio/webm"
    # 扩展名与内容都不可识别 → 默认 audio/mpeg（不抛错）
    assert resolve_media_type(b"", "weird") == "audio/mpeg"


def test_save_audio_bytes_uses_content_extension(tmp_path, monkeypatch):
    """保存侧按内容定扩展名：WebM 字节 → `.webm`（修复前一律 `.mp3`）。"""
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "audio_dir", str(tmp_path))
    url_webm = save_audio_bytes(EBML_WEBM + b"\x00" * 64)
    assert url_webm.endswith(".webm")
    assert (tmp_path / url_webm.rsplit("/", 1)[-1]).exists()
    url_unknown = save_audio_bytes(b"unknown-container-bytes" + b"\x00" * 40)
    assert url_unknown.endswith(".mp3")  # 未知容器 → 回落旧行为
    # 幂等：同内容重复保存 → 同名（不重复写）
    assert save_audio_bytes(EBML_WEBM + b"\x00" * 64) == url_webm
