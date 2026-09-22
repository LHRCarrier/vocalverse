"""next_turn：遭遇回合推进（下标回绕 → 轮次 +1；docs/56 §3）。"""

from __future__ import annotations

import asyncio

from app.trpg import encounter as encounter_rules
from app.trpg.state import get_active_encounter, set_encounter_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

NEXT_TURN_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "next_turn",
        "description": (
            "推进遭遇的当前回合（跑团专用）。一个参战者行动结束后调用；"
            "走到队尾会自动进入下一轮（round+1）。系统负责顺序与轮次，你只按返回结果叙事。"
        ),
        "parameters": {"type": "object", "properties": {}},
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    current = await asyncio.to_thread(get_active_encounter, campaign_id)
    if current is None:
        return {"text": "当前没有进行中的遭遇——先用 start_encounter 开启战斗。"}
    order: list[str] = list(current.get("order") or [])
    if not order:
        return {"text": "遭遇的先攻序丢失，无法推进回合；请用 start_encounter 重新开始。"}
    advanced = encounter_rules.advance_turn(
        len(order), int(current.get("turn") or 0), int(current.get("round") or 1)
    )
    await asyncio.to_thread(
        set_encounter_facts,
        campaign_id,
        str(current["id"]),
        turn=advanced.turn,
        round_no=advanced.round,
        status="active",
    )
    report = encounter_rules.format_turn_report(order, advanced.turn, advanced.round)
    if advanced.wrapped:
        report += "（新一轮开始）"
    return {
        "text": f"{report}请沿先攻序继续叙事。",
        "encounter": {
            "kind": "turn",
            "order": order,
            "turn": advanced.turn,
            "round": advanced.round,
        },
    }


register(ToolSpec(name="next_turn", schema=NEXT_TURN_SCHEMA, handler=handle))
