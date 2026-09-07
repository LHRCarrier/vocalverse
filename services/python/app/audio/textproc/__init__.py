"""TTS 文本工程层（engine-agnostic，纯逻辑）。

把「文本 → 可合成文本」的纯字符串处理与引擎/网络解耦：
- :mod:`sentence_splitter`：流式句切分（句界 / 缩写 / 小数点 / 网址 / 长句截断）。
- 后续扩展（文本归一化、发音词典、ssml-lite 语速标记）同归本层，见 docs/44。
"""

from app.audio.textproc.sentence_splitter import (
    MAX_SENTENCE_CHARS,
    StreamSentenceSplitter,
    find_sentence_end,
)

__all__ = ["MAX_SENTENCE_CHARS", "StreamSentenceSplitter", "find_sentence_end"]
