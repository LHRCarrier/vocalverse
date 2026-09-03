"""讯飞 ISE 流式客户端单测（转码/分帧/解析；全程无 Key、无真实调用）。"""

from __future__ import annotations

import base64
import io
import subprocess
import wave

import pytest
from app.audio.asr import _ffmpeg_bin
from app.audio.ise import _ise_frames, _parse_ise, _to_pcm16

# 真实响应结构（2026-09-03 实测）：sentence 层 accuracy/fluency/standard/total，
# integrity_score 只在 read_chapter 层；词级 word(content/total_score) + phone 细评。
XML_REAL = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<xml_result><read_sentence lan="en" type="study" version="7.0.0.1020">'
    "<rec_paper>"
    '<read_chapter accuracy_score="97.590760" fluency_score="92.696160" '
    'integrity_score="100.000000" standard_score="95.323020" total_score="95.895600" '
    'word_count="7">'
    '<sentence accuracy_score="92.590760" fluency_score="87.696160" standard_score="90.323020" '
    'total_score="90.895600" word_count="7">'
    '<word content="hello" total_score="98.091300"><syll><phone content="hh"/></syll></word>'
    '<word content="sil"/>'
    "</sentence>"
    "</read_chapter>"
    "</rec_paper>"
    "</read_sentence></xml_result>"
)


def _ffmpeg_ready() -> bool:
    try:
        subprocess.run([_ffmpeg_bin(), "-version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


_NEED_FFMPEG = pytest.mark.skipif(
    not _ffmpeg_ready(), reason="ffmpeg 不可用（PATH/FFMPEG_BIN/imageio 均无）"
)


def _wav_8k_1s() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 8000)  # 1 秒静音
    return buf.getvalue()


@_NEED_FFMPEG
def test_to_pcm16_converts_to_16k_mono_s16le() -> None:
    """回归：ISE 只收 16k 单声道 s16le 裸 PCM（auf=L16;rate=16000, aue=raw）。

    编排器传入原始 WebM 字节；1s@8k → 1s@16k = 16000×2 字节（不转码 ISE 解码失败）。
    """
    out = _to_pcm16(_wav_8k_1s())
    assert len(out) == 16000 * 2


def test_ise_frames_chunk_status() -> None:
    """分帧：aus 首帧1/中间2/末帧4，status 1/1/2；base64 可还原且每帧 ≤ 26000 字符。"""
    pcm = b"\x01\x02\x03" * 30000  # 90KB
    frames = _ise_frames(pcm)
    assert frames[0] == (1, 1, base64.b64encode(pcm[:19000]).decode())
    assert frames[-1][:2] == (4, 2)
    assert b"".join(base64.b64decode(c) for _, _, c in frames) == pcm
    assert all(len(c) <= 26000 for _, _, c in frames)


def test_ise_frames_single_chunk() -> None:
    """单帧音频：内容帧 (aus=1,status=1) + 空末帧 (aus=4,status=2) 结束信号。"""
    frames = _ise_frames(b"\x00" * 100)
    assert len(frames) == 2
    assert frames[0][:2] == (1, 1) and frames[0][2]
    assert frames[1] == (4, 2, "")


def test_parse_ise_real_response() -> None:
    """契约解析（真实结构）：sentence 总分 + 词级；完整性回退到 read_chapter 层。"""
    out = _parse_ise({"code": 0, "data": {"ise_res": {"xml": XML_REAL}}})
    assert out["overall"] == 90.8956
    assert out["pron"] == 92.59076
    assert out["flu"] == 87.69616
    assert out["completeness"] == 100.0  # sentence 层无 integrity_score → chapter 回退
    assert out["words"][0] == {"word": "hello", "error_type": "other", "score": 98.0913}
    assert out["words"][1]["word"] == "sil"  # 静音帧（score 缺失 → 0）
    assert out["words"][1]["score"] == 0.0


def test_parse_ise_missing_fields_degrades() -> None:
    """字段缺失/畸形时保守降级为 0，不抛异常。"""
    out = _parse_ise({"code": 0, "data": {"ise_res": {"xml": "<xml_result></xml_result>"}}})
    assert (out["overall"], out["pron"], out["flu"], out["completeness"], out["words"]) == (
        0.0,
        0.0,
        0.0,
        0.0,
        [],
    )
    out2 = _parse_ise({"code": 1, "message": "boom"})
    assert out2 == {"overall": 0.0, "pron": 0.0, "flu": 0.0, "completeness": 0.0, "words": []}
