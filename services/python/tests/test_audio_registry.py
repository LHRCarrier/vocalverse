"""ASR/TTS provider 注册表测试（2026-09 可插拔重构核心）。

覆盖：内置引擎登记齐全 / 别名解析 / auto 链按 priority 且**剔除 Fake** /
显式 strict 不可用 → ProviderUnavailable / 显式非 strict → 返回实例交调用方降级 /
未知名回退 auto（配置漂移不炸服务）/ tts_format 兜底 / health_summary 形状。
"""

from __future__ import annotations

import pytest
from app.audio import providers, registry
from app.audio.registry import ASR, TTS, ProviderSpec, ProviderUnavailable


class _Client:
    """可配置可用性的最小客户端（不继承 ABC —— 注册表只关心属性/方法）。"""

    def __init__(self, provider_id: str, *, ok: bool = True, reason: str = "") -> None:
        self.provider_id = provider_id
        self.media_type = "audio/wav"
        self.ext = "wav"
        self._ok = ok
        self._reason = reason

    def is_available(self) -> tuple[bool, str]:
        return self._ok, self._reason


@pytest.fixture()
def clean_registry(monkeypatch):
    """隔离注册表：每个用例从空表开始（注册是全局副作用，必须还原）。"""
    monkeypatch.setattr(registry, "_REGISTRY", {})
    return registry


def _spec(name: str, *, ok: bool = True, priority: int = 10, auto: bool = True, aliases=()):
    return ProviderSpec(
        name=name,
        kind=TTS,
        label=name,
        factory=lambda _s: _Client(name, ok=ok, reason="fake reason"),
        priority=priority,
        in_auto_chain=auto,
        aliases=aliases,
        ext="wav",
        media_type="audio/wav",
    )


# ---------------------------------------------------------------------------
# 内置引擎登记
# ---------------------------------------------------------------------------


def test_builtin_providers_registered() -> None:
    providers.ensure_registered()
    names = set(registry.registered())
    assert {"asr:whisper", "asr:sherpa", "asr:fake"} <= names
    assert {"tts:edge", "tts:azure", "tts:kitten", "tts:omnivoice", "tts:fake"} <= names


def test_fake_is_not_in_auto_chain() -> None:
    """生产 auto 绝不允许静默落到打桩引擎（审计 V2.0 最危险的静默失败）。"""
    providers.ensure_registered()
    assert "fake" not in {s.name for s in registry.auto_chain(ASR)}
    assert "fake" not in {s.name for s in registry.auto_chain(TTS)}
    assert "fake" in {s.name for s in registry.catalog(TTS)}  # 显式指名仍可用


def test_auto_chain_ordered_by_priority() -> None:
    providers.ensure_registered()
    tts = [s.name for s in registry.auto_chain(TTS)]
    # 本地优先：克隆音色 → 本地 ONNX → 云端兜底 → 未接线占位
    assert tts[0] == "omnivoice"
    assert tts.index("omnivoice") < tts.index("kitten") < tts.index("edge") < tts.index("azure")
    assert tts[-1] == "azure"


def test_whisper_and_sherpa_are_local_asr() -> None:
    providers.ensure_registered()
    assert [s.name for s in registry.auto_chain(ASR)] == ["whisper", "sherpa"]
    assert all(s.is_local for s in registry.auto_chain(ASR))


# ---------------------------------------------------------------------------
# 别名 / 格式
# ---------------------------------------------------------------------------


def test_alias_resolves_to_same_spec(clean_registry) -> None:
    registry.register(_spec("kitten", aliases=("kittentts", "kitten-tts")))
    assert registry.get(TTS, "kittentts") is registry.get(TTS, "kitten")
    assert registry.get(TTS, "KITTEN-TTS") is registry.get(TTS, "kitten")
    assert registry.get(TTS, "nope") is None


def test_tts_format_prefers_registered_spec(clean_registry) -> None:
    registry.register(_spec("myeng"))
    assert registry.tts_format("myeng") == ("wav", "audio/wav")


def test_tts_format_falls_back_for_unknown_provider(clean_registry) -> None:
    """未注册名字必须给可读兜底，避免 None 传播到缓存路径拼装。"""
    assert registry.tts_format("edge") == ("mp3", "audio/mpeg")
    assert registry.tts_format("kitten") == ("wav", "audio/wav")
    assert registry.tts_format("totally-unknown") == ("mp3", "audio/mpeg")
    assert registry.tts_format("") == ("mp3", "audio/mpeg")


