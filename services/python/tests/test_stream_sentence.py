"""流式句切分器测试（docs/19 P0-5：边生成边合成的前置纯逻辑）。

覆盖：句边界立即出句 / 跨 chunk 拆分 / 无标点长句上限截断 / flush 尾句 /
纯标点句过滤（"Wow!!" 不产出独立 "!" 句）。
"""

from __future__ import annotations

from app.practice.orchestrator import _MAX_SENTENCE_CHARS, StreamSentenceSplitter


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
    assert all(len(x) <= _MAX_SENTENCE_CHARS for x in out)
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
