"""exit_character：角色离场（实体 status=cleared；docs/56 §3）。"""

from __future__ import annotations

import asyncio

from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import mark_entity_departed
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

EXIT_CHARACTER_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "exit_character",
        "description": (
            "让角色离场（跑团专用）。角色明确离开当前场景/剧情退场时调用；"
            "系统会把实体标记为离场，之后不再出现在在场名单里。"
            "只是暂时不说话的角色不要调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "角色名（实体表已登记）"},
                "reason": {"type": "string", "description": "可选：离场原因（一句话）"},
            },
            "required": ["entity"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    name = str(args.get("entity") or "").strip()[:ENTITY_NAME_MAX]
    if not name:
        return {"text": "请提供角色名（entity 参数）。"}
    reason = str(args.get("reason") or "").strip()[:60] or None
    entity = await asyncio.to_thread(mark_entity_departed, campaign_id, name)
    if entity is None:
        return {"text": f"实体表里没有角色「{name}」，无需离场处理（可正常叙述其离开）。"}
    return {
        "text": f"「{name}」已离场，在场名单将随之更新。",
        "character": {
            "name": name,
            "kind": str(entity["kind"]),
            "status": "departed",
            "reason": reason,
        },
    }


register(ToolSpec(name="exit_character", schema=EXIT_CHARACTER_SCHEMA, handler=handle))
