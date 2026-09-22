"""遭遇（战斗）纯函数（docs/56 §A；规则层无 DB、无 IO，红线 9 可单测）。

约定（docs/55 §P4 + DiceFrame 口径「模型讲故事，引擎管状态」）：
- 参战者键规范化 ``pc.{名}`` / ``npc.{名}``（与事实表域一致，可直接拼 ``.hp``）；
- 先攻序由系统排序（每参战者一枚 d20，经由 :mod:`app.trpg.dice`；同点按声明序），
  LLM 只拿顺序叙事，禁止自己排；
- 回合推进由系统做下标回绕（``turn`` 走完一圈 → ``round+1``）；
- 战报文案**去公式**：不下发 d20/加值/对抗值等算术细节，只给叙事语义（数值由事件
  字段 ``damage``/``targetHp`` 携带，前端判定卡消费）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from app.trpg.dice import parse_dice

#: 参战者键前缀（pc/npc；hp 事实键 = ``{participant}.hp``）
PARTICIPANT_KINDS: tuple[str, ...] = ("pc", "npc")
#: 单场遭遇参战者上限（防 LLM 一次塞入整支军队；超出截断由工具层报错）
ENCOUNTER_MAX_PARTICIPANTS = 8
#: 先攻骰面（d20；无属性系统 → 纯随机 + 声明序定平手，docs/56 §3）
INITIATIVE_SIDES = 20


def participant_key(name: str, kind: str | None = None) -> str | None:
    """名字 → 规范化参战者键；名字已带 ``pc./npc.`` 前缀时原样规范化返回。

    非法（空名 / kind 不在 pc|npc / 前缀冲突）→ None。
    """
    raw = str(name or "").strip()
    if not raw:
        return None
    if "." in raw:
        prefix, _, rest = raw.partition(".")
        if prefix in PARTICIPANT_KINDS and rest.strip():
            return f"{prefix}.{rest.strip()}"
        return None
    k = str(kind or "").strip().lower()
    if k not in PARTICIPANT_KINDS:
        return None
    return f"{k}.{raw}"


def parse_participant(key: str) -> tuple[str, str] | None:
    """规范化参战者键 → ``(kind, name)``；非法返回 None。"""
    raw = str(key or "").strip()
    prefix, _, name = raw.partition(".")
    if prefix not in PARTICIPANT_KINDS or not name.strip():
        return None
    return prefix, name.strip()


def normalize_participants(raw: list, resolve_kind=None) -> tuple[list[str], str | None]:
    """参战者列表归一：去空/去重/截断上限；返回 ``(keys, error)``。

    ``resolve_kind(name)``：裸名（无前缀）的 kind 解析回调（工具层用实体表查；
    查不到按 ``npc``）——纯函数不触 DB，故以回调注入。
    """
    if not isinstance(raw, list) or not raw:
        return [], "参战者列表不能为空"
    keys: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            continue
        if "." in item:
            key = participant_key(item)
        else:
            kind = "npc"
            if resolve_kind is not None:
                kind = str(resolve_kind(item.strip()) or "npc")
            key = participant_key(item, kind)
        if key is None or key in keys:
            continue
        keys.append(key)
        if len(keys) >= ENCOUNTER_MAX_PARTICIPANTS:
            break
    if not keys:
        return [], "参战者列表非法（需 pc.名 / npc.名 或已登记的角色名）"
    return keys, None


def initiative_order(keys: list[str], *, rolls: list[int] | None = None) -> list[str]:
    """先攻排序：每参战者一枚 d20（``rolls`` 仅测试/回放注入），降序 + 声明序定平手。

    正常路径经由 :func:`app.trpg.dice.parse_dice` 掷骰（系统骰，模型不参与）。
    """
    if rolls is None:
        rolls = [roll_initiative() for _ in keys]
    scored = list(zip(keys, rolls, range(len(keys)), strict=False))
    scored.sort(key=lambda item: (-item[1], item[2]))
    return [key for key, _, _ in scored]


def roll_initiative() -> int:
    """单枚先攻骰（d20）；解析失败理论上不可能，兜底返回 1。"""
    result = parse_dice({"dice": f"d{INITIATIVE_SIDES}"})
    if result is None or not result.rolls:
        return 1
    return int(result.rolls[0])


@dataclass(frozen=True)
class TurnAdvance:
    turn: int
    round: int
    wrapped: bool


def advance_turn(count: int, turn: int, round_no: int) -> TurnAdvance:
    """回合下标前进（回绕则轮次 +1）；``count<=0`` 视为 1，防零除/死循环。"""
    size = max(1, int(count))
    idx = int(turn) % size
    if idx + 1 >= size:
        return TurnAdvance(turn=0, round=max(1, int(round_no)) + 1, wrapped=True)
    return TurnAdvance(turn=idx + 1, round=max(1, int(round_no)), wrapped=False)


def encode_order(order: list[str]) -> str:
    """先攻序 → JSON 数组字符串（事实表 value 是 String(200)，系统编码，LLM 不写）。"""
    return json.dumps(list(order), ensure_ascii=False)


def decode_order(value: str | None) -> list[str]:
    """JSON 数组字符串 → 列表；坏值宽容返回 []（刷新时不炸面板）。"""
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if isinstance(item, str) and item.strip()]


def format_attack_report(
    attacker: str,
    target: str,
    *,
    hit: bool,
    damage: int = 0,
    target_hp: int | None = None,
    weapon: str | None = None,
) -> str:
    """战报文本（去公式：无 d20/加值/对抗值；数值只在「造成 N 点伤害/剩余 HP」出现）。"""
    attacker_name = display_name(attacker)
    target_name = display_name(target)
    weapon_text = f"用{weapon.strip()}" if (weapon or "").strip() else ""
    strike = f"{attacker_name}{weapon_text}的攻击"
    if not hit:
        return f"{strike}落空了——{target_name}闪身避开。"
    if damage > 0:
        hp_text = f"，{target_name}剩余 HP {target_hp}" if target_hp is not None else ""
        return f"{strike}命中了{target_name}，造成 {damage} 点伤害{hp_text}。"
    return f"{strike}命中了{target_name}，但没有造成实质伤害。"


def format_turn_report(order: list[str], turn: int, round_no: int) -> str:
    """回合指示文本（当前行动者 + 第几轮）。"""
    if not order:
        return f"第 {round_no} 轮。"
    actor = display_name(order[turn % len(order)])
    return f"第 {round_no} 轮，当前行动：{actor}。"


def display_name(key: str) -> str:
    """参战者键 → 展示名（``npc.地精`` → ``地精``）；非法键原样返回。"""
    parsed = parse_participant(key)
    return parsed[1] if parsed is not None else str(key or "某人")
