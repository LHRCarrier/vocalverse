"""文本归一化测试（docs/44 P1-A；app/audio/textproc/normalize.py）。

覆盖：缩写展开(cap 守卫) / 数字→单词(百分比/小数/序数/货币/年份/整数) /
保守不改(粘字母/千分位/区间/版本号/前导零) / 幂等 / 括号标记保留 / 绝不抛错。
"""

from __future__ import annotations

from app.audio.textproc.normalize import normalize_for_tts, normalize_text


def test_abbreviation_expansion_with_cap_guard() -> None:
    """称谓前缀仅在后随大写词时展开（cap 守卫），Dr./Mr. 读成 Doctor/Mister。"""
    assert normalize_text("Dr. Smith") == "Doctor Smith"
    assert normalize_text("Mr. Smith went home.") == "Mister Smith went home."
    assert normalize_text("Prof. Lee left.") == "Professor Lee left."


def test_abbreviation_guarded_not_expanded_without_capital() -> None:
    """非称谓（后随小写/非大写）不展开——保守，避免误改（如 "Elm St. is" 的 St.）。"""
    # "No." 未入表，不展开（对话答复常见真句）。
    assert normalize_text("No. I disagree.") == "No. I disagree."


def test_connector_abbreviation_expansion() -> None:
    assert normalize_text("etc.") == "et cetera"
    assert normalize_text("e.g. apples") == "for example apples"
    assert normalize_text("i.e. that") == "that is that"


def test_percent_to_words() -> None:
    assert normalize_text("50%") == "fifty percent"
    assert normalize_text("3.5%") == "three point five percent"


def test_decimal_to_words() -> None:
    assert normalize_text("3.5") == "three point five"
    assert normalize_text("It's 2.5 km away.") == "It's two point five km away."


def test_ordinal_to_words() -> None:
    assert normalize_text("2nd") == "second"
    assert normalize_text("3rd place") == "third place"
    assert normalize_text("21st") == "twenty-first"


def test_currency_to_words() -> None:
    assert normalize_text("$10") == "ten dollars"
    assert normalize_text("$1") == "one dollar"


def test_integer_and_year() -> None:
    assert normalize_text("I have 42.") == "I have forty-two."
    assert normalize_text("in 2024") == "in twenty twenty-four"


def test_conservative_not_mangled() -> None:
    """保守：粘字母/千分位/区间/版本号/前导零一律不改（假阴性可接受）。"""
    assert normalize_text("v2.5") == "v2.5"
    assert normalize_text("MP3") == "MP3"
    assert normalize_text("1,000") == "1,000"
    assert normalize_text("3-5") == "3-5"
    assert normalize_text("007") == "007"
    assert normalize_text("version 3.5.1") == "version 3.5.1"


def test_contraction_left_alone() -> None:
    """缩写式（I'll/We're）不做归一（edge-tts 原生可读），避免过度处理。"""
    assert normalize_text("I'll be there.") == "I'll be there."
    assert normalize_text("We're ready.") == "We're ready."


def test_idempotent() -> None:
    """normalize(normalize(x)) == normalize(x)。"""
    for x in [
        "50%",
        "3.5",
        "Dr. Smith",
        "in 2024",
        "Bring some, e.g. apples, etc.",
        "  hello   world  ",
    ]:
        once = normalize_text(x)
        assert normalize_text(once) == once, x


def test_bracket_markup_preserved() -> None:
    """[...] 括号标记原样保留，数字/归一不进入括号内（供 ssml-lite/发音词典后续解析）。"""
    assert normalize_text("He said [pause 300ms] 3.5 ok.") == (
        "He said [pause 300ms] three point five ok."
    )
    assert normalize_text("Go to [[St. Louis|Saint Louis]] now.") == (
        "Go to [[St. Louis|Saint Louis]] now."
    )


def test_safety_filters() -> None:
    """零宽/连续标点/空白规整；重复标点封顶 3。"""
    assert normalize_text("  hello   world  ") == "hello world"
    assert normalize_text("Wow!!!!") == "Wow!!!"
    assert normalize_text("hello\u200b world") == "hello world"


def test_never_raise() -> None:
    """归一化绝不能打断合成：空/None/非字符串回退原文。"""
    assert normalize_for_tts(None) == ""
    assert normalize_for_tts("") == ""
    assert normalize_for_tts("  ") == ""
    assert normalize_for_tts(12345) == 12345  # type: ignore[arg-type]
