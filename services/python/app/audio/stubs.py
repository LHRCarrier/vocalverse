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
        return ASRResult(text="[stub] hello, I would like a coffee, please.", language=language)


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
