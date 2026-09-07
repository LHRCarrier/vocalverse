"""音频管线抽象接口 —— 依赖注入 + TESTING 时注入 Fake（docs/06 第 6 章）。

CI 零真实 API Key：ASR/TTS/评分/LLM 全部可打桩。
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("vocalverse")


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
    # vasr-10 判别位：No speech（静音/无话语，whisper no_speech_prob>0.7 或空转写）——
    # 与「失败」区分：前端提示按此走「似乎没说话」而非「听不清请重说」，避免反复重试
    no_speech: bool = False


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
    if settings.testing:
        from app.audio.stubs import FakeScorerClient

        return FakeScorerClient()
    if not (settings.ise_app_id and settings.ise_api_key):
        # va-08：生产缺 Key 时的行为按 app_env 分级——
        #  development（演示/联调，.env.example 默认）：Fake 保底可跑完整流程，但**告警**
        #   并打显式标识（假分不再零痕迹流入 skill/推荐链）；
        #  production：**fail-fast**（UnavailableScorerClient，score() 抛可读错误 → 评分链路
        #   明确降级「未评测」），杜绝「固定 88/90/86/85 以真分身份入库」的静默污染。
        from app.audio.stubs import FakeScorerClient, UnavailableScorerClient

        if settings.app_env == "production":
            logger.warning(
                "ISE 未配置（app_env=production）→ 评分不可用（fail-fast 降级为未评测，"
                "防止假分污染 skill/推荐链）"
            )
            return UnavailableScorerClient("ISE not configured (app_env=production)")
        logger.warning(
            "ISE 未配置（app_env=%s）→ 演示降级 Fake 评分（is_fake 标识，勿用于生产）",
            settings.app_env,
        )
        return FakeScorerClient()
    from app.audio.ise import ISEClient

    return ISEClient(
        app_id=settings.ise_app_id,
        api_key=settings.ise_api_key,
        api_secret=settings.ise_api_secret,
    )


#: LLM 客户端实例缓存（py-05：httpx.AsyncClient 连接池必须常驻 —— 每次新建 = 每调用
#: 一次 TCP+TLS 握手；缓存键 = (api_key 哈希, base_url, model)，进程生命周期复用）。
_LLM_CLIENT_CACHE: tuple | None = None


def get_llm_client() -> LLMClient:
    global _LLM_CLIENT_CACHE
    settings = _settings()
    if settings.testing or not settings.deepseek_api_key:
        from app.audio.stubs import FakeLLMClient

        return FakeLLMClient()
    key = (settings.deepseek_api_key, settings.deepseek_base_url, settings.deepseek_model)
    if _LLM_CLIENT_CACHE is None or _LLM_CLIENT_CACHE[0] != key:
        from app.audio.llm import DeepSeekLLMClient

        _LLM_CLIENT_CACHE = (
            key,
            DeepSeekLLMClient(
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url,
                model=settings.deepseek_model,
            ),
        )
    return _LLM_CLIENT_CACHE[1]


def _settings():
    from app.core.config import get_settings

    return get_settings()
