"""roll_dice：掷骰判定 + State 域增量 + 主线进度钟联动（系统解析/判定/先落表，模型只讲故事）。

docs/57 §3.1「推进靠规则不靠自觉」：带 ``quest`` 参数的判定由系统做钟算术并落表——
成功 +1（余量 ≥5 再 +1）；失败推进威胁钟 +1（正向钟不受挫）；无钟时按默认 6 格起。
``quest`` 缺省时行为与旧版完全一致（只做判定与 effects 写回）。
"""

from __future__ import annotations

import asyncio
import logging

from app.trpg import progress as progress_rules
from app.trpg.constants import ENTITY_NAME_MAX
from app.trpg.dice import DiceResult, format_dice_text, parse_dice
from app.trpg.state import apply_dice_delta, get_quest_state, set_quest_facts
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

logger = logging.getLogger("vocalverse")

ROLL_DICE_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "roll_dice",
        "description": (
            "掷骰判定（跑团专用）。系统会解析骰子、判定成败并自动更新角色状态，"
            "你只需要拿到结果后描述剧情。"
            "dice 格式：d20 / 2d6（骰面数 2-1000，骰数 1-10）；vs（对抗值，或 dc）必须为正数。"
            'effects 可选：状态增量（如 [{key:"pc.洛可.hp", delta:-5}]），'
            "系统会做增量算术并落表——你不要自己算结果，更不要试图在正文里复述公式，描述情景就好。"
            "quest 可选：本次判定若在推进某条主线，必须写任务名——系统会按成败自动推进进度钟"
            "（成功 +1、大成功再 +1；失败推进威胁钟），你只需在叙述里体现得失。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "dice": {"type": "string", "description": "骰子规格，如 d20 / 2d6"},
                "modifier": {"type": "number", "description": "调整值（默认 0）"},
                "vs": {"type": "number", "description": "对抗值/难度值（判定成功失败；也可用 dc）"},
                "effects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {
                                "type": "string",
                                "description": "状态 key，如 pc.洛可.hp（仅 pc./scene. 域）",
                            },
                            "delta": {"type": "number", "description": "增量（如 -5 表示伤害 5）"},
                        },
                        "required": ["key", "delta"],
                    },
                    "description": "可选：要更新到事实表的状态增量",
                },
                "quest": {
                    "type": "string",
                    "description": (
                        "可选：本次判定所属的主线任务名（与任务表一致）——"
                        "推进主线障碍的判定必须带上；系统自动推进进度钟，不要调用 tick_clock 补"
                    ),
                },
            },
            "required": ["dice"],
        },
    },
}


async def _apply_quest_tick(campaign_id: int, quest: str, result: DiceResult) -> dict | None:
    """判定 → 进度钟（系统算术 + 落表）；已结算任务不推进（返回 None）。"""
    state = await asyncio.to_thread(get_quest_state, campaign_id, quest)
    status = state.get("status")
    if status in ("done", "failed"):
        return None
    kind = progress_rules.normalize_kind(state.get("kind"))
    margin = result.total - result.vs if result.vs is not None else None
    delta = progress_rules.roll_tick_delta(result.outcome, margin, kind)
    tick = progress_rules.tick_progress(
        state.get("progress"), delta, default_segments=progress_rules.DEFAULT_SEGMENTS
    )
    await asyncio.to_thread(
        set_quest_facts,
        campaign_id,
        quest,
        progress=tick.text,
        kind=kind,
        status=status or "active",
    )
    if result.outcome == "success":
        reason = "判定成功" + ("·大成功" if delta >= 2 else "")
    elif kind == "threat":
        reason = "判定失败·威胁逼近"
    else:
        reason = "判定失败"
    return {
        "name": quest,
        "progress": tick.text,
        "segments": tick.segments,
        "kind": kind,
        "reason": reason,
        "full": tick.full,
    }


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    result = parse_dice(args)
    if result is None:
        return {
            "text": (
                "骰子参数无效：dice 需为 d20/2d6 格式（骰面 2-1000，骰数 1-10），vs 需为正数。"
            )
        }
    try:
        summary = await asyncio.to_thread(apply_dice_delta, campaign_id, result)
        logger.info("酒馆掷骰：%s", summary)
    except Exception as exc:  # noqa: BLE001
        # P2-41：落表失败 → 错误文本（杜绝「文本成功但 HP 未落表」），模型如实向玩家说明
        return {"text": f"掷骰判定失败：{exc}。请如实告诉玩家本回合判定尚未生效，稍后再试。"}

    quest = str(args.get("quest") or "").strip()[:ENTITY_NAME_MAX]
    quest_payload: dict | None = None
    if quest and result.outcome is not None:
        try:
            quest_payload = await _apply_quest_tick(campaign_id, quest, result)
        except Exception as exc:  # noqa: BLE001 - 钟落表失败不影响判定本体
            logger.warning("酒馆判定推进分钟失败（quest=%s）：%s", quest, exc)
            quest_payload = None

    # 去裸 key：工具文本只给判定语义，数值细节由系统判定卡/状态条携带
    text = format_dice_text(result) + "\n（系统已记录状态变化。）"
    if quest_payload is not None:
        text += f"\n任务「{quest}」进度 {quest_payload['progress']}。"
    outcome: ToolOutcome = {"text": text, "status_stage": "rolling"}
    if quest_payload is not None:
        outcome["quest"] = quest_payload
    return outcome


register(ToolSpec(name="roll_dice", schema=ROLL_DICE_SCHEMA, handler=handle))
