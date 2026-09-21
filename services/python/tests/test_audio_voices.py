"""音色目录测试（`app/audio/voices.py`）。

重构前音色清单硬编码在路由里（`reading.py:list_edge_voices`）+ 前端又写一份默认音色；
现在收敛到 `app/audio/voices.py` 单一真源。本测试锁住：
edge 清单**逐条不变**（下游 `/reading/voices` 契约与前端选择器都依赖它）、
本地引擎未就绪时**不暴露**其音色（避免用户选到发不出声的音色）、
`as_dict()` 形状与 `VoiceView` 契约一致。
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from app.audio.voices import DEFAULT_VOICE, EDGE_VOICES, VoiceSpec, list_voices


def _settings(tmp_path, **over):
    base = {
        "voice_models_dir": "",  # KittenTTS 未配置 → 不暴露
        "voice_refs_dir": "",  # OmniVoice 未配置 → 不暴露
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_edge_catalog_is_stable() -> None:
    """edge 清单是既有对外契约，逐条锁死（改这里必须同步前端选择器与契约快照）。"""
    assert [v.id for v in EDGE_VOICES] == [
        "en-US-JennyNeural",
        "en-US-AriaNeural",
        "en-US-GuyNeural",
        "en-GB-SoniaNeural",
        "en-GB-RyanNeural",
    ]
    assert all(v.engine == "edge" and v.is_local is False for v in EDGE_VOICES)


def test_default_voice_matches_edge_first() -> None:
    """默认音色单一真源：前端不再各写一份字符串。"""
    assert EDGE_VOICES[0].id == DEFAULT_VOICE


def test_list_voices_only_edge_when_no_local_engine(tmp_path) -> None:
    ids = [v.id for v in list_voices(_settings(tmp_path))]
    assert ids == [v.id for v in EDGE_VOICES]


def test_local_engines_hidden_when_not_ready(tmp_path) -> None:
    """模型目录/参考件目录缺失 → 本地音色**不出现**（用户不会选到哑的音色）。"""
    ids = [v.id for v in list_voices(_settings(tmp_path))]
    assert not any(i in ids for i in ("Jasper", "anchor-en", "podcaster-en"))


def test_omnivoice_voices_exposed_when_manifest_present(tmp_path) -> None:
    import hashlib

    wav = b"RIFF____ref____"
    (tmp_path / "male-en.wav").write_bytes(wav)
    (tmp_path / "VOICES.json").write_text(
        json.dumps(
            {
                "voices": [
                    {
                        "personaId": "male",
                        "lang": "en",
                        "file": "male-en.wav",
                        "sha256": hashlib.sha256(wav).hexdigest(),
                        "refText": "Good evening.",
                        "instruct": "male",
                        "seed": 42,
                        "wordOfMouth": "英文男声 · The Anchor",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    voices = list_voices(_settings(tmp_path, voice_refs_dir=str(tmp_path)))
    ids = [v.id for v in voices]
    assert "anchor-en" in ids
    spec = next(v for v in voices if v.id == "anchor-en")
    assert spec.engine == "omnivoice" and spec.is_local is True
    assert spec.langs == ("en",)


def test_as_dict_matches_voiceview_contract() -> None:
    """`VoiceView{id,label,engine,langs}` —— 多字段会让 OpenAPI 契约快照漂移。"""
    payload = VoiceSpec("x", "X · 女声", "edge", ("en-US",)).as_dict()
    assert set(payload) == {"id", "label", "engine", "langs"}
    assert payload["langs"] == ["en-US"]  # list（pydantic 友好），不是 tuple


def test_list_voices_dedupes_by_id(tmp_path) -> None:
    voices = list_voices(_settings(tmp_path))
    ids = [v.id for v in voices]
    assert len(ids) == len(set(ids))
