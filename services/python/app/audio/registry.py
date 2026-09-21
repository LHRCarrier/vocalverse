"""ASR/TTS provider 注册表与选择链 —— 可插拔机制的唯一真源。

设计（docs/audit/ASR-TTS链路架构调研与重构方案.md §5）：

1. **注册表**：每个引擎在自身模块内声明一条 :class:`ProviderSpec`（名字 / 工厂 /
   是否本地 / 输出容器）并 ``register()``；:mod:`app.audio.providers` 负责一次性导入
   全部内置引擎模块（懒加载，纯 import，无副作用）。
2. **选择链**：``auto`` 按 ``priority`` 升序逐个 ``is_available()`` 探测，取第一个可用；
   显式名字直取；未知名回退 ``auto``（配置漂移兜底，docs/46 B-7）。
3. **降级策略**：``strict=True`` 时显式 provider 不可用 → 抛 :class:`ProviderUnavailable`
   （调用方映射 503）；``strict=False``（默认）返回实例，由调用方查 ``is_available()``
   决定降级——两种既有语义都被保留，不再各写一套。

**为什么要有这一层**：重构前仓库里有两套互不相识的 provider 选择实现
（``app/audio/base.get_tts_client`` 的 edge|azure 与 ``app/reading/tts_client`` 的
auto|edge|kitten），且引擎身份只能靠 ``isinstance(tts, KittenTTSClient)`` 反推
（``app/api/routes/reading_tts.py:_provider_of``）——新增第三个引擎必然漏判并把缓存
目录/扩展名/Content-Type 一起带错。注册表把「有哪些引擎、怎么选、怎么降级」收敛到一处。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("vocalverse.audio.registry")

#: 引擎种类
ASR = "asr"
TTS = "tts"

#: 未注册 provider 的输出容器兜底表（扩展名, media_type）。
#: 正常情况下 provider 由 :class:`ProviderSpec` 提供；此表只为「名字拼错/引擎未装」时的
#: 可读降级服务，避免 None 传播到缓存路径拼装。
_FALLBACK_FORMATS: dict[str, tuple[str, str]] = {
    "edge": ("mp3", "audio/mpeg"),
    "azure": ("mp3", "audio/mpeg"),
    "kitten": ("wav", "audio/wav"),
    "omnivoice": ("wav", "audio/wav"),
    "fake": ("mp3", "audio/mpeg"),
}
_DEFAULT_FORMAT = ("mp3", "audio/mpeg")


class ProviderUnavailable(RuntimeError):
    """显式指定的 provider 不可用（或 auto 链全军覆没）。

    调用方据此给出**可读降级**（HTTP 503 + 具体原因），而不是 500 或静默换引擎。
    """

    def __init__(self, kind: str, name: str, reason: str = "") -> None:
        self.kind = kind
        self.name = name
        self.reason = reason
        detail = f"{kind} provider {name!r} unavailable"
        super().__init__(f"{detail}: {reason}" if reason else detail)


@dataclass(frozen=True)
class ProviderSpec:
    """一个可插拔引擎的声明式描述。

    - ``name``：配置里写的 provider 名（``APP_ASR_PROVIDER`` / ``APP_TTS_PROVIDER``）；
    - ``factory``：``(settings) -> client``，**不做可用性判断**（判断交给 ``is_available``）；
    - ``priority``：``auto`` 链顺序，小者优先（本地引擎可给更小的值以优先离线）；
    - ``is_local``：是否本机推理（不依赖外网；用于运维面板/健康检查分组）；
    - ``media_type`` / ``ext``：TTS 输出容器（ASR 留空）。
    """

    name: str
    kind: str
    label: str
    factory: Callable[[Any], Any]
    priority: int = 100
    is_local: bool = False
    media_type: str = ""
    ext: str = ""
    langs: tuple[str, ...] = ("en",)
    #: 显式选中且不可用时是否**抛错**（True）还是返回实例交由调用方查 is_available（False）
    strict_when_explicit: bool = False
    #: 别名（配置里可写的其它等价名字；不进 ``auto`` 链，避免同一引擎出现两次）
    aliases: tuple[str, ...] = ()
    #: 是否参与 ``auto`` 降级链（Fake 等"仅在测试显式指名时使用"的引擎置 False）
    in_auto_chain: bool = True

    def build(self, settings: Any) -> Any:
        return self.factory(settings)


_REGISTRY: dict[tuple[str, str], ProviderSpec] = {}


def register(spec: ProviderSpec) -> ProviderSpec:
    """登记一个 provider（同 kind 下同名覆盖，便于测试打桩）。"""
    _REGISTRY[(spec.kind, spec.name)] = spec
    return spec


def get(kind: str, name: str) -> ProviderSpec | None:
    key = (name or "").strip().lower()
    spec = _REGISTRY.get((kind, key))
    if spec is not None:
        return spec
    # 别名解析（线性扫描；provider 数量恒为个位数）
    for (k, _), candidate in _REGISTRY.items():
        if k == kind and key in candidate.aliases:
            return candidate
    return None


def catalog(kind: str) -> list[ProviderSpec]:
    """某 kind 下全部已登记 provider，按 ``priority`` 升序（含不参与 auto 的）。"""
    items = [s for (k, _), s in _REGISTRY.items() if k == kind]
    return sorted(items, key=lambda s: (s.priority, s.name))


def auto_chain(kind: str) -> list[ProviderSpec]:
    """``auto`` 降级链：按 ``priority`` 升序、剔除声明不参与的引擎。

    注意 Fake 不在此链上——生产环境的 ``auto`` 绝不允许静默落到打桩引擎。
    """
    return [s for s in catalog(kind) if s.in_auto_chain]


def registered() -> list[str]:
    """全部已登记 provider 的 ``kind:name``（诊断/自检用）。"""
    return [f"{k}:{n}" for k, n in sorted(_REGISTRY)]


def tts_format(provider: str) -> tuple[str, str]:
    """provider → ``(ext, media_type)``；未知 provider 走兜底表（绝不抛错）。

    缓存按 provider 分目录并把扩展名/Content-Type 绑到实际引擎上（docs/46 B-3：
    本地 WAV 与云端 MP3 物理隔离，混标会把音频播坏）。
    """
    name = (provider or "").strip().lower()
    spec = get(TTS, name)
    if spec is not None and spec.ext:
        return spec.ext, spec.media_type or f"audio/{spec.ext}"
    return _FALLBACK_FORMATS.get(name, _DEFAULT_FORMAT)


@dataclass
class Resolution:
    """一次 provider 解析的结果（含「为什么是它」，便于日志/健康检查解释）。"""

    client: Any
    provider: str
    requested: str
    degraded: bool = False
    notes: list[str] = field(default_factory=list)


def resolve(
    kind: str,
    settings: Any,
    requested: str | None = None,
    *,
    default: str = "auto",
    strict: bool = False,
    factory_override: Callable[[str], Any] | None = None,
) -> Resolution:
    """按配置解析一个引擎实例。

    - ``requested`` 为空 → 用 ``default``（默认 ``auto``）；
    - ``auto`` → 按 priority 探测第一个 ``is_available()`` 为真的引擎；全不可用抛
      :class:`ProviderUnavailable`；
    - 显式名字 → 构造后返回；``strict=True``（或该 provider 声明
      ``strict_when_explicit``）且不可用 → 抛 :class:`ProviderUnavailable`；
    - 未知名 → 告警 + 回退 ``auto``（不 fail-fast，配置漂移不炸服务）。
    """
    name = (requested or "").strip().lower() or default
    notes: list[str] = []

    if factory_override is not None:
        # 测试/预览注入点：直接产出实例（provider 名沿用 requested）
        return Resolution(
            client=factory_override(name if name != "auto" else default),
            provider=name,
            requested=name,
        )

    if name != "auto":
        spec = get(kind, name)
        if spec is None:
            logger.warning(
                "%s provider %r 未注册（已注册：%s）→ 回退 auto",
                kind,
                name,
                ", ".join(s.name for s in catalog(kind)) or "(空)",
            )
            notes.append(f"unknown provider {name!r} → auto")
            name = "auto"
        else:
            client = spec.build(settings)
            if strict or spec.strict_when_explicit:
                ok, reason = _availability(client)
                if not ok:
                    raise ProviderUnavailable(kind, spec.name, reason)
            return Resolution(client=client, provider=spec.name, requested=name, notes=notes)

    specs = auto_chain(kind)
    if not specs:
        raise ProviderUnavailable(kind, "auto", "auto 链为空（providers 未导入？）")
    for spec in specs:
        client = spec.build(settings)
        ok, reason = _availability(client)
        if ok:
            degraded = spec is not specs[0]
            if degraded:
                notes.append(f"auto 降级到 {spec.name}")
            return Resolution(
                client=client,
                provider=spec.name,
                requested="auto",
                degraded=degraded,
                notes=notes,
            )
        notes.append(f"{spec.name}: {reason}")
        logger.info("%s auto: %s 不可用（%s）→ 试下一个", kind, spec.name, reason)
    raise ProviderUnavailable(kind, "auto", "; ".join(notes))


def _availability(client: Any) -> tuple[bool, str]:
    """引擎可用性探测；未实现 ``is_available`` 的老客户端视为可用（向后兼容）。"""
    probe = getattr(client, "is_available", None)
    if not callable(probe):
        return True, ""
    try:
        ok, reason = probe()
    except Exception as exc:  # noqa: BLE001 — 探测自身异常不应炸选择链
        return False, f"is_available 探测异常: {exc}"
    return bool(ok), str(reason or "")


def health_summary(kind: str, settings: Any) -> list[dict[str, Any]]:
    """健康检查用：逐个探测已注册 provider（只读，不缓存实例）。"""
    out: list[dict[str, Any]] = []
    for spec in catalog(kind):
        try:
            client = spec.build(settings)
            ok, reason = _availability(client)
        except Exception as exc:  # noqa: BLE001
            ok, reason = False, f"构造失败: {exc}"
        out.append(
            {
                "provider": spec.name,
                "label": spec.label,
                "available": ok,
                "reason": reason,
                "is_local": spec.is_local,
            }
        )
    return out


__all__ = [
    "ASR",
    "TTS",
    "ProviderSpec",
    "ProviderUnavailable",
    "Resolution",
    "auto_chain",
    "catalog",
    "get",
    "health_summary",
    "register",
    "registered",
    "resolve",
    "tts_format",
]
