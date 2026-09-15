"""读书域 · 章节切分纯函数：段落 + 句子 + 章内 char offset 坐标系。

权威口径（数据模型拷问 V-20：offset 以「章节正文整文本」为基准）：
- ``content`` = ``"\\n\\n".join(paragraphs)``（seed 入库即此格式，无归一化改写）；
- ``split_chapter(content) -> ChapterSplit``：
  - ``paragraphs: list[str]`` —— 正文段落（与 content 可无损重建）；
  - ``sentences: list[Sentence]`` —— {idx, text, para_idx, start, end}，
    start/end 为**章内 char offset**（同 reading_annotations.start/end_offset 坐标系）；
- 复用 ``app/audio/textproc/sentence_splitter.py`` 的 ``StreamSentenceSplitter``
  （宁可少切不可误切；缩写/小数/网址/括号标签全部有守卫）；
- 句子 text 已 strip；``end = start + len(text)`` 保证段内顺序句首尾相邻。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.audio.textproc.sentence_splitter import StreamSentenceSplitter

#: 听书单句合成上限（edge-tts 单次约 1000 字符安全；取 320 保持句读自然，
#: 超长无标点句由 splitter 按分句边界/词边界收敛）。
DEFAULT_MAX_SENTENCE_CHARS = 320


@dataclass(frozen=True)
class Sentence:
    idx: int
    text: str
    para_idx: int
    start: int  # 章内 char offset（含）
    end: int  # 章内 char offset（不含）


@dataclass
class ChapterSplit:
    paragraphs: list[str] = field(default_factory=list)
    sentences: list[Sentence] = field(default_factory=list)

    def sentence_by_idx(self, idx: int) -> Sentence | None:
        if 0 <= idx < len(self.sentences):
            return self.sentences[idx]
        return None


def split_paragraph(
    para_text: str, para_idx: int, base: int, start_sentence: int, max_chars: int
) -> list[tuple[Sentence, int]]:
    """单段 → [(Sentence, 段内句末光标)]；``base`` 为段首章内 offset。"""
    splitter = StreamSentenceSplitter(max_sentence_chars=max_chars)
    out: list[tuple[Sentence, int]] = []
    cursor = base
    for s in splitter.push(para_text):
        # 段内定位：从句文本在 para 中的位置反推（push 已 strip，用 find 逐句前进）
        rel = para_text.find(s, cursor - base)
        if rel < 0:
            rel = 0
        start = base + rel
        out.append(
            (
                Sentence(
                    idx=start_sentence + len(out),
                    text=s,
                    para_idx=para_idx,
                    start=start,
                    end=start + len(s),
                ),
                cursor,
            )
        )
        cursor = start + len(s)
    for s in splitter.flush():
        rel = para_text.find(s, cursor - base)
        if rel < 0:
            rel = 0
        start = base + rel
        out.append(
            (
                Sentence(
                    idx=start_sentence + len(out),
                    text=s,
                    para_idx=para_idx,
                    start=start,
                    end=start + len(s),
                ),
                cursor,
            )
        )
        cursor = start + len(s)
    return out


def split_chapter(
    content: str, max_sentence_chars: int = DEFAULT_MAX_SENTENCE_CHARS
) -> ChapterSplit:
    """章节正文 → 段落 + 句子（idx 自 0 起；start/end 为章内 char offset）。"""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    split = ChapterSplit(paragraphs=paragraphs)
    base = 0
    for pi, para in enumerate(paragraphs):
        for sentence, _ in split_paragraph(
            para, pi, base, len(split.sentences), max_sentence_chars
        ):
            split.sentences.append(sentence)
        base += len(para) + 2  # 跳过 \n\n 分隔
    return split


__all__ = [
    "ChapterSplit",
    "Sentence",
    "split_chapter",
    "split_paragraph",
    "DEFAULT_MAX_SENTENCE_CHARS",
]
