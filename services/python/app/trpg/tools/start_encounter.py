"""start_encounter：开启遭遇战（系统排先攻序；docs/56 §3）。

- 参战者键规范化 ``pc.名`` / ``npc.名``（裸名查实体表，查不到按 npc 并注册 pending）；
- 先攻序 = 每参战者一枚 d20（系统骰，模型不参与）+ 声明序定平手；
- 事实落 ``encounter.main.status/order/turn/round``（order 为 JSON 数组字符串）。
"""

from __future__ import annotations

import asyncio

from app.trpg import encounter as encounter_rules
from app.trpg.state import ensure_entity, find_entity, set_encounter_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

START_ENCOUNTER_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "start_encounter",
        "description": (
            "开启一场遭遇战（跑团专用）。战斗/冲突开始时调用；先攻顺序由系统掷骰排序，"
            "你只按返回的顺序叙事。参战者写角色名或 pc.名 / npc.名（至少一个）。"
            "战斗中的每一次攻击用 attack，推进回合用 next_turn，结束用 end_encounter。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "participants": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参战者列表（pc.名 / npc.名 或角色名），最多 8 人",
                }
            },
            "required": ["participants"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    raw = args.get("participants")
    # 裸名先查实体表定 kind（DB 调用放线程；查不到按 npc），再交给纯函数归一排序
    resolved_kinds: dict[str, str] = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and "." not in item and item.strip():
                entity = await asyncio.to_thread(find_entity, campaign_id, item.strip())
                if entity is not None:
                    resolved_kinds[item.strip()] = str(entity["kind"])
    keys, error = encounter_rules.normalize_participants(
        raw, resolve_kind=lambda name: resolved_kinds.get(name, "npc")
    )
    if error or not keys:
        return {"text": error or "参战者列表非法。"}

    for key in keys:
        parsed = encounter_rules.parse_participant(key)
        if parsed is None:
            continue
        kind, name = parsed
        await asyncio.to_thread(ensure_entity, campaign_id, kind, name, pending=True)

    order = await asyncio.to_thread(encounter_rules.initiative_order, keys)
    await asyncio.to_thread(
        set_encounter_facts,
        campaign_id,
        "main",
        status="active",
        order=order,
        turn=0,
        round_no=1,
    )
    return {
        "text": (
            f"遭遇开始，先攻顺序：{' > '.join(encounter_rules.display_name(k) for k in order)}。"
            "请按此顺序叙事战斗，轮到谁行动就用 attack / use_item 结算。"
        ),
        "status_stage": "rolling",
        "encounter": {"kind": "start", "order": order, "turn": 0, "round": 1},
    }


register(ToolSpec(name="start_encounter", schema=START_ENCOUNTER_SCHEMA, handler=handle))
