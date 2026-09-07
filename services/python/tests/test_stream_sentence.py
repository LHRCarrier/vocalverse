"""流式句切分器测试（docs/19 P0-5：边生成边合成的前置纯逻辑）。

覆盖：句边界立即出句 / 跨 chunk 拆分 / 无标点长句上限截断 / flush 尾句 /
纯标点句过滤（"Wow!!" 不产出独立 "!" 句）。
"""

from __future__ import annotations

from app.audio.textproc.sentence_splitter import MAX_SENTENCE_CHARS, StreamSentenceSplitter


def test_boundary_emits_sentence_and_keeps_rest() -> None:
    s = StreamSentenceSplitter()
    assert s.push("Hello! How") == ["Hello!"]
    assert s.push(" are you? I'm fine.") == ["How are you?", "I'm fine."]
    assert s.flush() == []


def test_emits_multiple_sentences_in_one_delta() -> None:
    s = StreamSentenceSplitter()
    assert s.push("One. Two? Three!") == ["One.", "Two?", "Three!"]
    assert s.flush() == []


def test_cross_chunk_boundary() -> None:
    """标点跨 chunk（"Hello" + "! world" 分两次到达）必须合并出句。"""
    s = StreamSentenceSplitter()
    assert s.push("Hello") == []
    assert s.push("! world") == ["Hello!"]


def test_punctuation_with_trailing_whitespace_and_quotes() -> None:
    """边界吞并后随空白/引号（句尾引号归入句子），残余不再带引号。"""
    s = StreamSentenceSplitter()
    assert s.push('Great job!  "Next,') == ["Great job!"]
    assert s.flush() == ["Next,"]


def test_long_sentence_without_punctuation_truncates_at_word_boundary() -> None:
    """健壮性：无标点超长句在词边界强制切分，防单句合成尖峰。"""
    s = StreamSentenceSplitter()
    text = " ".join(["word"] * 200)  # 远超上限
    out = s.push(text)
    assert out
    assert all(len(x) <= MAX_SENTENCE_CHARS for x in out)
    assert s.flush()  # 残余还能收尾一句


def test_flush_emits_tail_without_punctuation() -> None:
    s = StreamSentenceSplitter()
    s.push("Hello there")
    assert s.flush() == ["Hello there"]
    assert s.flush() == []  # 幂等


def test_empty_delta_ignored() -> None:
    s = StreamSentenceSplitter()
    assert s.push("   ") == []
    assert s.push("") == []
    assert s.flush() == []


def test_double_punctuation_no_stray_sentence() -> None:
    """ "Wow!!" 第二个 '!' 不产出独立句子（纯标点句过滤）。"""
    s = StreamSentenceSplitter()
    assert s.push("Wow!! Really?") == ["Wow!", "Really?"]
    assert s.flush() == []


# ---------------------------------------------------------------------------
# P0-A 回归测试（vtts-03）：缩写点 / 小数点 / 网址 / 点分缩写不得当句号切
# 旧实现 `_SENTENCE_END_RE=[.!?][\s…]*` 对以下全部误拆 → 修复前必失败。
# ---------------------------------------------------------------------------


def test_titular_abbreviation_not_split() -> None:
    """ "Mr." / "Dr." 为称谓前缀，不得切句；整句作为一句。"""
    s = StreamSentenceSplitter()
    assert s.push("Mr. Smith went to the store.") == ["Mr. Smith went to the store."]
    assert s.flush() == []


def test_multiple_honorifics_not_split() -> None:
    s = StreamSentenceSplitter()
    assert s.push("Dr. Smith and Prof. Lee left.") == ["Dr. Smith and Prof. Lee left."]
    assert s.flush() == []


def test_decimal_not_split() -> None:
    """ "3.5" 的小数点不是句界；句末句号才是。"""
    s = StreamSentenceSplitter()
    assert s.push("It's 3.5 miles away.") == ["It's 3.5 miles away."]
    assert s.flush() == []


def test_acronym_not_split() -> None:
    """ "U.S." 的点分缩写不是句界。"""
    s = StreamSentenceSplitter()
    assert s.push("The U.S. economy grew.") == ["The U.S. economy grew."]
    assert s.flush() == []


def test_degree_abbreviation_not_split() -> None:
    s = StreamSentenceSplitter()
    assert s.push("He earned a Ph.D. in physics.") == ["He earned a Ph.D. in physics."]
    assert s.flush() == []


def test_connector_abbreviation_not_split() -> None:
    """ "e.g." / "etc." 不是句界（无后续真句界时整体收在 flush 尾句）。"""
    s = StreamSentenceSplitter()
    assert s.push("I like tea, e.g. green tea, etc.") == []
    assert s.flush() == ["I like tea, e.g. green tea, etc."]


def test_integer_score_still_splits() -> None:
    """ "98." 是整数+句号（真句界），"98." 后应切分（区别于小数 3.5）。"""
    s = StreamSentenceSplitter()
    assert s.push("I scored 98. Good job.") == ["I scored 98.", "Good job."]
    assert s.flush() == []


def test_website_period_not_split() -> None:
    """ ".com" 的域名点不是句界。"""
    s = StreamSentenceSplitter()
    assert s.push("Visit example.com today.") == ["Visit example.com today."]
    assert s.flush() == []


def test_punctuation_inside_bracket_tag_ignored() -> None:
    """句界落在 `[...]` 括号标签内不切；标签外的句点/叹号正常切。"""
    s = StreamSentenceSplitter()
    assert s.push("He said [laugh!] and continued. Thanks!") == [
        "He said [laugh!] and continued.",
        "Thanks!",
    ]
    assert s.flush() == []
