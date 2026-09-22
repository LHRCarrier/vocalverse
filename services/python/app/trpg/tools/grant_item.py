"""grant_item：道具入账（战利品/购买/搜刮/拾取/奖励的唯一来源；docs/57 §3.1）。

- 新条目：写 ``item.{名}.qty/owner/effect/consumable``（owner 缺省 = 首 PC / 唯一 pc 事实主体）；
- 已存在：数量累加（effect/consumable 显式给出才覆盖；owner 移动不在本工具职责内）；
- 不发新 SSE 事件类型：前端从事实表刷新背包（``item.*``）。
"""

from __future__ import annotations

import asyncio

from app.trpg import items as item_rules
from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.encounter import display_name
from app.trpg.state import (
    default_item_owner,
    find_entity,
    get_item_state,
    set_item_facts,
)
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

#: 单次入账数量上限（防 LLM 一次塞 9999 瓶药水；docs/57 §3.1）
GRANT_QTY_MAX = 99

GRANT_ITEM_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "grant_item",
        "description": (
            "把道具放进玩家背包（跑团专用）。战利品、购买、搜刮、拾取、任务奖励等"
            "任何获得物品的情形都必须调用本工具，禁止只在叙述里给物品。"
            "name 是道具名；qty 为本次获得数量（1~99，默认 1）；"
            "effect 写效果描述（数值约定如 hp+5 / 回复5）；consumable 表示用后是否扣减（默认是）；"
            "owner 可选（缺省归当前 PC）。同一道具再次获得会累加数量。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "道具名（背包条目标题）"},
                "qty": {"type": "integer", "description": "本次获得数量 1~99（默认 1）"},
                "effect": {"type": "string", "description": "可选：效果描述（≤60 字，如 hp+5）"},
                "consumable": {"type": "boolean", "description": "可选：用后是否扣减（默认是）"},
                "owner": {
                    "type": "string",
                    "description": "可选：持有者（角色名或 pc.名；缺省为当前 PC）",
                },
            },
            "required": ["name"],
        },
    },
}


def _owner_key(campaign_id: int, raw: str) -> str:
    """持有者 → ``{kind}.{名}``；裸名经实体表解析，查不到按 pc（背包归属 PC）。"""
    from app.trpg.encounter import parse_participant

    parsed = parse_participant(raw)
    if parsed is not None:
        return f"{parsed[0]}.{parsed[1]}"
    entity = find_entity(campaign_id, raw)
    if entity is not None:
        return f"{entity['kind']}.{entity['name']}"
    return f"pc.{raw}"


def _owner_text(owner: str | None) -> str:
    if not owner:
        return ""
    return f"，归 {display_name(owner)}"


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    name = str(args.get("name") or "").strip()[:ENTITY_NAME_MAX]
    if not name:
        return {"text": "请提供道具名（name 参数）。"}

    qty = item_rules.parse_qty(args.get("qty", 1))
    if qty is None or not (1 <= qty <= GRANT_QTY_MAX):
        return {"text": f"qty 需为 1~{GRANT_QTY_MAX} 的整数（收到 {args.get('qty')!r}）。"}

    effect = item_rules.normalize_effect(args.get("effect")) or None
    raw_consumable = args.get("consumable")
    consumable = item_rules.parse_consumable(raw_consumable) if raw_consumable is not None else None

    state = await asyncio.to_thread(get_item_state, campaign_id, name)
    current_qty = item_rules.parse_qty(state.get("qty"))
    if current_qty is not None:
        total = current_qty + qty
        await asyncio.to_thread(
            set_item_facts,
            campaign_id,
            name,
            qty=total,
            effect=effect,
            consumable=consumable,
        )
        detail = f"，效果：{effect}" if effect else ""
        return {
            "text": (
                f"「{name}」×{qty} 已入账（现有 {total}{detail}）。"
                "请自然地把它写进叙述，不要说这是系统发放。"
            )
        }

    owner_raw = str(args.get("owner") or "").strip()[:ENTITY_NAME_MAX]
    if owner_raw:
        owner = await asyncio.to_thread(_owner_key, campaign_id, owner_raw)
    else:
        owner = await asyncio.to_thread(default_item_owner, campaign_id)
    await asyncio.to_thread(
        set_item_facts,
        campaign_id,
        name,
        qty=qty,
        owner=owner,
        effect=effect,
        consumable=consumable,
    )
    detail = f"，效果：{effect}" if effect else ""
    return {
        "text": (
            f"已获得「{name}」×{qty}{_owner_text(owner)}{detail}。"
            "请自然地把它写进叙述，不要说这是系统发放。"
        )
    }


register(ToolSpec(name="grant_item", schema=GRANT_ITEM_SCHEMA, handler=handle))
