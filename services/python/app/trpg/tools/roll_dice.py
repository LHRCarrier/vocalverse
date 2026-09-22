"""roll_dice：掷骰判定 + State 域增量（系统解析/判定/先落表，模型只拿结果讲故事）。"""

from __future__ import annotations

import asyncio
import logging

from app.trpg.dice import format_dice_text, parse_dice
from app.trpg.state import apply_dice_delta
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
            },
            "required": ["dice"],
        },
    },
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
        # 去裸 key：工具文本只给判定语义，数值细节由系统判定卡/状态条携带
        return {
            "text": format_dice_text(result) + "\n（系统已记录状态变化。）",
            "status_stage": "rolling",
        }
    except Exception as exc:  # noqa: BLE001
        # P2-41：落表失败 → 错误文本（杜绝「文本成功但 HP 未落表」），模型如实向玩家说明
        return {"text": f"掷骰判定失败：{exc}。请如实告诉玩家本回合判定尚未生效，稍后再试。"}


register(ToolSpec(name="roll_dice", schema=ROLL_DICE_SCHEMA, handler=handle))
