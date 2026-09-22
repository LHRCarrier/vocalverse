"""enter_character：角色登场（实体注册 + arriving/pending 占位；docs/56 §3）。

语义（docs/55 §P3）：「XX 正在赶来…」= 实体 pending=True（无立绘时），前端出占位卡；
已挂立绘的实体直接 active。已在场（pending=False 且 active）的角色不重复触发登场信号。
"""

from __future__ import annotations

import asyncio

from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import find_entity, get_entity_portrait, mark_entity_arriving
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

ENTER_CHARACTER_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "enter_character",
        "description": (
            "让角色登场（跑团专用）。关键角色首次出现在剧情里时调用；"
            "系统会登记实体并在没有立绘时让前端显示「正在赶来…」占位，图就绪后自动替换。"
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
                "note": {"type": "string", "description": "可选：登场情境（一句话，供前端占位卡）"},
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

    await asyncio.to_thread(mark_entity_arriving, campaign_id, kind, name)
    portrait = await asyncio.to_thread(get_entity_portrait, campaign_id, name)
    if portrait:
        text = f"「{name}」已就位，立绘可在画面中展示（请自然承接）。"
        status = "active"
    else:
        text = f"「{name}」正在赶来（尚无立绘）——请在叙述里为出场留出空间，不要复述本提示。"
        status = "arriving"
    return {
        "text": text,
        "character": {"name": name, "kind": kind, "status": status, "note": note},
    }


register(ToolSpec(name="enter_character", schema=ENTER_CHARACTER_SCHEMA, handler=handle))
