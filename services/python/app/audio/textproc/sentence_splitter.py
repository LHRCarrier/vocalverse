"""流式 TTS 句切分器（engine-agnostic 纯逻辑，独立模块）。

定位：把「文本 → 完整句」的切割从 turn 编排器里剥离出来，归入 TTS 文本工程层。
本模块**不 import 任何引擎 / 网络 / 配置**，只在字节流上做纯字符串判定，便于单测
与复用（orchestrator 边生成边合成、自由对话、shadow 出句共用同一口径）。

边界判定（借鉴 Patter / VoiceStudio 思路，自写实现；重要原则：**宁可少切，不可误切**，
因为把"Mr." 当句号切开会让 TTS 在错误处停顿、甚至把半句单独合成——假阴性可接受，
假阳性是听感硬伤）：

- `.!?` 后随空白 / 引号 / 括号 / 行尾 → 候选句界；
- `.` 且其后紧跟字母/数字（`3.5`、`U.S`、`e.g`、`Ph.D`、`v2.5`）→ **中缀**，非句界；
- `.` 前是单词且命中缩写表（`Mr/Dr/St/Inc/etc/…`，带 cap/digit 守卫）→ 非句界；
- `.` 前是**单字母**或**点分缩写**（`U.S.` 尾部、`J. Smith`、`Ph.D.` 尾部）→ 非句界；
- `.` 属于网址后缀（`.com/.net/.org/...`）→ 非句界；
- `.!?` 落在 `[...]` 括号标签内（如 `[pause 300ms]`、`[laugh]`）→ 非句界；
- 无标点超长句：优先 **分句边界**(`;:,—`) → **词边界**(空格) → **避开括号 tag 的硬切**。
"""

from __future__ import annotations

import re

#: 单句合成尖峰上限（LLM 不守规矩时防单句过长，docs/19 P0-5）。可被调用方覆盖。
MAX_SENTENCE_CHARS = 300

#: 句子终结符（.!? 及后随空白/引号/括号/下引号，作 consume/rstrip 的后缀集合）。
_SENTENCE_TERMINATORS = ".!?"

#: 句界后随、需一并吞入再 rstrip 的字符（与旧实现一致的边界字符集）。
_CLOSERS = " \t\r\n\"'”‘’()"

#: 缩写词 → 守卫。守卫决定「是否仍按缩写处理（=非句界）」：
#:   "cap"   —— 后随（跳过空白）为大写词（称谓前缀，如 "Mr. Smith"）；
#:   "digit" —— 后随（跳过空白）为数字（编号，如 "No. 5"，本表暂未收录）；
#:   None    —— 恒按缩写处理（无论后随什么）。
#: "no" 刻意不入表：对话里 "No." 常见地是真句，误判为缩写会把答复吞并（听感损失大）。
_ABBREVIATION_GUARDS: dict[str, str | None] = {
    "mr": "cap",
    "mrs": "cap",
    "ms": "cap",
    "dr": "cap",
    "prof": "cap",
    "st": "cap",
    "sr": "cap",
    "jr": None,
    "ave": None,
    "blvd": None,
    "inc": None,
    "ltd": None,
    "corp": None,
    "dept": None,
    "est": None,
    "approx": None,
    "vs": None,
    "etc": None,
}

#: 网址顶级域：句点在它们前面是域名分隔，不是句界。
_WEBSITE_TLDS = frozenset({"com", "net", "org", "io", "gov", "edu", "me"})

#: 括号标签（`[...]`，如 [pause 300ms]、[laugh]、[slow]）：标签内不切。
_BRACKET_TAG_RE = re.compile(r"\[[^\]]*\]")

#: 分句边界（软停顿）：逗号/分号/冒号/破折号。后随空白或行尾才算。
_CLAUSE_BOUNDARY_RE = re.compile(r"[;:,\u2014\u2013](?=\s|$)")


def _inside_bracket_tag(text: str, pos: int) -> bool:
    """``pos`` 是否落在某个 `[...]` 括号标签内。"""
    return any(m.start() < pos < m.end() for m in _BRACKET_TAG_RE.finditer(text))


def _word_before(text: str, pos: int) -> str:
    """返回紧邻 ``pos`` 前的连续字母串（如 "Mr" 之于 "Mr."）。"""
    start = pos - 1
    while start >= 0 and text[start].isalpha():
        start -= 1
    return text[start + 1 : pos]


def _guard_ok(text: str, pos: int, guard: str | None) -> bool:
    """守卫是否满足 → 满足则仍按缩写处理（= 非句界）。

    ``None`` 恒真；``cap``/``digit`` 需后随（跳过空白）大写字母/数字才真。
    """
    if guard is None:
        return True
    j = pos + 1
    while j < len(text) and text[j] in " \t":
        j += 1
    if j >= len(text):
        return False
    if guard == "cap":
        return text[j].isupper()
    if guard == "digit":
        return text[j].isdigit()
    return True


def _is_website_period(text: str, pos: int) -> bool:
    """``.`` 是否属于网址的域名分隔（前是字母、后随顶级域）。"""
    if pos < 1 or not text[pos - 1].isalpha() or pos + 1 >= len(text):
        return False
    m = re.match(r"([A-Za-z]{1,6})", text[pos + 1 :])
    return bool(m and m.group(1).lower() in _WEBSITE_TLDS)


