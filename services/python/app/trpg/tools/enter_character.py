"""enter_character：角色登场（实体注册为 active；docs/57 §3.1 修订）。

语义：登场即 **active**（人物确实在场，含 PC）——「正在赶来」是给未来立绘任务的占位，
已由 :func:`app.trpg.state.mark_entity_arriving` 预留但本路径不再调用；已在场的角色不重复触发。
"""

from __future__ import annotations

import asyncio

from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import ensure_entity, find_entity, get_entity_portrait, set_entity_presence
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

ENTER_CHARACTER_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "enter_character",
        "description": (
            "让角色登场（跑团专用）。关键角色首次出现在剧情里时调用；"
            "系统会登记实体并标记为在场（前端据此更新在场名单）。"
            "不要在角色只被提起/在远处一笔带过时调用；同一角色在场期间不要反复调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "角色名（NPC 或 PC）"},
                "role": {
                    "type": "string",
                    "description": "可选：pc / npc（缺省按实体表已有类型或 npc）",
                },
                "note": {"type": "string", "description": "可选：登场情境（一句话）"},
            },
            "required": ["entity"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    name = str(args.get("entity") or "").strip()[:ENTITY_NAME_MAX]
    if not name:
        return {"text": "请提供角色名（entity 参数）。"}
    note = str(args.get("note") or "").strip()[:60] or None
    existing = await asyncio.to_thread(find_entity, campaign_id, name)
    role = str(args.get("role") or "").strip().lower()
    if role in ("pc", "npc"):
        kind = role
    elif existing is not None:
        kind = str(existing["kind"])
    else:
        kind = "npc"

    if existing is not None and existing["status"] == "active" and not existing["pending"]:
        return {
            "text": f"「{name}」已经在本场景中，无需重复登场（继续叙述即可）。",
            "character": {"name": name, "kind": kind, "status": "active", "note": note},
        }

    await asyncio.to_thread(ensure_entity, campaign_id, kind, name, pending=False)
    await asyncio.to_thread(
        set_entity_presence, campaign_id, kind, name, pending=False, status="active"
    )
    portrait = await asyncio.to_thread(get_entity_portrait, campaign_id, name)
    if portrait:
        text = f"「{name}」已就位，立绘可在画面中展示（请自然承接）。"
    else:
        text = f"「{name}」已登场（当前无立绘，前端以占位展示）。请在叙述里为出场留出空间。"
    return {
        "text": text,
        "character": {"name": name, "kind": kind, "status": "active", "note": note},
    }


register(ToolSpec(name="enter_character", schema=ENTER_CHARACTER_SCHEMA, handler=handle))
