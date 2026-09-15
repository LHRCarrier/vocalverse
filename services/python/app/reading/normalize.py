"""读书域 · 词归一化纯函数（seed 导入与查询 API 共用同一实现，防归一不一致导致查不到）。

规则（数据模型拷问 V-8）：
1. Unicode NFC 规范化；2. 小写；3. 弯撇 U+2018/U+2019 → 直撇 '；
4. 去两端引号/括号/标点（保留内部连字符与撇号）；5. 折叠内部空白；
6. 空/纯标点/纯数字项返回空串（调用方决定 45003）。

不在连字符处拆分（"well-known" / "o'clock" 当整词，ECDICT 有对应条目）。
"""

from __future__ import annotations

import re
import unicodedata

#: 词义字符集：字母/撇号/连字符（内部），词首词尾的引号括号标点一律剥掉。
_WORD_CHARS_RE = re.compile(r"^[a-z][a-z'\-]*$")

_STRIP_CHARS = " \t\r\n\"'’‘“”()（）[]【】.,;:!?…—–·《》<>/\\|`~@#$%^&*+=_{}"


def normalize_word(raw: str) -> str:
    """归一化：NFC → 小写 → 弯撇转直 → 去两端标点 → 折叠空白。"""
    word = unicodedata.normalize("NFC", raw or "")
    word = word.replace("\u2018", "'").replace("\u2019", "'")
    word = word.strip(_STRIP_CHARS)
    word = re.sub(r"\s+", " ", word)
    word = word.lower()
    return word


def is_lookupable(word: str) -> bool:
    """是否可查词（词形合法：字母开头、仅字母/撇号/连字符）。纯数字/空/符号 → False。"""
    return bool(_WORD_CHARS_RE.match(word)) and any(c.isalpha() for c in word)


__all__ = ["normalize_word", "is_lookupable"]
