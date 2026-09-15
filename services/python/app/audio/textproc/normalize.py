"""文本归一化（engine-agnostic 纯逻辑，独立模块）——TTS 前处理层。

定位：把「可能读错」的原文清洗成「引擎一定能读对」的文本，与引擎/网络解耦。
与 :mod:`sentence_splitter` 同归 `app/audio/textproc/`（docs/44 P1-A）。

设计规则（load-bearing）：

* **保守**：假阴性（数字没转词）可接受；假阳性（意思被改坏）不可接受。凡有歧义的
  数字（千分位 "1,000"、区间 "3-5"、版本号 "v2"/"3.5.1"、前导零 "007"、7+ 位 ID）一律不改。
* **幂等**：``normalize_for_tts(normalize_for_tts(x)) == normalize_for_tts(x)``——
  数字/缩写输出不再含可再匹配的 token，重复经过流水线无害。
* **绝不抛错**：任何异常回退原文（归一化永远不能打断合成，VS 同款契约）。
* **标记安全**：单括号 ``[...]``（如 ``[pause 300ms]``、``[voice:..]``）与双括号
  ``[[term|replacement]]`` 发音覆盖一律跳过（同 chunked_tts 的 ``_BRACKET_TAG_RE`` 形状），
  保证后续 ssml-lite / 发音词典层有标记可解析。
* **越界防护**：数字转换只处理「明确可读」的情形，年份/序数/货币仅英文（其读法与语言相关）。

当前仅实现英文（``language="en"``）；多语言结构已预留（``_LANG_RULES``）。
"""

from __future__ import annotations

import re

# ── 安全过滤（所有语言）──────────────────────────────────────────────────────────

# 零宽 / bidi 控制符、C0/C1（除 \t \n \r）、BOM、U+FFFD。显式枚举，避免误伤空格控制。
_UNSAFE_CONTROLS = frozenset(
    (
        *range(0x00, 0x09),
        0x0B,
        0x0C,
        *range(0x0E, 0x20),
        *range(0x7F, 0xA0),
        *range(0x200B, 0x2010),
        *range(0x202A, 0x202F),
        *range(0x2060, 0x2065),
        0xFEFF,
        0xFFFD,
    )
)
_UNSAFE_TRANSLATION = dict.fromkeys(_UNSAFE_CONTROLS)

# 常见的语义空转 HTML 实体子集（&amp; 仅在非 &letter/# 时解码，保幂等）。
_ENTITIES = {
    "&nbsp;": " ",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&hellip;": "…",
    "&mdash;": "—",
    "&ndash;": "–",
}
_ENTITY_RE = re.compile("(?:" + "|".join(re.escape(k) for k in _ENTITIES) + "|&amp;(?![a-zA-Z#]))")

# 同一 ASCII 标点重复 >3 次 → 封顶 3（"!!!!!!!!" 造成死寂/口吃）。
_REPEAT_RE = re.compile(r"([!?.,;:~_*#=-])\1{3,}")

_HSPACE_RE = re.compile(r"[^\S\n]+")  # 横向空白串 → 单空格
_NEWLINE_RE = re.compile(r"\n{3,}")  # 空行洪泛 → 单空行


def _safety_filters(text: str) -> str:
    out = text.translate(_UNSAFE_TRANSLATION)
    out = _ENTITY_RE.sub(lambda m: _ENTITIES.get(m.group(0), "&"), out)
    out = _REPEAT_RE.sub(lambda m: m.group(1) * 3, out)
    out = _HSPACE_RE.sub(" ", out)
    out = _NEWLINE_RE.sub("\n\n", out)
    return out.strip()


# ── 括号掩码：语言规则跳过 [...] / [[...]] 段 ──────────────────────────────────────

_BRACKET_SPAN_RE = re.compile(r"\[[^\]\n]{0,128}\]")


def _outside_brackets(text: str, fn) -> str:
    """只在括号外应用 ``fn``，括号内原文保留（标记语法原样，供后续层解析）。"""
    if "[" not in text:
        return fn(text)
    parts: list[str] = []
    last = 0
    for m in _BRACKET_SPAN_RE.finditer(text):
        parts.append(fn(text[last : m.start()]))
        parts.append(m.group(0))
        last = m.end()
    parts.append(fn(text[last:]))
    return "".join(parts)


# ── 缩写展开（英文，带 cap/digit 守卫）─────────────────────────────────────────────

# key → (expansion, guard)。guard: "cap"=后随大写词(称谓前缀)；"digit"=后随数字(编号)；None=恒配。
_ABBREVIATIONS_EN: dict[str, tuple[str, str | None]] = {
    "Dr.": ("Doctor", "cap"),
    "Mr.": ("Mister", "cap"),
    "Mrs.": ("Missus", "cap"),
    "Prof.": ("Professor", "cap"),
    "St.": ("Saint", "cap"),
    "Mt.": ("Mount", "cap"),
    "Jr.": ("Junior", None),
    "Sr.": ("Senior", None),
    "vs.": ("versus", None),
    "etc.": ("et cetera", None),
    "e.g.": ("for example", None),
    "i.e.": ("that is", None),
    "approx.": ("approximately", None),
}

_GUARD_LOOKAHEAD = {
    None: "",
    "cap": r"(?=\s+[A-Z])",
    "digit": r"(?=\s*\d)",
}


