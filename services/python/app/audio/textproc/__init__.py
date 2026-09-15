"""TTS 文本工程层（engine-agnostic，纯逻辑）。

把「文本 → 可合成文本」的纯字符串处理与引擎/网络解耦：
- :mod:`sentence_splitter`：流式句切分（句界 / 缩写 / 小数点 / 网址 / 长句截断）。
- :mod:`normalize`：文本归一化（缩写展开 / 数字→单词 / 零宽与重复标点清理），幂等、绝不抛错。
- 后续扩展（发音词典、ssml-lite 语速标记）同归本层，见 docs/44。
"""

from app.audio.textproc.normalize import normalize_for_tts, normalize_text
from app.audio.textproc.sentence_splitter import (
    MAX_SENTENCE_CHARS,
    StreamSentenceSplitter,
    find_sentence_end,
)

__all__ = [
    "MAX_SENTENCE_CHARS",
    "StreamSentenceSplitter",
    "find_sentence_end",
    "normalize_for_tts",
    "normalize_text",
]
