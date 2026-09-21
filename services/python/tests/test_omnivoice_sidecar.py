"""OmniVoice 边车契约测试（`services/omnivoice-sidecar/server.py`）。

边车是**独立进程**（torch + GPU），因此它的价值全在「契约」二字：
一旦服务端校验逻辑与调用方（`app/audio/tts_omnivoice.py`）漂移，真机上才会以
「克隆请求被 400 掉」或「静默按设计模式随机抽了一把嗓子」的形式暴露。
本文件用同一份请求体喂两边，把漂移挡在 CI：

1. `validate()` 纯函数全量覆盖（不 import torch，任何机器可跑）；
2. **跨进程契约对账**：客户端 `build_request()` 造出的体，必须能通过服务端 `validate()`。

边车模块按**文件路径**加载（它不在 `services/python` 包内，也不该被装成包），
与 `tests/test_healthcheck_scripts.py` 加载 `scripts/` 下脚本同一手法。
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVER_PY = _REPO_ROOT / "services" / "omnivoice-sidecar" / "server.py"


def _load_sidecar():
    assert _SERVER_PY.exists(), f"边车服务缺失：{_SERVER_PY}"
    spec = importlib.util.spec_from_file_location("vv_omnivoice_sidecar", _SERVER_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sidecar = _load_sidecar()

_REF_TEXT = "Good evening. Topping our broadcast tonight."
_WAV = b"RIFF____fake_reference_wav____"


def _clone_body(**over) -> dict:
    body = {
        "text": "Good evening.",
        "language": "en",
        "mode": "clone",
        "ref": {"audioBase64": base64.b64encode(_WAV).decode(), "text": _REF_TEXT},
        "seed": 42,
        "format": "wav",
    }
    body.update(over)
    return body


def _err_code(body: dict) -> str:
    with pytest.raises(sidecar.SynthError) as ei:
        sidecar.validate(body)
    return ei.value.code


# ---------------------------------------------------------------------------
# validate()：正常路径
# ---------------------------------------------------------------------------


def test_clone_normalizes_request() -> None:
    req = sidecar.validate(_clone_body())
    assert req["mode"] == "clone"
    assert req["language"] == "en"
    assert req["ref"]["audio"] == _WAV  # base64 已解码回字节
    assert req["ref"]["text"] == _REF_TEXT.strip()
    assert req["seed"] == 42
    assert req["format"] == "wav"


def test_design_requires_instruct_and_rejects_ref() -> None:
    req = sidecar.validate({"text": "hi", "mode": "design", "instruct": "male, low pitch"})
    assert req["instruct"] == "male, low pitch"
    assert (
        _err_code({"text": "hi", "mode": "design", "instruct": "x", "ref": {}}) == "REF_IN_DESIGN"
    )


def test_auto_takes_neither_ref_nor_instruct() -> None:
    assert sidecar.validate({"text": "hi", "mode": "auto"})["mode"] == "auto"
    assert _err_code({"text": "hi", "mode": "auto", "instruct": "x"}) == "AUTO_EXCLUSIVE"


def test_language_whitelist_and_optional() -> None:
    assert sidecar.validate({"text": "hi", "mode": "auto", "language": "EN"})["language"] == "en"
    assert sidecar.validate({"text": "hi", "mode": "auto"})["language"] is None
    assert _err_code({"text": "hi", "mode": "auto", "language": "jp"}) == "BAD_LANGUAGE"


def test_format_default_wav_and_whitelist() -> None:
    assert sidecar.validate({"text": "hi", "mode": "auto"})["format"] == "wav"
    assert _err_code({"text": "hi", "mode": "auto", "format": "flac"}) == "BAD_FORMAT"


# ---------------------------------------------------------------------------
# validate()：失败语义（每条都对应一种真实误用）
# ---------------------------------------------------------------------------


def test_bad_request_shapes() -> None:
    assert _err_code([]) == "BAD_REQUEST"  # 不是对象
    assert _err_code({"mode": "auto"}) == "BAD_REQUEST"  # 缺 text
    assert _err_code({"text": "   ", "mode": "auto"}) == "BAD_REQUEST"  # 空白 text
    assert (
        _err_code({"text": "x" * (sidecar.MAX_TEXT_CHARS + 1), "mode": "auto"}) == "TEXT_TOO_LONG"
    )


def test_mode_is_mandatory_and_not_guessed() -> None:
    """刻意不猜 mode：猜错的表现是「我要克隆，它却随机抽了一把嗓子」且不报错。"""
    assert _err_code({"text": "hi"}) == "BAD_MODE"
    assert _err_code({"text": "hi", "mode": "Clone"}) == "BAD_MODE"


def test_clone_ref_failure_modes() -> None:
    assert _err_code({"text": "hi", "mode": "clone"}) == "REF_REQUIRED"  # 整个 ref 缺失
    assert _err_code({"text": "hi", "mode": "clone", "ref": {}}) == "REF_REQUIRED"  # 字段缺失
    body = _clone_body(ref={"audioBase64": "not base64!!", "text": "x"})
    assert _err_code(body) == "REF_NOT_BASE64"
    # 「没给」与「给了一个空的」是两种不同的调用方错误，必须报不同的码
    body = _clone_body(ref={"audioBase64": base64.b64encode(b"").decode(), "text": "x"})
    assert _err_code(body) == "REF_EMPTY"
    big = base64.b64encode(b"\x00" * (sidecar.MAX_REF_BYTES + 1)).decode()
    assert _err_code(_clone_body(ref={"audioBase64": big, "text": "x"})) == "REF_TOO_LARGE"


def test_clone_requires_ref_text_no_auto_transcribe() -> None:
    """参考文本是**音色定义的一部分**：不做自动转写（那会让音色随 ASR 模型漂移）。"""
    assert _err_code(_clone_body(ref={"audioBase64": base64.b64encode(_WAV).decode()})) == (
        "REF_TEXT_REQUIRED"
    )
    body = _clone_body(ref={"audioBase64": base64.b64encode(_WAV).decode(), "text": "  "})
    assert _err_code(body) == "REF_TEXT_REQUIRED"


def test_clone_rejects_instruct() -> None:
    """静默忽略比报错坏得多：调用方会以为 instruct 生效了。"""
    assert _err_code(_clone_body(instruct="male, middle-aged")) == "INSTRUCT_IN_CLONE"


# ---------------------------------------------------------------------------
# 跨进程契约对账：客户端造体 → 服务端校验
# ---------------------------------------------------------------------------


def _client(tmp_path: Path):
    from app.audio.tts_omnivoice import OmniVoiceTTSClient

    wav = tmp_path / "male-en.wav"
    wav.write_bytes(_WAV)
    (tmp_path / "VOICES.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "personaId": "male",
                        "lang": "en",
                        "file": "male-en.wav",
                        "sha256": hashlib.sha256(_WAV).hexdigest(),
                        "refText": _REF_TEXT,
                        "instruct": "male, middle-aged, american accent",
                        "seed": 42,
                        "wordOfMouth": "英文男声 · The Anchor",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return OmniVoiceTTSClient(endpoint="http://127.0.0.1:8765", refs_dir=str(tmp_path))


def test_client_payload_passes_sidecar_validation(tmp_path) -> None:
    """**本文件最重要的一条**：两端用同一份请求体对账，漂移即红。"""
    client = _client(tmp_path)
    payload = client.build_request("Good evening, everyone.", voice="anchor-en")

    req = sidecar.validate(payload)  # 不抛 = 契约一致
    assert req["mode"] == "clone"
    assert req["language"] == "en"
    assert req["ref"]["audio"] == _WAV  # 参考件字节原样送达（不重编码）
    assert req["ref"]["text"] == _REF_TEXT
    assert req["seed"] == 42
    assert req["format"] == "wav"


def test_client_payload_has_no_instruct(tmp_path) -> None:
    """clone 模式下 instruct 会被服务端 400 —— 客户端必须不发。"""
    payload = _client(tmp_path).build_request("hi")
    assert "instruct" not in payload
    assert "instruct" not in payload["ref"]


def test_client_seed_override_survives_validation(tmp_path) -> None:
    from app.audio.tts_omnivoice import OmniVoiceTTSClient

    wav_dir = tmp_path
    _client(wav_dir)  # 建好参考件目录
    client = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(wav_dir), seed=7)
    assert sidecar.validate(client.build_request("hi"))["seed"] == 7
