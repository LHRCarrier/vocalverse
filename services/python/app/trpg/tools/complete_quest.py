"""complete_quest：任务结算 + 尾声渲染 + 一局收尾标记（零 LLM；docs/56 §3）。

- ``outcome`` 可省略 → 由进度自动判定（正向钟满格=强；威胁钟满格=失，见 progress.judge_outcome）；
- 结算写 ``quest.{名}.status``（strong/weak → done；miss → failed，任务行同步）；
- 尾声三件套由模板渲染（标题/正文/后日谈），模型只负责把它讲出来；
- 营地 ``finished_at`` 置位 = 本局归档（允许之后开新篇章）。
"""

from __future__ import annotations

import asyncio

from app.trpg import progress as progress_rules
from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.state import get_quest_state, mark_campaign_finished, set_quest_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

COMPLETE_QUEST_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "complete_quest",
        "description": (
            "结算任务并生成尾声（跑团专用）。当故事走到结局、玩家主动收尾、或进度钟已满时调用；"
            "系统会渲染尾声卡（结局标题/正文/后日谈），你只需要用叙述把它承接好，"
            "不要再为已结算的任务新开主线。outcome 可省略，由进度自动判定。"
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
    quest_state = await asyncio.to_thread(get_quest_state, campaign_id, quest)
    status = quest_state.get("status")
    if status in ("done", "failed"):
        return {"text": f"任务「{quest}」已经结算过了（{status}），可开启新的篇章。"}

    raw_outcome = str(args.get("outcome") or "").strip().lower()
    parsed = progress_rules.parse_progress(quest_state.get("progress")) or (
        0,
        progress_rules.DEFAULT_SEGMENTS,
    )
    kind = progress_rules.normalize_kind(quest_state.get("kind"))
    outcome = (
        raw_outcome
        if raw_outcome in ("strong", "weak", "miss")
        else progress_rules.judge_outcome(parsed[0], parsed[1], kind)
    )
    ending = progress_rules.render_ending(quest, outcome, stage=quest_state.get("stage"))
    await asyncio.to_thread(
        set_quest_facts, campaign_id, quest, status="failed" if outcome == "miss" else "done"
    )
    await asyncio.to_thread(mark_campaign_finished, campaign_id)
    return {
        "text": f"任务「{quest}」已结算（{outcome}）：{ending['title']}。请用尾声叙述收束这一幕。",
        "ending": {"quest": quest, "outcome": outcome, **ending},
    }


register(ToolSpec(name="complete_quest", schema=COMPLETE_QUEST_SCHEMA, handler=handle))
