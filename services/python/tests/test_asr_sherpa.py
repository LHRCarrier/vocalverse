"""sherpa-onnx 本地 ASR 引擎测试（`app/audio/asr_sherpa.py`）。

sherpa-onnx 是**可选依赖**（`uv sync --extra local-asr`），CI 与多数开发机不装，
因此这里只测**不依赖它**的部分：模型文件清单校验（纯函数）、未配置/未装时
`is_available()` 的可读原因与「绝不抛错」、以及注册表登记。
"""

from __future__ import annotations

from app.audio import providers, registry
from app.audio.asr_sherpa import (
    _REQUIRED_FILES,
    SherpaOnnxASRClient,
    missing_model_files,
)

# ---------------------------------------------------------------------------
# 模型文件清单（纯函数）
# ---------------------------------------------------------------------------


def test_missing_files_when_dir_empty() -> None:
    assert missing_model_files("", "sense_voice") == list(_REQUIRED_FILES["sense_voice"])
    assert set(missing_model_files("", "transducer")) == set(_REQUIRED_FILES["transducer"])


def test_missing_files_when_dir_absent(tmp_path) -> None:
    assert missing_model_files(str(tmp_path / "nope"), "sense_voice")


def test_missing_files_all_present(tmp_path) -> None:
    for name in _REQUIRED_FILES["sense_voice"]:
        (tmp_path / name).write_bytes(b"x")
    assert missing_model_files(str(tmp_path), "sense_voice") == []


def test_missing_files_reports_only_absent(tmp_path) -> None:
    (tmp_path / "model.onnx").write_bytes(b"x")
    assert missing_model_files(str(tmp_path), "sense_voice") == ["tokens.txt"]


def test_unknown_model_type_falls_back_to_sense_voice() -> None:
    assert missing_model_files("", "no-such-type") == list(_REQUIRED_FILES["sense_voice"])


# ---------------------------------------------------------------------------
# is_available：可读原因，绝不抛
# ---------------------------------------------------------------------------


def test_unavailable_without_model_dir() -> None:
    ok, reason = SherpaOnnxASRClient(model_dir="").is_available()
    assert ok is False
    assert "SHERPA_MODEL_DIR" in reason


def test_unavailable_without_model_files(tmp_path) -> None:
    ok, reason = SherpaOnnxASRClient(model_dir=str(tmp_path)).is_available()
    assert ok is False
    # 未装依赖时报「未安装」，装了但缺文件时报「模型文件缺失」——两者都是可读原因
    assert ("未安装" in reason) or ("模型文件缺失" in reason)


def test_provider_identity() -> None:
    c = SherpaOnnxASRClient(model_dir="")
    assert c.provider_id == "sherpa"
    assert c.is_local is True
    c.unload()  # 幂等，不抛


def test_registered_in_auto_chain_with_no_word_timestamps_caveat() -> None:
    """sherpa 是本地第二引擎（whisper 之后），且**不产出词级时间戳**。"""
    providers.ensure_registered()
    chain = [s.name for s in registry.auto_chain(registry.ASR)]
    assert chain == ["whisper", "sherpa"]
    spec = registry.get(registry.ASR, "sherpa-onnx")
    assert spec is not None and spec.name == "sherpa" and spec.is_local is True