def _is_sentence_period(text: str, pos: int) -> bool:
    """``text[pos] == '.'``；返回 True 表示真句界（否则缩写/小数点/网址等）。"""
    # 中缀符号：'.' 后紧跟非空白（字母/数字）→ 3.5 / U.S / e.g / Ph.D / v2.5
    if pos + 1 < len(text) and text[pos + 1].isalnum():
        return False
    # 单词缩写（'.' 前是字母）：Mr./Dr./St./Inc./etc.，命中缩写表 → 非句界。
    # 注意用 `in` 判断（而非 .get(…) is not None）：dict 值可以是 None（恒缩写），
    # 此时 .get(word) 返回 None 无法区别于"键不存在"。
    if pos >= 1 and text[pos - 1].isalpha():
        word = _word_before(text, pos)
        guard = _ABBREVIATION_GUARDS.get(word.lower())
        if word.lower() in _ABBREVIATION_GUARDS and (guard is None or _guard_ok(text, pos, guard)):
            return False
        # 单字母 / 点分缩写：'.' 前是单个字母，且再往前不是字母
        # （U.S. 的第二个点、J. Smith、Ph.D. 的第二个点；"Mr." 这里不命中，
        #   因为其前"r"前还有字母 "M"——由上面缩写表兜住）
        if pos < 2 or not text[pos - 2].isalpha():
            return False
    # 网址后缀
    return not _is_website_period(text, pos)


def find_sentence_end(text: str) -> int:
    """返回第一个真句界字符（``.!?``）在 ``text`` 中的索引；无则 -1。

    纯函数、无副作用，供 ``StreamSentenceSplitter`` 与后续文本工程复用。
    """
    for i, ch in enumerate(text):
        if ch not in _SENTENCE_TERMINATORS:
            continue
        if _inside_bracket_tag(text, i):
            continue
        if ch == "." and not _is_sentence_period(text, i):
            continue
        return i
    return -1


def _find_clause_boundary(text: str) -> int:
    """返回最后一个分句边界（; : , — ）的索引，无则 -1（且避开括号标签）。"""
    best = -1
    for m in _CLAUSE_BOUNDARY_RE.finditer(text):
        if not _inside_bracket_tag(text, m.start()):
            best = m.start()
    return best


def _safe_hard_cut(seg: str) -> int:
    """在 ``seg`` 尾部硬切，但避开括号 tag（不发一个断在 `[...]` 中间的 chunk）。"""
    cut = len(seg) - 1
    for m in _BRACKET_TAG_RE.finditer(seg):
        if m.start() < cut < m.end():
            return m.start() - 1 if m.start() > 0 else cut
    return cut


def _cut_long(text: str, limit: int) -> tuple[str, str]:
    """超长无标点段切成 (句, 余)。优先分句边界 → 词边界 → 避开 tag 的硬切。"""
    seg = text[:limit]
    cut = _find_clause_boundary(seg)
    if cut == -1:
        cut = seg.rfind(" ")
    if cut <= 0:
        cut = _safe_hard_cut(seg)
    return seg[: cut + 1].strip(), text[cut + 1 :].lstrip()


class StreamSentenceSplitter:
    """流式 TextDelta → 完整句（遇句边界立即出句；flush 收尾句）。

    - 跨 chunk 安全（缓冲累积后统一切分）；
    - 输出句已 strip；空句/纯标点不产出；
    - 输入应为 TurnRunner 泄漏门放行的**纯正文**（META 已被剥离，docs/26）。
    """

    def __init__(self, max_sentence_chars: int = MAX_SENTENCE_CHARS) -> None:
        self._buf = ""
        self._max_chars = max_sentence_chars

    def push(self, delta: str) -> list[str]:
        self._buf += delta
        out: list[str] = []
        while True:
            if len(self._buf) > self._max_chars:
                # 无标点超长句：自然边界（分句/词）优先，兜底硬切（含括号 tag 保护）
                sentence, self._buf = _cut_long(self._buf, self._max_chars)
                if sentence:
                    out.append(sentence)
                continue
            pos = find_sentence_end(self._buf)
            if pos < 0:
                break
            # 边界后随空白/引号/括号一并吞入，再 rstrip 掉句尾边界字符
            end = pos + 1
            while end < len(self._buf) and self._buf[end] in _CLOSERS:
                end += 1
            sentence = self._buf[:end].rstrip(_CLOSERS)
            self._buf = self._buf[end:]
            # 纯标点/空白句不产出（"Wow!!" 的第二个 "!" 不成为独立句子）
            if sentence and any(c.isalnum() for c in sentence):
                out.append(sentence)
        return out

    def flush(self) -> list[str]:
        """流结束：残余无标点文本也作为最后一句（音频/字幕完整闭合）。"""
        rest, self._buf = self._buf.strip(), ""
        return [rest] if rest else []


__all__ = ["StreamSentenceSplitter", "MAX_SENTENCE_CHARS", "find_sentence_end"]
