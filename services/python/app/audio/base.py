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
    # 词级时间戳（faster-whisper word_timestamps=True）：[{word, start, end, probability}]
    # —— 流利度时间戳特征（wpm/停顿）的数据源（docs/06 §9.3 辅助口径），无时间戳实现返回 []
    words: list[dict[str, Any]] = field(default_factory=list)
    duration: float = 0.0  # 音频总时长（秒；whisper info.duration，未知为 0）


@dataclass
class ScoreResult:
    overall: float
    pronunciation: float
    fluency: float
    grammar: float | None = None  # None = 未启用语法项（LLM 判定）
    completeness: float | None = None
    word_level: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TTSResult:
    """TTS 响应数据。M1 stub 为 hex 字符串；M2 真 TTS 改二进制/URL 时更新契约（docs/06 §8）。"""

    audio_bytes: str  # hex（stub 阶段）
    length: int


@dataclass
class ChatResult:
    """LLM 场景扮演单轮回复。M2 多轮/流式扩展时更新契约（docs/06 §8）。"""

    reply: str


class ASRClient(abc.ABC):
    """语音识别接口（默认 faster-whisper small int8 CPU）。"""

    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
        raise NotImplementedError


class TTSClient(abc.ABC):
    """语音合成接口（默认 edge-tts，Azure 备胎）。

    生命周期契约（docs/44 P0-B）：带默认实现，子类/``FakeTTSClient`` 无需覆写即兼容。
    调用方应先 ``is_available()`` 再 ``synthesize``，不可用时给出可读降级而非静默/500。
    """

    @abc.abstractmethod
    async def synthesize(
        self, text: str, voice: str = "en-US-JennyNeural", rate: str = "+0%"
    ) -> bytes:
        raise NotImplementedError

    def is_available(self) -> tuple[bool, str]:
        """引擎能否在当前环境运行。默认 (True, "")；子类可报 (False, 可读原因)。"""
        return True, ""

    def ensure_ready(self) -> None:
        """预热模型/连接（阻塞，LOAD 预算与 GENERATE 预算分离）。默认 no-op。"""
        return None

    def unload(self) -> None:
        """释放引擎持有资源（模型/连接/显存）。默认 no-op，幂等。"""
        return None


class ScorerClient(abc.ABC):
    """发音评分接口（默认讯飞 ISE 基线；wav2vec2 门禁通过后替换）。"""

    @abc.abstractmethod
    async def score(self, audio_bytes: bytes, reference: str, language: str = "en") -> ScoreResult:
        raise NotImplementedError


class LLMClient(abc.ABC):
    """LLM 客户端（DeepSeek；场景扮演/语法判定/报告生成/答辩知识包）。

    - ``chat``：非流式（答辩知识包生成、报告生成等一次性 JSON 输出）；
    - ``stream``：流式（对话回复：纯文本 + 尾部 [-META-] 标记块，docs/14 §3.4）。
    """

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        raise NotImplementedError

    @abc.abstractmethod
    def stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.6,
        max_tokens: int = 512,
    ):
        """流式输出：异步迭代器逐段产出文本（含 [-META-] 尾部标记）。"""
        raise NotImplementedError


def get_asr_client() -> ASRClient:
    settings = _settings()
    if settings.testing or not settings.asr_model:
        from app.audio.stubs import FakeASRClient

        return FakeASRClient()
    from app.audio.asr import FasterWhisperClient

    return FasterWhisperClient(
        model=settings.asr_model, device=settings.asr_device, compute_type=settings.asr_compute_type
    )


def get_tts_client() -> TTSClient:
    settings = _settings()
    if settings.testing:
        from app.audio.stubs import FakeTTSClient

        return FakeTTSClient()

    provider = (settings.tts_provider or "edge").lower()
    if provider == "azure":
        # docs/44 P0-C：Azure 备胎尚未接线。返回一个显式「未接线」客户端，
        # 让其 is_available()==(False, 可读原因) —— 调用方可据此干净降级，而非 500/静默用 edge。
        from app.audio.tts import AzureNotWiredClient

        return AzureNotWiredClient()
    from app.audio.tts import EdgeTTSClient

    return EdgeTTSClient(voice=settings.tts_voice, rate=settings.tts_rate)


def get_scorer_client() -> ScorerClient:
    settings = _settings()
    if settings.testing or not (settings.ise_app_id and settings.ise_api_key):
        from app.audio.stubs import FakeScorerClient

        return FakeScorerClient()
    from app.audio.ise import ISEClient

    return ISEClient(
        app_id=settings.ise_app_id,
        api_key=settings.ise_api_key,
        api_secret=settings.ise_api_secret,
    )


def get_llm_client() -> LLMClient:
    settings = _settings()
    if settings.testing or not settings.deepseek_api_key:
        from app.audio.stubs import FakeLLMClient

        return FakeLLMClient()
    from app.audio.llm import DeepSeekLLMClient

    return DeepSeekLLMClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
    )


def _settings():
    from app.core.config import get_settings

    return get_settings()
