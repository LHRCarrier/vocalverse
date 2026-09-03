"""Fake 音频/LLM 客户端 —— M1 占位与 CI 打桩（docs/06 第 6 章）。

M2 起按 docs/06 第 8 章替换为真实现：
- ASR → faster-whisper（small/int8/cpu）
- TTS → edge-tts（AZURE_TTS_KEY 存在时切 Azure）
- 评分 → 讯飞 ISE（并发信号量 2）
- LLM → DeepSeek API
"""

from __future__ import annotations

from app.audio.base import ASRClient, ASRResult, LLMClient, ScorerClient, ScoreResult, TTSClient


class FakeASRClient(ASRClient):
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        # 词级时间戳与转写文本逐词对应（"coffee," 后接 1.05s 停顿 → 停顿特征可测）
        return ASRResult(
            text="[stub] hello, I would like a coffee, please.",
            language=language,
            words=[
                {"word": "hello", "start": 0.10, "end": 0.34, "probability": 0.98},
                {"word": "I", "start": 0.42, "end": 0.50, "probability": 0.97},
                {"word": "would", "start": 0.58, "end": 0.86, "probability": 0.99},
                {"word": "like", "start": 0.94, "end": 1.14, "probability": 0.98},
                {"word": "a", "start": 1.22, "end": 1.30, "probability": 0.95},
                {"word": "coffee,", "start": 2.35, "end": 2.72, "probability": 0.99},
                {"word": "please.", "start": 2.80, "end": 2.98, "probability": 0.98},
            ],
            duration=3.2,
        )


class FakeTTSClient(TTSClient):
    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        return b"RIFF__fake_wav_payload__"


class FakeScorerClient(ScorerClient):
    async def score(self, audio_bytes: bytes, reference: str, language: str = "en") -> ScoreResult:
        return ScoreResult(overall=88.0, pronunciation=90.0, fluency=86.0, grammar=85.0)


class FakeLLMClient(LLMClient):
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        return "[stub] That sounds great! What size would you like?"

    async def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ):
        """Fake 流式：分 3 段吐出回复文本 + 尾部 META（与真实现同协议，供全链路测试）。"""
        async for kind, payload in self.stream_rich(messages, temperature, max_tokens):
            if kind == "delta":
                yield payload

    async def stream_rich(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ):
        """Fake 富流：与真实现同事件形状（docs/26 §10.3②：测试用量记账链路）。"""
        from app.practice.meta import render_meta

        chunks = [
            "Of course! Would you like it hot ",
            "or iced? ",
            "That will be four dollars, please.",
        ]
        for c in chunks:
            yield ("delta", c)
        yield ("usage", {"model": "fake", "prompt_tokens": 120, "completion_tokens": 60})
        yield (
            "delta",
            render_meta(
                grammar={"score": 92, "errors": []},
                coach_note="Nice and clear!",
                corpus_hits=[{"phrase": "I would like a coffee, please", "state": "ok"}],
                difficulty_delta=0,
                conclude=False,
            ),
        )
