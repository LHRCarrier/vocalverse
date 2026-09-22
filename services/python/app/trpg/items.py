"""道具条目纯函数（docs/56 §A；规则层无 DB、无 IO，红线 9 可单测）。

事实表条目形状（docs/56 §2）：
- ``item.{名}.qty``        数量（非负整数；工具增减）
- ``item.{名}.owner``      持有者（``pc.{名}``；背包过滤）
- ``item.{名}.effect``     效果描述（≤60 字；数值约定由本模块解析）
- ``item.{名}.consumable`` 用后是否扣减（true|false，缺省按 true）

效果数值约定（叙事 + 数值分离：文案给模型，增量给系统）：
``effect`` 文本内嵌 ``hp+N`` / ``hp-N``（大小写不敏感），或中文「回复N / 恢复N / 治疗N」
（正向）与「损失N / 失去N」（负向）；解析出的增量由 use_item 走 ``apply_dice_delta`` 落表。
"""

from __future__ import annotations

import re

#: item.name.property 的合法属性（与 constants.DOMAIN_PROPERTIES["item"] 一致）
ITEM_PROPERTIES: tuple[str, ...] = ("qty", "owner", "effect", "consumable")
#: 效果描述长度上限（docs/56 §2：≤60）
ITEM_EFFECT_MAX = 60
#: 单次效果增量上限（防 LLM 写出「回复 hp+9999」击穿数值）
ITEM_EFFECT_DELTA_MAX = 99

_HP_SIGNED_RE = re.compile(r"hp\s*([+-])\s*(\d+)", re.IGNORECASE)
_HEAL_RE = re.compile(r"(?:回复|恢复|治疗)\s*(\d+)")
_LOSS_RE = re.compile(r"(?:损失|失去|扣除)\s*(\d+)")


def item_key(name: str, prop: str) -> str | None:
    """``("治疗药水", "qty")`` → ``item.治疗药水.qty``；属性非法返回 None。"""
    item = str(name or "").strip()
    if not item or prop not in ITEM_PROPERTIES:
        return None
    return f"item.{item}.{prop}"


def parse_item_name(key: str) -> str | None:
    """``item.治疗药水.qty`` → ``治疗药水``；非 item 键/结构非法返回 None。"""
    parts = str(key or "").split(".")
    if len(parts) != 3 or parts[0] != "item" or not parts[1] or parts[2] not in ITEM_PROPERTIES:
        return None
    return parts[1]


def parse_qty(value: object) -> int | None:
    """数量解析：非负整数才合法（``"3"``/``3`` → 3；负数/小数/文本/None → None）。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isdigit():
            return None
        return int(text)
    return None


def parse_consumable(value: object) -> bool:
    """用后是否扣减：显式 false/0/否 → False；其余（含缺省）→ True（道具默认消耗）。"""
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    return text not in ("false", "0", "no", "否", "不消耗")


def normalize_effect(value: object) -> str:
    """效果描述归一：去首尾空白 + 截断 60 字（空 → 空串，调用方按「无效果」处理）。"""
    return str(value or "").strip()[:ITEM_EFFECT_MAX]


def decrement(qty: int, amount: int = 1) -> int | None:
    """扣减算术：足够返回新数量；不足返回 None（调用方给「已经用完」文本，绝不写负数）。"""
    if amount < 0:
        return None
    if qty < amount:
        return None
    return qty - amount


def parse_hp_delta(effect: str | None) -> int | None:
    """从效果描述解析 HP 增量（``hp+5`` / 「回复 5」…）；无约定命中 → None。"""
    text = str(effect or "")
    if not text:
        return None
    if match := _HP_SIGNED_RE.search(text):
        delta = int(match.group(2)) * (1 if match.group(1) == "+" else -1)
    elif match := _HEAL_RE.search(text):
        delta = int(match.group(1))
    elif match := _LOSS_RE.search(text):
        delta = -int(match.group(1))
    else:
        return None
    if delta == 0 or abs(delta) > ITEM_EFFECT_DELTA_MAX:
        return None
    return delta
