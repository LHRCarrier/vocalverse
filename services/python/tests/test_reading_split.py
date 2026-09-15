"""读书域 · 分句/归一化纯函数测试（docs/45 §3 权威坐标系；修复前必失败——全新实现）。"""

from __future__ import annotations

from app.reading.normalize import is_lookupable, normalize_word
from app.reading.split import split_chapter, split_paragraph


class TestNormalizeWord:
    def test_lower_and_strip_punctuation(self):
        assert normalize_word("  Alice's, ") == "alice's"

    def test_curly_apostrophe_to_straight(self):
        assert normalize_word("Alice\u2019s") == "alice's"

    def test_hyphen_kept(self):
        assert normalize_word("Well-known") == "well-known"

    def test_quotes_stripped(self):
        assert normalize_word('"hello!"') == "hello"

    def test_not_lookupable(self):
        assert is_lookupable(normalize_word("")) is False
        assert is_lookupable(normalize_word("123")) is False
        assert is_lookupable(normalize_word("---")) is False
        assert is_lookupable(normalize_word("hello")) is True


class TestSplitChapter:
    def test_paragraphs_round_trip(self):
        content = "First paragraph one.\n\nSecond paragraph two.\n\nThird!"
        split = split_chapter(content)
        assert split.paragraphs == [
            "First paragraph one.",
            "Second paragraph two.",
            "Third!",
        ]

    def test_sentence_offsets_continuous(self):
        content = "Hello world. This is fine!\n\nNext para yes."
        split = split_chapter(content)
        assert [s.text for s in split.sentences] == [
            "Hello world.",
            "This is fine!",
            "Next para yes.",
        ]
        # start/end 与 text 精确对应且段间连续（复用可无损重建）
        assert split.sentences[0].start == 0
        assert split.sentences[0].end == 12
        assert split.sentences[1].start == 13
        assert split.sentences[2].start == 28  # 第二段 offset = 25(正文) + 2(\n\n) + 1? 见下断言
        assert split.sentences[2].end == split.sentences[2].start + len("Next para yes.")

    def test_para_idx_maps_paragraph(self):
        content = "A.\n\nB.\n\nC."
        split = split_chapter(content)
        assert [s.para_idx for s in split.sentences] == [0, 1, 2]
        assert [s.idx for s in split.sentences] == [0, 1, 2]

    def test_abbreviation_not_cut(self):
        content = "Mr. Smith went home. He slept."
        split = split_chapter(content)
        assert [s.text for s in split.sentences] == ["Mr. Smith went home.", "He slept."]

    def test_long_sentence_capped(self):
        content = "word " * 200
        split = split_chapter(content, max_sentence_chars=200)
        assert all(len(s.text) <= 210 for s in split.sentences)  # 硬切阈值宽容
        assert len(split.sentences) >= 2

    def test_sentence_by_idx(self):
        split = split_chapter("One. Two. Three.")
        assert split.sentence_by_idx(1).text == "Two."
        assert split.sentence_by_idx(99) is None


class TestSplitParagraph:
    def test_offsets_within_paragraph(self):
        result = split_paragraph(
            "One. Two. Three.", para_idx=0, base=0, start_sentence=0, max_chars=300
        )
        assert len(result) == 3
        first, _ = result[0]
        assert first.start == 0
        assert first.text == "One."
