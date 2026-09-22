"""complete_quest：任务结算 + 尾声渲染 + 一局收尾标记（零 LLM；docs/56 §3、docs/57 §3.1）。

- 结算逻辑收敛在 :func:`app.trpg.state.settle_quest`（与 settle 路由共用，规则在 progress.py）；
- ``outcome`` 可省略 → 由进度自动判定（正向钟满格=强；威胁钟满格=失，见 progress.judge_outcome）；
- 已 done/failed → **幂等**：返回「已结算」文本，不再发 ending 事件/卡片（docs/57 §3.1 防重）；
- 尾声三件套由模板渲染（标题/正文/后日谈），模型只负责把它讲出来。
"""

from __future__ import annotations

import asyncio

from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import settle_quest
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

COMPLETE_QUEST_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "complete_quest",
        "description": (
            "结算任务并生成尾声（跑团专用）。当故事走到结局、玩家主动收尾、或进度钟已满时调用；"
            "系统会渲染尾声卡（结局标题/正文/后日谈），你只需要用叙述把它承接好。"
            "已结算的任务不得继续推进或再次结算；需要新目标时另开新任务。"
            "outcome 可省略，由进度自动判定。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "quest": {"type": "string", "description": "要结算的任务名"},
                "outcome": {
                    "type": "string",
                    "enum": ["strong", "weak", "miss"],
                    "description": (
                        "结局档位：strong=圆满 / weak=代价与收获并存 / miss=遗憾收场；"
                        "省略则按进度自动判定"
                    ),
                },
            },
            "required": ["quest"],
        },
    },
}


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    quest = str(args.get("quest") or "").strip()[:ENTITY_NAME_MAX]
    if not quest:
        return {"text": "请提供要结算的任务名（quest 参数）。"}
    raw_outcome = str(args.get("outcome") or "").strip().lower() or None
    result = await asyncio.to_thread(settle_quest, campaign_id, quest, raw_outcome)
    if result["existing"]:
        return {
            "text": (
                f"任务「{quest}」已结算（{result['status']}）——不得继续推进或重复结算；"
                "如需继续请开启新篇章。"
            )
        }
    ending = {
        "quest": quest,
        "outcome": result["outcome"],
        "title": result["title"],
        "text": result["text"],
        "epilogue": result["epilogue"],
    }
    return {
        "text": (
            f"任务「{quest}」已结算（{ending['outcome']}）：{ending['title']}。"
            "请用尾声叙述收束这一幕。"
        ),
        "ending": ending,
    }


register(ToolSpec(name="complete_quest", schema=COMPLETE_QUEST_SCHEMA, handler=handle))
