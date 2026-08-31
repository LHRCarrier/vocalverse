"""音频管线抽象接口 —— 依赖注入 + TESTING 时注入 Fake（docs/06 第 6 章）。

CI 零真实 API Key：ASR/TTS/评分/LLM 全部可打桩。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ASRResult:
    text: str
    language: str = "en"
    confidence: float = 0.0
    segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScoreResult:
    overall: float
    pronunciation: float
    fluency: float
    grammar: float | None = None  # None = 未启用语法项（LLM 判定）
    completeness: float | None = None
    word_level: list[dict[str, Any]] = field(default_factory=list)


class ASRClient(abc.ABC):
    """语音识别接口（默认 faster-whisper small int8 CPU）。"""

    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        raise NotImplementedError


class TTSClient(abc.ABC):
    """语音合成接口（默认 edge-tts，Azure 备胎）。"""

    @abc.abstractmethod
    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        raise NotImplementedError


class ScorerClient(abc.ABC):
    """发音评分接口（默认讯飞 ISE 基线；wav2vec2 门禁通过后替换）。"""

    @abc.abstractmethod
    async def score(self, audio_bytes: bytes, reference: str, language: str = "en") -> ScoreResult:
        raise NotImplementedError


class LLMClient(abc.ABC):
    """LLM 客户端（DeepSeek；场景扮演/语法判定/报告生成）。"""

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        raise NotImplementedError


def get_asr_client() -> ASRClient:
    from app.audio.stubs import FakeASRClient

    return FakeASRClient()


def get_tts_client() -> TTSClient:
    from app.audio.stubs import FakeTTSClient

    return FakeTTSClient()


def get_scorer_client() -> ScorerClient:
    from app.audio.stubs import FakeScorerClient

    return FakeScorerClient()


def get_llm_client() -> LLMClient:
    from app.audio.stubs import FakeLLMClient

    return FakeLLMClient()
