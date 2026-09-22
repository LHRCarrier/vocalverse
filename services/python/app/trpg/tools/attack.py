"""attack：攻击判定 + 伤害写回（系统权威；docs/56 §3、docs/55 §P4）。

契约（红线：模型只提议，规则引擎权威——DiceFrame / TRPG-master 口径）：
- 目标解析为实体（npc/pc）→ 事实键 ``{kind}.{名}.hp``；
- 命中 = d20 + modifier ≥ vs（默认 12，modifier 默认 0）；
- 伤害写回复用 :func:`app.trpg.state.apply_dice_delta`（与掷骰同一条写路径），
  **未命中绝不写状态**；文本只给叙事语义（去公式），数值由事件字段携带；
- 目标缺 HP 行时可用 ``target_hp`` 建档（一次性），否则伤害不落表并如实告知。
"""

from __future__ import annotations

import asyncio
import logging

from app.trpg import encounter as encounter_rules
from app.trpg.constants import ENTITY_NAME_MAX, STATE_DOMAINS
from app.trpg.dice import DiceEffect, DiceResult, parse_dice
from app.trpg.facts import parse_key
from app.trpg.state import (
    apply_dice_delta,
    find_entity,
    find_pc_entity,
    get_fact_value,
    persist_system_card,
)
from app.trpg.tools.registry import ToolArgs, ToolOutcome, ToolSpec, register

logger = logging.getLogger("vocalverse")

#: 默认对抗值（docs/56 §3：vs 缺省 12）
DEFAULT_VS = 12
#: 单次伤害上限（防 LLM 写出 -9999；不影响叙事自由）
DAMAGE_MAX = 999

ATTACK_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "attack",
        "description": (
            "发起一次攻击（跑团专用）。系统负责命中判定与 HP 写回，你只拿结果叙事。"
            "target 是目标角色名或 npc.名 / pc.名；attacker 缺省为玩家角色。"
            "weapon 写武器/招式名；damage 写命中后的伤害点数（或 effects 给状态增量）。"
            "目标还没有 HP 记录时可以传 target_hp 先建档。"
            "禁止在正文里复述命中公式——叙述结果即可；未命中就是未命中。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "目标：角色名或 npc.名 / pc.名"},
                "attacker": {"type": "string", "description": "可选：攻击者（默认玩家角色）"},
                "weapon": {"type": "string", "description": "可选：武器/招式（叙事用）"},
                "vs": {"type": "integer", "description": "对抗值（默认 12）"},
                "modifier": {"type": "integer", "description": "命中调整值（默认 0，范围 -50~50）"},
                "damage": {"type": "integer", "description": "命中后的伤害点数（默认 0）"},
                "effects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "key": {"type": "string", "description": "状态 key，如 npc.地精.hp"},
                            "delta": {"type": "number", "description": "增量（如 -5）"},
                        },
                        "required": ["key", "delta"],
                    },
                    "description": "可选：命中后的状态增量（与 damage 二选一，优先 effects）",
                },
                "target_hp": {
                    "type": "integer",
                    "description": "可选：目标缺 HP 行时的初始 HP（一次性建档）",
                },
            },
            "required": ["target"],
        },
    },
}


def _resolve_entity(campaign_id: int, raw: str) -> tuple[str, str] | None:
    """解析目标为 ``(kind, name)``；规范化键（npc./pc.）或实体表名字。"""
    parsed = encounter_rules.parse_participant(raw)
    if parsed is not None:
        return parsed
    entity = find_entity(campaign_id, raw)
    if entity is None:
        return None
    return str(entity["kind"]), str(entity["name"])


def _valid_effects(raw: object) -> list[DiceEffect] | None:
    """校验 effects（仅 State 域键；与 dice.parse_dice 同口径）；非法返回 None。"""
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    out: list[DiceEffect] = []
    for item in raw:
        if not isinstance(item, dict):
            return None
        key = item.get("key")
        delta = item.get("delta")
        if (
            not isinstance(key, str)
            or isinstance(delta, bool)
            or not isinstance(delta, (int, float))
        ):
            return None
        parsed = parse_key(key)
        if parsed is None or parsed.domain not in STATE_DOMAINS:
            return None
        out.append(DiceEffect(key=key, delta=int(delta)))
    return out


def _hp_int(value: str | None) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


