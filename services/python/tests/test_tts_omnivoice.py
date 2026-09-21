"""OmniVoice 参考件音色引擎测试（`app/audio/tts_omnivoice.py`）。

覆盖两件**不能出错**的事（上游纪律，抄错就静默换嗓子）：
1. 参考件 sha256 校验 —— 字节就是音色的身份，对不上必须**拒合成**；
2. clone 请求体形状 —— `mode="clone"` + `ref{audioBase64,text}` + `seed`，
   **不下发 instruct**（上游对 clone+instruct 直接 400）、**参考文本来自清单**。
另覆盖 `is_available()` 的逐条可读原因与音色别名解析。
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from app.audio import tts_omnivoice as omni
from app.audio.tts_omnivoice import (
    MANIFEST_NAME,
    OmniVoiceTTSClient,
    normalize_voice,
    read_manifest,
    supported_voices,
)

_REF_TEXT = "Good evening. Topping our broadcast tonight."
_WAV = b"RIFF____fake_reference_wav____"


@pytest.fixture(autouse=True)
def _clear_health_cache():
    """连通性探测有 10s TTL 缓存：用例间必须隔离，否则结论互相污染。"""
    omni.reset_health_cache()
    yield
    omni.reset_health_cache()


@pytest.fixture()
def sidecar_up(monkeypatch):
    """把「边车在线」作为测试前提（真实探测见 test_unavailable_when_sidecar_down）。"""
    monkeypatch.setattr(omni, "_probe_health", lambda *a, **kw: True)


def _write_refs(tmp_path: Path, *, sha: str | None = None, voice_id: str = "male-en") -> Path:
    (tmp_path / "male-en.wav").write_bytes(_WAV)
    manifest = {
        "engine": "omnivoice",
        "voices": [
            {
                "personaId": "male",
                "lang": "en",
                "file": "male-en.wav",
                "sha256": sha if sha is not None else hashlib.sha256(_WAV).hexdigest(),
                "bytes": len(_WAV),
                "refText": _REF_TEXT,
                "instruct": "male, middle-aged, american accent",
                "seed": 42,
                "wordOfMouth": "英文男声 · The Anchor",
            }
        ],
    }
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# 清单与音色解析
# ---------------------------------------------------------------------------


def test_read_manifest_parses_rows(tmp_path) -> None:
    rows = read_manifest(str(_write_refs(tmp_path)))
    assert len(rows) == 1
    row = rows[0]
    assert row.voice_id == "anchor-en"  # personaId-lang → 规范 id
    assert row.ref_text == _REF_TEXT
    assert row.seed == 42
    assert row.lang == "en"


def test_read_manifest_missing_or_broken_is_empty(tmp_path) -> None:
    """清单坏了按「无音色」处理（绝不抛）——由 is_available 报可读原因。"""
    assert read_manifest(str(tmp_path)) == []
    (tmp_path / MANIFEST_NAME).write_text("{not json", encoding="utf-8")
    assert read_manifest(str(tmp_path)) == []


def test_manifest_row_without_reftext_is_skipped(tmp_path) -> None:
    (tmp_path / MANIFEST_NAME).write_text(
        json.dumps({"voices": [{"personaId": "male", "lang": "en", "file": "a.wav"}]}),
        encoding="utf-8",
    )
    assert read_manifest(str(tmp_path)) == []  # 参考文本必须给死，缺了就不算一条音色


def test_voice_alias_normalization() -> None:
    assert normalize_voice("The-Anchor") == "anchor-en"
    assert normalize_voice("podcaster") == "podcaster-en"
    assert normalize_voice("male-en") == "anchor-en"
    assert normalize_voice("anchor-en") == "anchor-en"


def test_supported_voices_returns_api_shape(tmp_path) -> None:
    settings = SimpleNamespace(voice_refs_dir=str(_write_refs(tmp_path)))
    rows = supported_voices(settings)
    assert [r["id"] for r in rows] == ["anchor-en"]
    assert rows[0]["engine"] == "omnivoice"
    assert rows[0]["langs"] == ["en"]
    assert set(rows[0]) == {"id", "label", "engine", "langs"}


def test_supported_voices_empty_without_dir() -> None:
    assert supported_voices(SimpleNamespace(voice_refs_dir="")) == []


# ---------------------------------------------------------------------------
# is_available：逐条可读原因
# ---------------------------------------------------------------------------


def test_unavailable_without_endpoint(tmp_path) -> None:
    c = OmniVoiceTTSClient(endpoint="", refs_dir=str(_write_refs(tmp_path)))
    ok, reason = c.is_available()
    assert ok is False and "ENDPOINT" in reason


def test_unavailable_without_refs_dir() -> None:
    ok, reason = OmniVoiceTTSClient(endpoint="http://x", refs_dir="").is_available()
    assert ok is False and "VOICE_REFS_DIR" in reason


def test_unavailable_without_manifest(tmp_path) -> None:
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(tmp_path))
    ok, reason = c.is_available()
    assert ok is False and "清单" in reason


def test_available_when_endpoint_refs_and_sidecar_ready(tmp_path, sidecar_up) -> None:
    c = OmniVoiceTTSClient(endpoint="http://x/", refs_dir=str(_write_refs(tmp_path)))
    assert c.is_available() == (True, "ready")
    assert c._endpoint == "http://x"  # 尾斜杠被规整，避免拼出 //synthesize


def test_unavailable_when_sidecar_down(tmp_path, monkeypatch) -> None:
    """参考件齐、边车没起 → 必须判不可用（否则 auto 选中它，每次合成都失败）。"""
    monkeypatch.setattr(omni, "_probe_health", lambda *a, **kw: False)
    c = OmniVoiceTTSClient(endpoint="http://127.0.0.1:9", refs_dir=str(_write_refs(tmp_path)))
    ok, reason = c.is_available()
    assert ok is False and "边车未就绪" in reason


def test_probe_health_is_false_for_dead_endpoint() -> None:
    """真实探测：连不上的地址必须返回 False 且不抛错（绝不炸 auto 链）。"""
    assert omni._probe_health("http://127.0.0.1:9", timeout_s=0.2) is False


def test_probe_health_caches_result(monkeypatch) -> None:
    """探测结果按 TTL 缓存：auto 链每次解析都会问，不能每请求打一次网络。"""
    calls: list[str] = []

    class _Resp:
        status_code = 200

    def _fake_get(url, timeout=None):  # noqa: ARG001
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(httpx, "get", _fake_get)
    omni.reset_health_cache()
    assert omni._probe_health("http://cached") is True
    assert omni._probe_health("http://cached") is True
    assert calls == ["http://cached/health"]  # 第二次命中缓存


# ---------------------------------------------------------------------------
# sha256 校验：静默换嗓子守卫
# ---------------------------------------------------------------------------


def test_ensure_ready_rejects_tampered_reference(tmp_path) -> None:
    refs = _write_refs(tmp_path, sha="0" * 64)  # 清单里的 sha 与文件不符
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(refs))
    with pytest.raises(RuntimeError) as ei:
        c.ensure_ready()
    assert "参考件校验不过" in str(ei.value)


def test_ensure_ready_accepts_matching_sha(tmp_path) -> None:
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(_write_refs(tmp_path)))
    c.ensure_ready()  # 不抛
    c.unload()
    assert c.voices()  # unload 后可重新加载


async def test_synthesize_rejects_tampered_reference(tmp_path) -> None:
    refs = _write_refs(tmp_path, sha="0" * 64)
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(refs))
    with pytest.raises(RuntimeError):
        await c.synthesize("hello", voice="anchor-en")


# ---------------------------------------------------------------------------
# synthesize：请求体形状
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"RIFFWAV", text: str = "") -> None:
        self.status_code = status_code
        self.content = content
        self.text = text


class _FakeAsyncClient:
    last: tuple[str, dict] | None = None
    response = _FakeResponse()

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_exc) -> bool:
        return False

    async def post(self, url: str, json: dict | None = None) -> _FakeResponse:
        _FakeAsyncClient.last = (url, json or {})
        return _FakeAsyncClient.response


@pytest.fixture()
def fake_httpx(monkeypatch):
    _FakeAsyncClient.last = None
    _FakeAsyncClient.response = _FakeResponse()
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


async def test_synthesize_sends_clone_payload_without_instruct(tmp_path, fake_httpx) -> None:
    refs = _write_refs(tmp_path)
    c = OmniVoiceTTSClient(endpoint="http://127.0.0.1:8765", refs_dir=str(refs))
    audio = await c.synthesize("Hello there.", voice="anchor-en")

    assert audio == b"RIFFWAV"
    url, body = fake_httpx.last
    assert url == "http://127.0.0.1:8765/synthesize"
    assert body["mode"] == "clone"
    assert body["language"] == "en"
    assert body["format"] == "wav"
    assert body["seed"] == 42  # 清单里的 seed
    assert "instruct" not in body  # clone + instruct 会被上游 400
    # 参考件走 base64 进 JSON（不传路径：传路径会引入「文件被换掉」的静默变声）
    assert base64.b64decode(body["ref"]["audioBase64"]) == _WAV
    assert body["ref"]["text"] == _REF_TEXT  # 参考文本来自清单，禁止自动转写


async def test_synthesize_honours_seed_override(tmp_path, fake_httpx) -> None:
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(_write_refs(tmp_path)), seed=7)
    await c.synthesize("hi", voice="anchor-en")
    assert fake_httpx.last[1]["seed"] == 7


async def test_synthesize_unknown_voice_falls_back_to_default(tmp_path, fake_httpx) -> None:
    """前端可能传来 edge 音色名（如 en-US-JennyNeural）→ 回落到默认参考件，不报错。"""
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(_write_refs(tmp_path)))
    await c.synthesize("hi", voice="en-US-JennyNeural")
    assert fake_httpx.last[1]["ref"]["text"] == _REF_TEXT


async def test_synthesize_raises_readable_on_http_error(tmp_path, fake_httpx) -> None:
    fake_httpx.response = _FakeResponse(status_code=400, text='{"error":{"code":"BAD_MODE"}}')
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(_write_refs(tmp_path)))
    with pytest.raises(RuntimeError) as ei:
        await c.synthesize("hi")
    assert "BAD_MODE" in str(ei.value)


async def test_synthesize_raises_readable_on_empty_audio(tmp_path, fake_httpx) -> None:
    fake_httpx.response = _FakeResponse(content=b"")
    c = OmniVoiceTTSClient(endpoint="http://x", refs_dir=str(_write_refs(tmp_path)))
    with pytest.raises(RuntimeError) as ei:
        await c.synthesize("hi")
    assert "空音频" in str(ei.value)


async def test_synthesize_raises_readable_when_sidecar_down(tmp_path, monkeypatch) -> None:
    class _Down:
        def __init__(self, **_kw) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc) -> bool:
            return False

        async def post(self, *_a, **_kw):
            raise ConnectionError("refused")

    monkeypatch.setattr(httpx, "AsyncClient", _Down)
    c = OmniVoiceTTSClient(endpoint="http://127.0.0.1:9", refs_dir=str(_write_refs(tmp_path)))
    with pytest.raises(RuntimeError) as ei:
        await c.synthesize("hi")
    assert "边车不可达" in str(ei.value)


# ---------------------------------------------------------------------------
# 默认 auto 档的安全性（本引擎在 auto 链首位，必须能自己让位）
# ---------------------------------------------------------------------------


def _auto_settings(refs_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        testing=False,
        tts_provider="auto",
        tts_voice="en-US-JennyNeural",
        tts_rate="+0%",
        voice_models_dir="",
        voice_refs_dir=str(refs_dir),
        tts_omnivoice_endpoint="http://127.0.0.1:8765",
    )


def test_auto_falls_back_to_edge_when_sidecar_down(tmp_path, monkeypatch) -> None:
    """**默认档位的安全底线**：参考件配好但边车没起 → 落到 edge，而不是选中后每次都失败。"""
    from app.audio.base import resolve_tts_client

    monkeypatch.setattr(omni, "_probe_health", lambda *a, **kw: False)
    assert resolve_tts_client(settings=_auto_settings(_write_refs(tmp_path))).provider_id == "edge"


def test_auto_picks_omnivoice_when_sidecar_up(tmp_path, monkeypatch) -> None:
    from app.audio.base import resolve_tts_client

    monkeypatch.setattr(omni, "_probe_health", lambda *a, **kw: True)
    client = resolve_tts_client(settings=_auto_settings(_write_refs(tmp_path)))
    assert client.provider_id == "omnivoice"
    assert client.media_type == "audio/wav"  # 容器元数据随引擎走
