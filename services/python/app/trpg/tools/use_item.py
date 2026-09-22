"""use_item：道具使用（校验 → 扣减 → 效果写回；docs/56 §3、docs/55 §P4）。

- 条目来自事实表 ``item.{名}.*``（qty/owner/effect/consumable，工具唯一写路径）；
- 校验：道具不存在 → 「你没有」；qty≤0 → 「已经用完」（F&F 同款可校验资源）；
- consumable（缺省 true）使用后扣 1（扣到 0 不删条目，留痕与前端背包一致）；
- 效果数值约定由 :mod:`app.trpg.items` 解析（``hp+5``/「回复5」），写回复用
  :func:`app.trpg.state.apply_dice_delta`（与战斗同一条路径），文本不出现公式。
"""

from __future__ import annotations

import asyncio

from app.trpg import items as item_rules
from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.dice import DiceEffect, DiceResult
from app.trpg.state import apply_dice_delta, get_item_state, set_item_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

USE_ITEM_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "use_item",
        "description": (
            "使用一件道具（跑团专用）。系统会校验数量、扣除消耗品并写回效果，你只拿结果叙事。"
            "item 是道具名（背包条目）；target 可选（缺省为持有者）。"
            "没有或已用完的道具不能使用——系统会拒绝并如实返回原因，不要凭空描述成功。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "item": {"type": "string", "description": "道具名（背包条目）"},
                "target": {
                    "type": "string",
                    "description": "可选：使用对象（角色名或 pc.名 / npc.名）",
                },
            },
            "required": ["item"],
        },
    },
}


def _target_key(campaign_id: int, raw: str) -> str | None:
    """目标 → 状态键 ``{kind}.{名}``；裸名经实体表解析，查不到按 pc（持有者多为 PC）。"""
    from app.trpg.encounter import parse_participant
    from app.trpg.state import find_entity

    parsed = parse_participant(raw)
    if parsed is not None:
        return f"{parsed[0]}.{parsed[1]}"
    entity = find_entity(campaign_id, raw)
    if entity is not None:
        return f"{entity['kind']}.{entity['name']}"
    return f"pc.{raw}"


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    name = str(args.get("item") or "").strip()[:ENTITY_NAME_MAX]
    if not name:
        return {"text": "请提供道具名（item 参数）。"}
    state = await asyncio.to_thread(get_item_state, campaign_id, name)
    qty = item_rules.parse_qty(state.get("qty"))
    if state.get("qty") is None:
        return {"text": f"背包里没有「{name}」——不能凭空使用未登记的道具。"}
    if qty is None or qty <= 0:
        return {"text": f"「{name}」已经用完了，无法再次使用。"}

    effect = item_rules.normalize_effect(state.get("effect"))
    consumable = item_rules.parse_consumable(state.get("consumable"))

    target_raw = str(args.get("target") or "").strip()[:ENTITY_NAME_MAX]
    owner_raw = str(state.get("owner") or "").strip()
    target = target_raw or owner_raw
    target_key = await asyncio.to_thread(_target_key, campaign_id, target) if target else None

    hp_delta = item_rules.parse_hp_delta(effect)
    notes: list[str] = []
    if hp_delta is not None and target_key is not None:
        hp_key = f"{target_key}.hp"
        result = DiceResult(
            rolls=[],
            sides=1,
            count=0,
            modifier=0,
            total=0,
            vs=None,
            outcome=None,
            deltas=[DiceEffect(key=hp_key, delta=hp_delta)],
        )
        try:
            await asyncio.to_thread(apply_dice_delta, campaign_id, result)
        except Exception as exc:  # noqa: BLE001 - 落表失败 → 不扣道具
            return {"text": f"道具效果落表失败：{exc}。请如实告诉玩家本次使用尚未生效。"}
    elif hp_delta is not None and target_key is None:
        notes.append("（没有可写回的目标，效果仅叙事）")

    remaining = qty
    if consumable:
        new_qty = item_rules.decrement(qty, 1)
        if new_qty is None:
            return {"text": f"「{name}」数量不足，无法使用。"}
        remaining = new_qty
        await asyncio.to_thread(set_item_facts, campaign_id, name, qty=remaining)

    detail = f"效果：{effect}。" if effect else "（无附加效果）"
    target_text = f"用于 {target_key}" if target_key else ""
    text = (
        f"已使用「{name}」{target_text}。{detail}"
        f"剩余数量 {remaining}。请自然描述道具发挥作用的画面。"
    )
    outcome: dict = {"name": name, "qty": remaining, "effect": effect or None}
    if target_key:
        outcome["target"] = target_key
    return {"text": text, "item_used": outcome}


register(ToolSpec(name="use_item", schema=USE_ITEM_SCHEMA, handler=handle))