# ---------------------------------------------------------------------------
# resolve：auto / 显式 / strict / 未知
# ---------------------------------------------------------------------------


def test_resolve_auto_picks_first_available(clean_registry) -> None:
    registry.register(_spec("a-down", ok=False, priority=10))
    registry.register(_spec("b-up", ok=True, priority=20))
    res = registry.resolve(TTS, object(), "auto")
    assert res.provider == "b-up"
    assert res.degraded is True  # 降级留痕（供 /readyz 与管理端解释）
    assert any("a-down" in n for n in res.notes)


def test_resolve_auto_raises_when_all_down(clean_registry) -> None:
    registry.register(_spec("only", ok=False))
    with pytest.raises(ProviderUnavailable) as ei:
        registry.resolve(TTS, object(), "auto")
    assert "fake reason" in str(ei.value)  # 可读原因必须带上


def test_resolve_auto_ignores_non_auto_providers(clean_registry) -> None:
    registry.register(_spec("manual-only", ok=True, auto=False))
    with pytest.raises(ProviderUnavailable):
        registry.resolve(TTS, object(), "auto")


def test_resolve_explicit_returns_even_if_unavailable(clean_registry) -> None:
    """非 strict：显式选中但不可用 → 返回实例，由调用方查 is_available 后降级。

    （保留 Azure 未接线占位客户端的既有语义，docs/44 P0-C。）
    """
    registry.register(_spec("azure-like", ok=False))
    res = registry.resolve(TTS, object(), "azure-like")
    assert res.provider == "azure-like"
    assert res.client.is_available() == (False, "fake reason")


def test_resolve_explicit_strict_raises(clean_registry) -> None:
    registry.register(_spec("kitten-like", ok=False))
    with pytest.raises(ProviderUnavailable) as ei:
        registry.resolve(TTS, object(), "kitten-like", strict=True)
    assert ei.value.kind == TTS and ei.value.name == "kitten-like"


def test_resolve_strict_when_explicit_flag(clean_registry) -> None:
    """spec 自带 strict_when_explicit：本地引擎显式选中但没条件 → 不静默换云引擎。"""
    registry.register(
        ProviderSpec(
            name="local-only",
            kind=TTS,
            label="x",
            factory=lambda _s: _Client("local-only", ok=False, reason="模型目录为空"),
            strict_when_explicit=True,
        )
    )
    with pytest.raises(ProviderUnavailable):
        registry.resolve(TTS, object(), "local-only")


def test_resolve_unknown_name_falls_back_to_auto(clean_registry) -> None:
    """配置漂移兜底：写错 provider 名不应 500（docs/46 B-7）。"""
    registry.register(_spec("edge-like", ok=True, priority=10))
    res = registry.resolve(TTS, object(), "typo-name")
    assert res.provider == "edge-like"
    assert res.requested == "auto"
    assert any("unknown provider" in n for n in res.notes)


def test_resolve_empty_requested_uses_default(clean_registry) -> None:
    registry.register(_spec("edge-like", ok=True, priority=10))
    assert registry.resolve(TTS, object(), "").provider == "edge-like"
    assert registry.resolve(TTS, object(), None, default="edge-like").provider == "edge-like"


def test_resolve_factory_override_short_circuits(clean_registry) -> None:
    """测试/预览注入点：绕过注册表直接产出实例。"""
    res = registry.resolve(TTS, object(), "edge", factory_override=lambda name: _Client(name))
    assert res.client.provider_id == "edge"


def test_resolve_probe_exception_counts_as_unavailable(clean_registry) -> None:
    class _Boom:
        def is_available(self):
            raise RuntimeError("probe exploded")

    registry.register(
        ProviderSpec(name="boom", kind=TTS, label="x", factory=lambda _s: _Boom(), priority=1)
    )
    registry.register(_spec("ok", priority=2))
    assert registry.resolve(TTS, object(), "auto").provider == "ok"


# ---------------------------------------------------------------------------
# health_summary
# ---------------------------------------------------------------------------


def test_health_summary_reports_every_provider(clean_registry) -> None:
    registry.register(_spec("a", ok=True, priority=1))
    registry.register(_spec("b", ok=False, priority=2, auto=False))
    rows = {r["provider"]: r for r in registry.health_summary(TTS, object())}
    assert rows["a"]["available"] is True
    assert rows["b"]["available"] is False and rows["b"]["reason"] == "fake reason"
    assert set(rows) == {"a", "b"}