def _compile_abbreviations() -> tuple[re.Pattern, dict[str, str]]:
    keys = sorted(_ABBREVIATIONS_EN, key=len, reverse=True)
    lookup: dict[str, str] = {}
    alts: list[str] = []
    for key in keys:
        expansion, guard = _ABBREVIATIONS_EN[key]
        lookup[key.casefold()] = expansion
        suffix = r"(?!\w)" if key[-1:].isalnum() else ""
        alts.append(f"{re.escape(key)}{suffix}{_GUARD_LOOKAHEAD[guard]}")
    # (?<!\w.) 避免把 "aDr." 之类中段当缩写；无嵌套量词 → 线性无 ReDoS。
    pattern = re.compile(r"(?<![\w.])(?:" + "|".join(alts) + ")", re.IGNORECASE)
    return pattern, lookup


_ABBREV_PATTERN, _ABBREV_LOOKUP = _compile_abbreviations()


def _expand_abbreviations(text: str) -> str:
    def _repl(m: re.Match) -> str:
        return _ABBREV_LOOKUP.get(m.group(0).casefold(), m.group(0))

    return _ABBREV_PATTERN.sub(_repl, text)


# ── 数字 → 单词（英文，覆盖 百分比/小数/整数/年份/序数/货币）─────────────────────────

# 所有匹配要求干净词边界；粘字母 ("MP3","v2")、千分位 ("1,000")、区间 ("3-5")、前导零 ("007")、
# 7+ 位 ID 一律不改（保守）。
_PERCENT_RE = re.compile(r"(?<![\w.,])(\d{1,4}(?:\.\d{1,2})?)\s?%")
_DECIMAL_RE = re.compile(r"(?<![\w.,:/$%-])(\d{1,3})\.(\d{1,3})(?![\w:/%-])(?![.,]\d)")
_INTEGER_RE = re.compile(r"(?<![\w.,:/$%-])(?!0\d)(\d{1,6})(?![\w:/%-])(?![.,]\d)")
_ORDINAL_RE = re.compile(r"(?<![\w.,])(\d{1,4})(st|nd|rd|th)\b")
_CURRENCY_RE = re.compile(r"(?<!\w)\$(\d{1,4}(?:\.\d{2})?)(?![\d.,])")

_ORDINAL_SUFFIX = {1: "st", 2: "nd", 3: "rd"}


def _correct_ordinal_suffix(n: int) -> str:
    if 10 <= n % 100 <= 13:
        return "th"
    return _ORDINAL_SUFFIX.get(n % 10, "th")


def _num2words(value, **kw) -> str:
    """委托 num2words；任何异常都让调用方以原文兜底（保守，绝不 mangle）。"""
    from num2words import num2words

    return num2words(value, lang="en", **kw)


def _numbers_to_words(text: str) -> str:
    def _safe(m: re.Match, render) -> str:
        try:
            return render(m)
        except Exception:  # noqa: BLE001 — 保守：一次转换失败不改变整段
            return m.group(0)

    # 百分比：50% → fifty percent
    def _percent(m: re.Match) -> str:
        raw = m.group(1)
        value = float(raw) if "." in raw else int(raw)
        return f"{_num2words(value)} percent"

    text = _PERCENT_RE.sub(lambda m: _safe(m, _percent), text)

    # 小数：3.5 → three point five
    def _decimal(m: re.Match) -> str:
        return _num2words(float(f"{m.group(1)}.{m.group(2)}"))

    text = _DECIMAL_RE.sub(lambda m: _safe(m, _decimal), text)

    # 序数：2nd → second
    def _ordinal(m: re.Match) -> str:
        n = int(m.group(1))
        if m.group(2) != _correct_ordinal_suffix(n):
            return m.group(0)
        return _num2words(n, to="ordinal")

    text = _ORDINAL_RE.sub(lambda m: _safe(m, _ordinal), text)

    # 货币：$10 → ten dollars
    def _currency(m: re.Match) -> str:
        raw = m.group(1)
        if "." in raw:
            amount = float(raw)
            return f"{_num2words(amount, to='currency', currency='USD')}"
        n = int(raw)
        unit = "dollar" if n == 1 else "dollars"
        return f"{_num2words(n)} {unit}"

    text = _CURRENCY_RE.sub(lambda m: _safe(m, _currency), text)

    # 整数（含年份）：1500-2099 的裸 4 位数读成年份，其余读成基数词
    def _integer(m: re.Match) -> str:
        raw = m.group(1)
        n = int(raw)
        if len(raw) == 4 and 1500 <= n <= 2099:
            return _num2words(n, to="year")
        return _num2words(n)

    text = _INTEGER_RE.sub(lambda m: _safe(m, _integer), text)
    return text


# ── 语言规则分发 ─────────────────────────────────────────────────────────────────

_LANG_RULES = {
    "en": (_expand_abbreviations, _numbers_to_words),
}


def _lang_code(language: str | None) -> str:
    if not language:
        return "en"
    s = str(language).strip().lower()
    if s in ("auto", "-"):
        return "en"
    return s[:2]


def normalize_text(text: str, language: str | None = None) -> str:
    """纯归一化（无门控）；幂等、不抛错。供单测与门控入口复用。"""
    if not text:
        return text or ""
    lang = _lang_code(language)
    out = _safety_filters(text)
    rules = _LANG_RULES.get(lang)
    if rules:
        for rule in rules:
            out = _outside_brackets(out, rule)
    return out


def normalize_for_tts(text: str, language: str | None = None) -> str:
    """TTS 入口：门控 + 硬化。任何异常回退原文（归一化绝不能打断合成）。"""
    if not text:
        return text or ""
    try:
        return normalize_text(text, language)
    except Exception:  # noqa: BLE001 — 保守兜底
        return text


__all__ = ["normalize_for_tts", "normalize_text"]
