"""end_encounter：结束遭遇（status=done；docs/56 §3）。"""

from __future__ import annotations

import asyncio

from app.trpg.state import get_active_encounter, set_encounter_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

END_ENCOUNTER_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "end_encounter",
        "description": (
            "结束当前遭遇战（跑团专用）。战斗分出结果（击退/逃脱/谈判收场）后调用；"
            "系统会关闭遭遇状态，之后请回到常规叙事。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "outcome": {"type": "string", "description": "可选：战斗结果概述（一句话）"}
            },
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    current = await asyncio.to_thread(get_active_encounter, campaign_id)
    if current is None:
        return {"text": "当前没有进行中的遭遇，无需结束。"}
    outcome = str(args.get("outcome") or "").strip()[:40] or None
    await asyncio.to_thread(set_encounter_facts, campaign_id, str(current["id"]), status="done")
    tail = f"（{outcome}）" if outcome else ""
    return {
        "text": f"遭遇已结束{tail}。请用一段收束叙述回到常规冒险节奏。",
        "encounter": {"kind": "end", "outcome": outcome},
    }


register(ToolSpec(name="end_encounter", schema=END_ENCOUNTER_SCHEMA, handler=handle))
