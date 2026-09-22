"""状态快照组装纯函数（迁移自 ai4u build-state-snapshot，P2-30/31）。

注入视图，不落库。规则：
1. State 一行式：pc.* 当前值拼一行；scene.current 拼场景行；
2. 活动任务全量 + 完成/失败折叠为一行计数；
3. 线索：当前场景 + 未回收，按最后提及倒序，上限 SNAPSHOT_CLUE_MAX；
4. Fact 关系子集：rel.* 按 importance 降序，上限 SNAPSHOT_FACT_REL_MAX；
5. 行囊：item.* 聚合（P1-3 道具对 DM 可见），无道具行 → pc.*.inventory 字符串兜底，
   上限 SNAPSHOT_ITEM_MAX。
返回空串 = 无状态可注入（调用方跳过该 section）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.trpg.constants import (
    SNAPSHOT_CLUE_MAX,
    SNAPSHOT_FACT_REL_MAX,
    SNAPSHOT_ITEM_MAX,
    SNAPSHOT_NPC_MAX,
)
from app.trpg.facts import parse_key

_PROPERTY_LABEL: dict[str, str] = {
    "hp": "HP",
    "location": "位置",
    "inventory": "持有",
    "current": "场景",
    "attitude": "态度",
    "trust": "信任",
    "status": "状态",
}


@dataclass
class SnapshotFact:
    key: str
    kind: str
    value: str
    modality: str | None = None
    speaker: str | None = None
    importance: float | None = None


@dataclass
class SnapshotTask:
    title: str
    status: str


@dataclass
class SnapshotClue:
    title: str
    content: str | None = None
    scene: str | None = None
    found: bool | None = None
    recovered: bool | None = None
    last_mentioned_at: Any = None


@dataclass
class SnapshotInput:
    facts: list[SnapshotFact]
    tasks: list[SnapshotTask]
    clues: list[SnapshotClue]
    scene: str | None = None


def _time_of(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return 0.0


def build_state_snapshot(data: SnapshotInput) -> str:
    lines: list[str] = []

    # 1. State 一行式（pc.* + npc.* + scene.current；docs/56 §C：敌方 HP 进 DM 上下文）
    state_parts: list[str] = []
    npc_state: dict[str, list[str]] = {}
    scene_value = data.scene
    inventory_text: str | None = None
    item_props: dict[str, dict[str, str]] = {}
    item_order: list[str] = []
    for f in data.facts:
        parsed = parse_key(f.key)
        if parsed is None:
            continue
        # 道具（item.* 为 fact 域）：聚合为行囊行（P1-3），不散进 PC 状态行
        if parsed.domain == "item" and parsed.entity:
            if parsed.entity not in item_props:
                item_props[parsed.entity] = {}
                item_order.append(parsed.entity)
            item_props[parsed.entity][parsed.property] = f.value
            continue
        if f.kind != "state":
            continue
        if parsed.domain == "scene" and parsed.property == "current":
            scene_value = f.value
            continue
        if parsed.domain == "pc" and parsed.property == "inventory":
            inventory_text = f.value
            continue
        if parsed.domain == "npc" and parsed.entity:
            if parsed.entity not in npc_state and len(npc_state) >= SNAPSHOT_NPC_MAX:
                continue
            npc_state.setdefault(parsed.entity, []).append(
                f"{_PROPERTY_LABEL.get(parsed.property, parsed.property)} {f.value}"
            )
            continue
        state_parts.append(f"{_PROPERTY_LABEL.get(parsed.property, parsed.property)} {f.value}")
    if state_parts:
        lines.append(f"PC：{'｜'.join(state_parts)}")
    for entity_name, parts in npc_state.items():
        lines.append(f"{entity_name}：{'｜'.join(parts)}")
    if scene_value:
        lines.append(f"场景：{scene_value}")

    # 1b. 行囊（P1-3：DM 必须看得见道具，否则会当面否认玩家持有）
    bag_parts: list[str] = []
    for name in item_order:
        props = item_props[name]
        owner = (props.get("owner") or "").strip()
        if owner and not owner.startswith("pc."):
            continue  # NPC/商人持有 → 不进玩家行囊
        qty = (props.get("qty") or "").strip()
        label = f"{name}×{qty}" if qty else name
        effect = (props.get("effect") or "").strip()
        if effect:
            label = f"{label}（{effect}）"
        bag_parts.append(label)
        if len(bag_parts) >= SNAPSHOT_ITEM_MAX:
            break
    bag_text = "、".join(bag_parts) or (inventory_text or "")
    if bag_text:
        lines.append(f"行囊：{bag_text}")

    # 2. 任务：活动全量 + 完成/失败计数
    active = [t for t in data.tasks if t.status == "active"]
    done_count = sum(1 for t in data.tasks if t.status == "done")
    failed_count = sum(1 for t in data.tasks if t.status == "failed")
    if active:
        lines.append(f"任务：{'；'.join(f'[进行中] {t.title}' for t in active)}")
    folded = "，".join(
        x
        for x in (
            f"已完成 {done_count}" if done_count else "",
            f"失败 {failed_count}" if failed_count else "",
        )
        if x
    )
    if folded:
        lines.append(f"任务统计：{folded}")

    # 3. 线索：当前场景 + 未回收（按最后提及倒序 + 上限）
    clue_items = [
        c
        for c in data.clues
        if (c.found if c.found is not None else True)
        and not (c.recovered if c.recovered is not None else False)
        and (c.scene is None or c.scene == data.scene)
    ]
    clue_items.sort(key=lambda c: _time_of(c.last_mentioned_at), reverse=True)
    clue_items = clue_items[:SNAPSHOT_CLUE_MAX]
    if clue_items:
        lines.append(f"线索：{'；'.join(c.title for c in clue_items)}")

    # 4. Fact 关系子集（importance 降序 + 上限）
    rel_facts = []
    for f in data.facts:
        parsed = parse_key(f.key)
        if parsed is not None and parsed.domain == "rel":
            rel_facts.append((f, parsed))
    rel_facts.sort(
        key=lambda pair: pair[0].importance if pair[0].importance is not None else 0.5, reverse=True
    )
    rel_parts = []
    for f, parsed in rel_facts[:SNAPSHOT_FACT_REL_MAX]:
        claim_note = (
            f"（{f.speaker or '某人'} 声称）" if f.modality and f.modality != "fact" else ""
        )
        rel_parts.append(f"{parsed.entity}（{f.value}{claim_note}）")
    if rel_parts:
        lines.append(f"关系：{'｜'.join(rel_parts)}")

    if not lines:
        return ""
    return "【当前状态】\n" + "\n".join(lines)
