"""事实表纯函数：规范化 key（两级白名单）/ 提取结果宽容解析 / upsert 裁决矩阵。

迁移自 ai4u（fact-key.util / parse-fact-ops.util / adjudicate-upsert.util，P2-24/25/26/27/35/42）。
纯函数可单测（红线 9）：不触 DB、不依赖框架。

key 语法（P2-24：LLM 不选 id，只填 key；系统按 key upsert）：
    3 段 ``{domain}.{entity}.{property}`` —— pc.洛可.hp / rel.莉亚.attitude / quest.戒指.status
    2 段 ``{domain}.{property}``          —— scene.current（场景是 campaign 级单值，无实体）
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Literal

from app.trpg.constants import (
    DOMAIN_PROPERTIES,
    ENTITY_NAME_MAX,
    FACT_VALUE_MAX_LEN,
    KEY_LEN_MAX,
    STATE_DOMAINS,
)

Modality = Literal["fact", "claim", "rumor"]
_MODALITIES: tuple[str, ...] = ("fact", "claim", "rumor")


@dataclass(frozen=True)
class ParsedKey:
    domain: str
    entity: str | None  # 2 段 key（scene.current）为 None
    property: str


def parse_key(key: str) -> ParsedKey | None:
    """解析规范化 key；非法返回 None。"""
    if not isinstance(key, str):
        return None
    k = key.strip()
    if not k:
        return None
    parts = k.split(".")
    if len(parts) == 3:
        domain, entity, prop = parts
        if not domain or not entity or not prop:
            return None
        return ParsedKey(domain=domain, entity=entity, property=prop)
    if len(parts) == 2:
        domain, prop = parts
        if not domain or not prop:
            return None
        # 2 段 key 仅允许 scene 域（campaign 级单值；其余域 entity 不可省略）
        if domain != "scene":
            return None
        return ParsedKey(domain=domain, entity=None, property=prop)
    return None


def make_key(domain: str, entity: str | None, property: str) -> str | None:
    """构造规范化 key；参数非法返回 None（服务层生成系统 key 用）。"""
    raw = f"{domain}.{entity}.{property}" if entity else f"{domain}.{property}"
    parsed = parse_key(raw)
    if parsed is None:
        return None
    return f"{domain}.{entity}.{property}" if entity else f"{domain}.{property}"


KeyCheckReason = Literal[
    "malformed", "unknown-domain", "unknown-property", "unknown-entity", "entity-overlong"
]


@dataclass(frozen=True)
class KeyCheckResult:
    ok: bool
    reason: KeyCheckReason | None = None
    parsed: ParsedKey | None = None


def check_key_whitelist(key: str, known_entities: set[str]) -> KeyCheckResult:
    """两级白名单校验（域 → 属性 → 实体注册表）；pending 实体由调用方并入 known_entities。"""
    parsed = parse_key(key)
    if parsed is None:
        return KeyCheckResult(ok=False, reason="malformed")
    props = DOMAIN_PROPERTIES.get(parsed.domain)
    if props is None:
        return KeyCheckResult(ok=False, reason="unknown-domain", parsed=parsed)
    if parsed.property not in props:
        return KeyCheckResult(ok=False, reason="unknown-property", parsed=parsed)
    if parsed.entity is not None:
        if len(parsed.entity) > ENTITY_NAME_MAX:
            return KeyCheckResult(ok=False, reason="entity-overlong", parsed=parsed)
        if parsed.entity not in known_entities:
            return KeyCheckResult(ok=False, reason="unknown-entity", parsed=parsed)
    return KeyCheckResult(ok=True, parsed=parsed)


@dataclass
class FactOp:
    """提取/直写的单条操作（写者：llm=模型提取 / system=系统直写）。"""

    op: Literal["create", "update"]
    key: str
    value: str
    modality: Modality | None = None
    speaker: str | None = None
    importance: float | None = None
    writer: Literal["llm", "system"] = "llm"


def parse_fact_ops(content: str) -> list[FactOp]:
    """宽容解析模型输出为 FactOp 列表；坏输入/空内容返回 []（失败显式降级，不抛错）。"""
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    ops: list[FactOp] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()[:KEY_LEN_MAX]
        value = str(item.get("value") or "").strip()[:FACT_VALUE_MAX_LEN]
        if not key or not value:
            continue
        modality: Modality | None = None
        if item.get("modality") in _MODALITIES:
            modality = item["modality"]  # type: ignore[assignment]
        speaker = None
        raw_speaker = item.get("speaker")
        if isinstance(raw_speaker, str) and raw_speaker.strip():
            speaker = raw_speaker.strip()[:ENTITY_NAME_MAX]
        importance = None
        if isinstance(item.get("importance"), (int, float)) and not isinstance(
            item.get("importance"), bool
        ):
            importance = min(1.0, max(0.0, float(item["importance"])))
        ops.append(
            FactOp(
                op="update" if item.get("op") == "update" else "create",
                key=key,
                value=value,
                modality=modality,
                speaker=speaker,
                importance=importance,
            )
        )
    return ops


@dataclass
class FactRowLike:
    """既有事实行的最小形态（服务层从 DB 行映射）。"""

    key: str
    value: str
    id: int | None = None
    kind: str | None = None
    modality: str | None = None
    speaker: str | None = None
    importance: float | None = None
    user_touched_at: object | None = None
    user_deleted_at: object | None = None
    version: int | None = None


RejectReason = Literal[
    "malformed",
    "unknown-domain",
    "unknown-property",
    "unknown-entity",
    "entity-overlong",
    "llm-state",
    "user-touched",
    "tombstone",
]


@dataclass
class Adjudication:
    """裁决结果：create / update / reject（写权限矩阵，P2-26）。"""

    action: Literal["create", "update", "reject"]
    op: FactOp | None = None
    entity: str | None = None
    register_entity: bool = False
    existing: FactRowLike | None = None
    reason: RejectReason | None = None
    key: str = ""


def adjudicate_upsert(
    op: FactOp,
    existing: list[FactRowLike],
    known_entities: set[str],
    tombstone_keys: set[str] | None = None,
) -> Adjudication:
    """upsert 裁决矩阵（P2-24/26/27/35/42）：

    - key 结构非法 → reject malformed；
    - 域/属性白名单外 → reject unknown-domain / unknown-property；
    - LLM 写 State 域 → reject llm-state（红线 1）；
    - 墓碑 key（用户已删）→ reject tombstone（防提取复活）；
    - 用户碰过的行 → reject user-touched（user > rules > llm）；
    - key 命中既有无墓碑行 → update；
    - 未命中 → create（未知实体走注册，P2-42 懒确认）。
    """
    parsed = parse_key(op.key)
    if parsed is None:
        return Adjudication(action="reject", reason="malformed", key=op.key)
    props = DOMAIN_PROPERTIES.get(parsed.domain)
    if props is None:
        return Adjudication(action="reject", reason="unknown-domain", key=op.key)
    if parsed.property not in props:
        return Adjudication(action="reject", reason="unknown-property", key=op.key)

    writer = op.writer or "llm"
    if writer == "llm" and parsed.domain in STATE_DOMAINS:
        return Adjudication(action="reject", reason="llm-state", key=op.key)

    tombstones = tombstone_keys or set()
    found = next((e for e in existing if e.key == op.key), None)
    if op.key in tombstones or (found is not None and found.user_deleted_at is not None):
        return Adjudication(action="reject", reason="tombstone", key=op.key)

    if found is not None and found.user_touched_at is not None:
        return Adjudication(action="reject", reason="user-touched", key=op.key)

    if found is not None:
        return Adjudication(action="update", op=op, existing=found, key=op.key)

    register = parsed.entity is not None and parsed.entity not in known_entities
    return Adjudication(
        action="create",
        op=op,
        entity=parsed.entity,
        register_entity=register,
        key=op.key,
    )
