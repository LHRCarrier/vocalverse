"""faster-whisper 词级时间戳抽取回归（docs/06 §9.3；2026-09-04 联调 BUG 实测归档）。

根因：`model.transcribe()` 返回的是**生成器**；`transcribe_sync` 先「拉平文本」
（`''.join(s.text for s in segments)`）再「遍历取词」——第二次迭代同一生成器恒为空
→ `words` 恒 []（且旧代码 `ASRResult.segments` 同样恒 []，因无消费方而未被发现）。

本测试用假模型（与 faster-whisper 同款「返回生成器」+ 校验 word_timestamps 透传）
钉住「生成器只物化一次」的契约：**修复前该测试必红（words == []），修复后绿**。
"""

from __future__ import annotations

from app.audio.asr import FasterWhisperClient


class _FakeInfo:
    language = "en"
    language_probability = 0.99
    duration = 2.0


class _Word:
    def __init__(self, word: str, start: float, end: float, probability: float):
        self.word = word
        self.start = start
        self.end = end
        self.probability = probability


class _Seg:
    def __init__(self, text: str, start: float, end: float, words: list[_Word]):
        self.text = text
        self.start = start
        self.end = end
        self.words = words


class _FakeModel:
    """返回 (生成器, info)——与 faster-whisper 行为一致；记录调用参数供断言。"""

    def __init__(self):
        self.calls: list[dict] = []

    def transcribe(self, wav_path, language="en", beam_size=5, word_timestamps=False):
        self.calls.append(
            {
                "wav": wav_path,
                "language": language,
                "beam_size": beam_size,
                "word_timestamps": word_timestamps,
            }
        )

        def gen():
            yield _Seg(
                "Hello world.",
                0.0,
                1.0,
                [_Word(" Hello", 0.0, 0.5, 0.98), _Word(" world.", 0.6, 1.0, 0.95)],
            )
            yield _Seg(" Goodbye.", 1.2, 1.8, [_Word(" Goodbye.", 1.2, 1.8, 0.92)])

        return gen(), _FakeInfo()


def test_transcribe_sync_extracts_words_and_segments() -> None:
    """生成器只物化一次：words/segments 均从同一份段列表抽取。"""
    client = FasterWhisperClient()
    fake = _FakeModel()
    client._model = fake  # 跳过延迟加载（真模型不属于 CI 轻量测试）

    res = client.transcribe_sync("x.wav", "en")

    assert fake.calls[-1]["word_timestamps"] is True, "word_timestamps 必须透传（特征数据源）"
    assert res.text == "Hello world. Goodbye."
    assert len(res.words) == 3
    assert res.words[0] == {"word": " Hello", "start": 0.0, "end": 0.5, "probability": 0.98}
    assert res.words[2] == {"word": " Goodbye.", "start": 1.2, "end": 1.8, "probability": 0.92}
    assert len(res.segments) == 2  # 旧代码此处恒 []（同一根因）
    assert res.duration == 2.0
    assert res.language == "en"
    assert res.confidence == 0.99