async def handle(args: ToolArgs, campaign_id: int) -> ToolOutcome:
    target_raw = str(args.get("target") or "").strip()[:ENTITY_NAME_MAX]
    if not target_raw:
        return {"text": "请提供攻击目标（target 参数）。"}
    resolved = await asyncio.to_thread(_resolve_entity, campaign_id, target_raw)
    if resolved is None:
        return {
            "text": (
                f"攻击目标「{target_raw}」不在本局实体表里——若刚登场，请先用 enter_character "
                "登记；本回合该攻击尚未生效，请如实告诉玩家。"
            )
        }
    target_kind, target_name = resolved
    target_key = f"{target_kind}.{target_name}"
    hp_key = f"{target_key}.hp"

    raw_vs = args.get("vs", DEFAULT_VS)
    if isinstance(raw_vs, bool) or not isinstance(raw_vs, (int, float)) or raw_vs < 1:
        return {"text": f"vs 需为正整数（收到 {raw_vs!r}）。"}
    vs = int(raw_vs)
    raw_mod = args.get("modifier", 0)
    if isinstance(raw_mod, bool) or not isinstance(raw_mod, (int, float)):
        return {"text": "modifier 需为整数（范围 -50~50）。"}
    modifier = int(raw_mod)

    roll = parse_dice({"dice": "d20", "modifier": modifier, "vs": vs})
    if roll is None:
        return {"text": "命中参数非法：modifier 需在 -50~50 之间，vs 为正整数。"}

    # 攻击者：显式指定 > 最近提及的 PC 实体 > 玩家
    attacker_raw = str(args.get("attacker") or "").strip()[:ENTITY_NAME_MAX]
    if attacker_raw:
        attacker_resolved = await asyncio.to_thread(_resolve_entity, campaign_id, attacker_raw)
        attacker = (
            f"{attacker_resolved[0]}.{attacker_resolved[1]}"
            if attacker_resolved is not None
            else f"pc.{attacker_raw}"
        )
    else:
        pc = await asyncio.to_thread(find_pc_entity, campaign_id)
        attacker = f"pc.{pc['name']}" if pc is not None else "玩家"
    weapon = str(args.get("weapon") or "").strip()[:40] or None

    hit = roll.outcome == "success"
    deltas: list[DiceEffect] = []
    notes: list[str] = []
    hp_before: int | None = None
    if hit:
        effects = _valid_effects(args.get("effects"))
        if effects is None:
            return {"text": "effects 非法：需为 [{key, delta}]，key 仅限 pc./npc./scene. 状态域。"}
        if effects:
            deltas = effects
        else:
            raw_damage = args.get("damage", 0)
            if isinstance(raw_damage, bool) or not isinstance(raw_damage, (int, float)):
                return {"text": "damage 需为非负整数。"}
            damage_value = int(raw_damage)
            if damage_value < 0 or damage_value > DAMAGE_MAX:
                return {"text": f"damage 需在 0~{DAMAGE_MAX} 之间（收到 {damage_value}）。"}
            if damage_value > 0:
                deltas = [DiceEffect(key=hp_key, delta=-damage_value)]

        hp_before = _hp_int(await asyncio.to_thread(get_fact_value, campaign_id, hp_key))
        if any(d.key == hp_key for d in deltas) and hp_before is None:
            seed = args.get("target_hp")
            if isinstance(seed, (int, float)) and not isinstance(seed, bool) and seed > 0:
                await asyncio.to_thread(_seed_hp, campaign_id, hp_key, int(seed))
                hp_before = int(seed)
            else:
                deltas = [d for d in deltas if d.key != hp_key]
                notes.append(
                    f"（{target_name} 的 HP 尚未登记，本次伤害未落表；可传 target_hp 建档）"
                )
        if deltas:
            apply_result = DiceResult(
                rolls=roll.rolls,
                sides=roll.sides,
                count=roll.count,
                modifier=roll.modifier,
                total=roll.total,
                vs=roll.vs,
                outcome=roll.outcome,
                deltas=deltas,
            )
            try:
                await asyncio.to_thread(apply_dice_delta, campaign_id, apply_result)
            except Exception as exc:  # noqa: BLE001 - 落表失败 → 错误文本，绝不假装成功
                return {"text": f"攻击落表失败：{exc}。请如实告诉玩家本回合该攻击尚未生效。"}

    hp_after = _hp_int(await asyncio.to_thread(get_fact_value, campaign_id, hp_key))
    damage_done = (
        max(0, hp_before - hp_after) if hp_before is not None and hp_after is not None else 0
    )
    report = encounter_rules.format_attack_report(
        attacker,
        target_key,
        hit=hit,
        damage=damage_done,
        target_hp=hp_after,
        weapon=weapon,
    )
    if notes:
        report = f"{report}{''.join(notes)}"
    # 战报系统卡（docs/57 §3.1）：命中/失手都留痕，刷新后仍能看到战斗经过
    card_text = encounter_rules.format_attack_card(
        attacker,
        target_key,
        hit=hit,
        damage=damage_done,
        target_hp=hp_after,
        weapon=weapon,
    )
    try:
        await asyncio.to_thread(persist_system_card, campaign_id, "dice", {"text": card_text})
    except Exception as exc:  # noqa: BLE001 - 卡片失败不影响攻击结果
        logger.warning("酒馆战报卡落库失败（campaign=%s）：%s", campaign_id, exc)
    return {
        "text": report,
        "status_stage": "rolling",
        "encounter": {
            "kind": "attack",
            "attacker": attacker,
            "target": target_key,
            "hit": hit,
            "damage": damage_done,
            "targetHp": hp_after,
        },
    }


def _seed_hp(campaign_id: int, hp_key: str, value: int) -> None:
    from app.trpg.facts import FactOp
    from app.trpg.state import upsert_facts

    upsert_facts(campaign_id, [FactOp(op="create", key=hp_key, value=str(value), writer="system")])


register(ToolSpec(name="attack", schema=ATTACK_SCHEMA, handler=handle))
