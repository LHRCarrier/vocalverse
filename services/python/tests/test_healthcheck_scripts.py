"""健康检查脚本契约回归测试（PR#23 审核意见 B1/B2 的自动化版本：修复前必红）。

验证 scripts/healthcheck/check_*.py 的判定口径与仓库真实契约一致：
- POST /api/v1/asr → Envelope{code, message:"ok", data:{text}}（app/api/routes/audio.py L38-47）
- POST /api/v1/tts → Envelope{code, message:"ok", data:{audio_bytes:hex, length}}（L62-70）
- POST /api/v1/score → Envelope{code, message:"ok", data:{overall}}（L50-59）

修复前（PR#23 首版）：
- check_asr.py 要求「返回文本含关键字『成功』」→ 健康响应（message="ok"）必然误报不通过；
- check_tts.py 要求 Content-Type: audio/wav + 原始音频字节 → JSON Envelope 响应必然误报不通过。
本文件判定逻辑抽为纯函数 verdict()，不发起任何网络请求。
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _repo_root() -> Path:
    """向上查找包含 scripts/healthcheck 的仓库根（本测试位于 services/python/tests/）。"""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "scripts" / "healthcheck").is_dir():
            return parent
    raise RuntimeError("未找到仓库根（scripts/healthcheck 目录缺失）")


ROOT = _repo_root()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(
        f"hc_{name}", ROOT / "scripts" / "healthcheck" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ASR = _load("check_asr")
ISE = _load("check_ise")
TTS = _load("check_tts")


# ---------- ASR：契约口径 code==0 且文本非空 ----------


def test_asr_healthy_envelope_passes():
    # 契约真实响应：message="ok"，识别文本不含「成功」→ 旧「关键字」口径在本用例必然失败
    ok, reason = ASR.verdict(200, 0, "[stub] hello, I would like a coffee, please.", keyword=None)
    assert ok, reason


def test_asr_keyword_flag_when_enabled():
    ok, _ = ASR.verdict(200, 0, "成功识别", keyword="成功")
    assert ok
    ok, _ = ASR.verdict(200, 0, "hello world", keyword="成功")
    assert not ok


def test_asr_empty_text_fails():
    ok, _ = ASR.verdict(200, 0, "   ")
    assert not ok


def test_asr_biz_error_fails():
    ok, _ = ASR.verdict(200, 40001, "hello")
    assert not ok


def test_asr_http_error_fails():
    ok, _ = ASR.verdict(404, None, "not found")
    assert not ok


# ---------- TTS：契约口径 Envelope + audio_bytes hex ----------


def test_tts_healthy_hex_envelope_passes():
    # 契约真实响应：JSON Envelope，audio_bytes 为 hex → 旧「audio/wav 原始字节」口径必然失败
    ok, reason = TTS.verdict(200, 0, b"RIFF__fake_wav_payload__", declared_len=24)
    assert ok, reason


def test_tts_empty_audio_fails():
    ok, _ = TTS.verdict(200, 0, b"", declared_len=0)
    assert not ok


def test_tts_length_mismatch_fails():
    ok, _ = TTS.verdict(200, 0, b"abc", declared_len=5)
    assert not ok


def test_tts_parse_payload_decodes_hex():
    audio = b"RIFFdata"
    resp = SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=lambda: {
            "code": 0,
            "message": "ok",
            "data": {"audio_bytes": audio.hex(), "length": len(audio)},
        },
    )
    parsed, declared, err = TTS.parse_tts_payload(resp)
    assert err is None
    assert parsed == audio
    assert declared == len(audio)


def test_tts_parse_payload_rejects_non_hex():
    resp = SimpleNamespace(
        status_code=200,
        headers={"Content-Type": "application/json"},
        json=lambda: {"code": 0, "message": "ok", "data": {"audio_bytes": "zz", "length": 1}},
    )
    parsed, declared, err = TTS.parse_tts_payload(resp)
    assert err is not None and parsed is None


# ---------- ISE：契约字段 data.overall ----------


def test_ise_healthy_overall_passes():
    ok, reason = ISE.verdict(200, 0, 88.0)
    assert ok, reason


def test_ise_missing_score_fails():
    ok, _ = ISE.verdict(200, 0, None)
    assert not ok


def test_ise_out_of_range_fails():
    ok, _ = ISE.verdict(200, 0, 120.0)
    assert not ok
    ok, _ = ISE.verdict(200, 0, -1.0)
    assert not ok


def test_ise_http_error_fails():
    ok, _ = ISE.verdict(503, None, None)
    assert not ok
