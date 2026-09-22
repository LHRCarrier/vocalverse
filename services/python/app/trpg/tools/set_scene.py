"""set_scene：DM 显式切换场景（更新 scene.current，线索/关系注入按新场景过滤）。"""

from __future__ import annotations

import asyncio
import logging

from app.trpg.constants import SCENE_NAME_MAX
from app.trpg.state import set_scene
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

logger = logging.getLogger("vocalverse")

SET_SCENE_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "set_scene",
        "description": (
            "切换当前场景（跑团专用，DM/主持动作）。当剧情明确进入新地点/新场景时调用，"
            "系统会把 scene.current 更新为场景名，后续线索/关系注入按新场景过滤。"
            "禁止凭比喻或修辞推断换场景——只有剧情叙述明确切换地点时才调用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "scene": {"type": "string", "description": "场景名（如 酒馆 / 地城入口 / 王都）"}
            },
            "required": ["scene"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    scene = str(args.get("scene") or "").strip()[:SCENE_NAME_MAX]
    if not scene:
        return {"text": "请提供场景名（scene 参数）。"}
    try:
        await asyncio.to_thread(set_scene, campaign_id, scene)
        return {"text": f"场景已切换至「{scene}」。", "status_stage": "scene"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("酒馆场景切换失败 campaign_id=%s scene=%s", campaign_id, scene)
        return {"text": f"场景切换失败：{exc}"}


register(ToolSpec(name="set_scene", schema=SET_SCENE_SCHEMA, handler=handle))
