"""酒馆工具集：roll_dice 掷骰判定 / set_scene 场景切换（迁移自 ai4u tool-defs + tool-executor）。

契约（P2-17/41/43）：
- 模型只调用不计算；系统解析、判定并落表，**先落表成功再返回文本**；
- roll_dice 的 effects 为 State 域（pc./scene.）增量，系统做算术；
- set_scene 是 DM 显式动作（不靠 LLM 推断场景名）。
"""

from __future__ import annotations

import json
import logging

from app.trpg.constants import SCENE_NAME_MAX
from app.trpg.dice import format_dice_text, parse_dice
from app.trpg.state import apply_dice_delta, set_scene

logger = logging.getLogger("vocalverse")

ROLL_DICE_TOOL: dict = {
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

SET_SCENE_TOOL: dict = {
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


def build_trpg_tools() -> list[dict]:
    """v1 仅骰子 + 场景切换（记忆轨读写全关，工具面最小化）。"""
    return [ROLL_DICE_TOOL, SET_SCENE_TOOL]


def parse_tool_args(raw: str) -> dict:
    """宽容解析工具参数 JSON；坏输入返回 {}（执行层再报可读错误）。"""
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def execute_tool(name: str, raw_args: str, campaign_id: int) -> dict:
    """执行工具调用；返回 ``{text, status_stage?}``（工具文本回填模型，status 供 SSE 指示）。"""
    args = parse_tool_args(raw_args)

    if name == "roll_dice":
        result = parse_dice(args)
        if result is None:
            return {
                "text": (
                    "骰子参数无效：dice 需为 d20/2d6 格式（骰面 2-1000，骰数 1-10），vs 需为正数。"
                )
            }
        try:
            summary = await _to_thread(apply_dice_delta, campaign_id, result)
            logger.info("酒馆掷骰：%s", summary)
            # 去裸 key：工具文本只给判定语义，数值细节由系统判定卡/状态条携带
            return {
                "text": format_dice_text(result) + "\n（系统已记录状态变化。）",
                "status_stage": "rolling",
            }
        except Exception as exc:  # noqa: BLE001
            # P2-41：落表失败 → 错误文本（杜绝「文本成功但 HP 未落表」），模型如实向玩家说明
            return {"text": f"掷骰判定失败：{exc}。请如实告诉玩家本回合判定尚未生效，稍后再试。"}

    if name == "set_scene":
        scene = str(args.get("scene") or "").strip()[:SCENE_NAME_MAX]
        if not scene:
            return {"text": "请提供场景名（scene 参数）。"}
        try:
            await _to_thread(set_scene, campaign_id, scene)
            return {"text": f"场景已切换至「{scene}」。", "status_stage": "scene"}
        except Exception as exc:  # noqa: BLE001
            return {"text": f"场景切换失败：{exc}"}

    return {"text": f"未知工具：{name}（本场景未注册）。"}


async def _to_thread(fn, *args):
    import asyncio

    return await asyncio.to_thread(fn, *args)
