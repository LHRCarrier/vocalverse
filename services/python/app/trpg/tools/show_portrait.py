"""show_portrait：关键节点展示角色立绘（**信号工具**：只校验实体 + 发展示信号，不生成图）。

骨架（2026-09-22，docs/54 §4 的 P1 第一步）：
- 模型在剧情关键时刻调用（角色首次登场 / 重要转折）→ 本工具校验实体（限 npc/pc、未离场）
  → outcome 附带 ``portrait`` 载荷 → ``turn.py`` 转 SSE ``portrait`` 事件 → 前端展示；
- **图源未接**：``media_id``/``url`` 暂为 null（P1 落 ``trpg_entities.portrait_media_id`` 后回填）；
  当前前端按实体名命中内置素材（无命中降级占位，见 ``components/mobile/trpg/art.ts``）；
- **频控**：同回合重复调用由 ``turn.py`` 去重；跨回合靠 prompt 规则（同一角色每场景至多一次）；
- 失败不阻塞回合：实体不存在 / 已离场 → 错误文本，模型照常叙述。
"""

from __future__ import annotations

import asyncio

from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import find_entity
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

SHOW_PORTRAIT_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "show_portrait",
        "description": (
            "在剧情关键时刻让角色立绘出场（视觉信号，不生成新内容）。"
            "适用：角色首次登场、重要台词/剧情转折。"
            "同一场景对同一角色至多展示一次，禁止每回合调用；"
            "旁白里自然承接即可，不要复述本工具。"
            "entity 必须是本局实体表里已存在的角色名（NPC 或 PC）；"
            "角色刚登场而系统尚未登记时，本回合先正常叙述，下一回合再展示。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entity": {
                    "type": "string",
                    "description": "角色名（本局实体表已登记，NPC 或 PC）",
                },
                "mood": {
                    "type": "string",
                    "description": "可选：此刻的情绪/意境（如 戒备 / 悲伤 / 激昂），供立绘变体选图",
                },
            },
            "required": ["entity"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    name = str(args.get("entity") or "").strip()[:ENTITY_NAME_MAX]
    mood = str(args.get("mood") or "").strip()[:20] or None
    if not name:
        return {"text": "请提供角色名（entity 参数）。"}
    entity = await asyncio.to_thread(find_entity, campaign_id, name)
    if entity is None:
        return {
            "text": (
                f"本局实体表里还没有角色「{name}」——若刚登场，请先用叙述让其出场，"
                "系统登记后下一回合再调用本工具。"
            )
        }
    if entity["status"] == "cleared":
        return {"text": f"角色「{name}」已离场，未展示立绘；如剧情需要请先让其重新登场。"}
    return {
        "text": f"「{name}」的立绘已在画面中展示（请自然承接，勿复述本提示）。",
        "portrait": {"entity": name, "kind": entity["kind"], "mood": mood},
    }


register(ToolSpec(name="show_portrait", schema=SHOW_PORTRAIT_SCHEMA, handler=handle))
