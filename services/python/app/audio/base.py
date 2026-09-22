"""音频管线抽象接口 —— 依赖注入 + TESTING 时注入 Fake（docs/06 第 6 章）。

CI 零真实 API Key：ASR/TTS/评分/LLM 全部可打桩。

**引擎身份是一等公民**（2026-09 重构）：``ASRClient`` / ``TTSClient`` 用类属性声明
``provider_id`` / ``media_type`` / ``ext`` / ``is_local``，调用方**读属性**而不是
``isinstance`` 反推——旧实现 ``isinstance(tts, KittenTTSClient)`` 在新增引擎时必然漏判，
并把缓存目录、文件扩展名与 Content-Type 一起带错（docs/46 B-3）。

**生命周期契约**（ASR 与 TTS 对齐）：``is_available()`` 先行探测 → ``ensure_ready()``
预热 → ``unload()`` 释放。三者都有默认实现，子类/Fake 无需覆写即兼容。

引擎的**选择**（配置 → 实例）统一走 :mod:`app.audio.registry`，本模块只保留
「按默认配置取一个实例」的便捷依赖注入入口，供 FastAPI ``Depends`` 使用。
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

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
    """TTS 响应数据（``/api/v1/tts``）。

    2026-09 增补 ``media_type`` / ``provider``：此前只回 hex 字节、无容器信息，
    消费方只能一律按 ``audio/mpeg`` 猜——本地引擎（KittenTTS/OmniVoice）出的是 24kHz
    WAV，被当 mp3 喂给 ``<audio>`` 会播坏（docs/46 B-3 同类问题）。两字段为**纯增量**，
    旧消费方忽略即可。
    """

    audio_bytes: str  # hex
    length: int
    media_type: str = "audio/mpeg"  # 实际输出容器（audio/mpeg | audio/wav）
    provider: str = "edge"  # 实际合成引擎（edge | kitten | omnivoice | fake）


@dataclass
class ChatResult:
    """LLM 场景扮演单轮回复。M2 多轮/流式扩展时更新契约（docs/06 §8）。"""

    reply: str


class ASRClient(abc.ABC):
    """语音识别接口。

    ``provider_id`` 是**引擎身份唯一真源**（进缓存键/日志/响应头/运维面板），
    子类必须覆写；默认值 ``unknown`` 会在 auto 链里被视为「未命名引擎」。
    """

    provider_id: ClassVar[str] = "unknown"
    is_local: ClassVar[bool] = True
    langs: ClassVar[tuple[str, ...]] = ("en",)

    @abc.abstractmethod
    async def transcribe(self, audio_bytes: bytes, language: str = "en") -> ASRResult:
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


class TTSClient(abc.ABC):
    """语音合成接口（默认 edge-tts，可切本地引擎）。

    生命周期契约（docs/44 P0-B）：带默认实现，子类/``FakeTTSClient`` 无需覆写即兼容。
    调用方应先 ``is_available()`` 再 ``synthesize``，不可用时给出可读降级而非静默/500。

    ``provider_id`` / ``media_type`` / ``ext`` 是引擎身份与**输出容器**的单一真源
    （缓存目录、文件后缀、Content-Type 都从这三者派生，不再由调用方猜）。
    """

    provider_id: ClassVar[str] = "unknown"
    media_type: ClassVar[str] = "audio/mpeg"
    ext: ClassVar[str] = "mp3"
    is_local: ClassVar[bool] = False
    langs: ClassVar[tuple[str, ...]] = ("en",)

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


def _fake_tts(settings, requested: str) -> TTSClient:
    """测试/CI 打桩客户端：**沿用解析到的 provider 名**，让缓存键与响应头保持真实维度。

    测试环境不探测真实可用性（否则本机 `.env` 里配了本地引擎会让用例结果随机器漂移），
    因此 ``auto`` 一律落到 ``settings.tts_provider``（仍为 ``auto`` 时取 ``edge``）。
    """
    from app.audio.registry import tts_format
    from app.audio.stubs import FakeTTSClient

    name = (requested or "").strip().lower()
    if name in ("", "auto"):
        fallback = (getattr(settings, "tts_provider", "") or "").strip().lower()
        name = fallback if fallback and fallback != "auto" else "edge"
    ext, media = tts_format(name)
    return FakeTTSClient(provider=name, ext=ext, media_type=media)


def resolve_asr_client(
    provider: str | None = None,
    *,
    strict: bool = False,
    settings: Any | None = None,
) -> ASRClient:
    """按配置解析 ASR 引擎（``APP_ASR_PROVIDER``；默认 ``auto``）。

    - ``auto``：按注册表 priority 探测第一个可用引擎（本地 whisper → 本地 sherpa）；
    - 显式名字：直取；``strict=True`` 且不可用 → :class:`ProviderUnavailable`；
    - ``APP_TESTING=true`` 或 ``APP_ASR_MODEL`` 为空 → Fake（CI 零真实模型）。

    ⚠️ 带参数的解析入口**不要**直接用作 FastAPI ``Depends`` —— FastAPI 会把
    ``provider`` / ``strict`` / ``settings`` 当成 query 参数写进 OpenAPI。依赖注入统一用
    零参的 :func:`get_asr_client`。
    """
    from app.audio import providers
    from app.audio.registry import ASR as _ASR
    from app.audio.registry import resolve

    settings = settings or _settings()
    providers.ensure_registered()
    if getattr(settings, "testing", False) or not getattr(settings, "asr_model", ""):
        from app.audio.stubs import FakeASRClient

        return FakeASRClient()
    requested = provider or getattr(settings, "asr_provider", "auto") or "auto"
    return resolve(_ASR, settings, requested, strict=strict).client


def get_asr_client() -> ASRClient:
    """ASR 客户端（零参依赖注入入口，FastAPI ``Depends`` 用）。"""
    return resolve_asr_client()


def resolve_tts_client(
    provider: str | None = None,
    *,
    strict: bool = False,
    settings: Any | None = None,
) -> TTSClient:
    """按配置解析 TTS 引擎（``APP_TTS_PROVIDER``；默认 ``edge``；``auto`` 走可用性链）。

    显式选中但未接线的 provider（如 ``azure``）**照原样返回实例**，由调用方查
    ``is_available()`` 后干净降级（docs/44 P0-C）；``strict=True`` 时改为直接抛
    :class:`ProviderUnavailable`（听书域显式指定本地引擎但不具备条件时的语义）。

    ⚠️ 同 :func:`resolve_asr_client`：带参数版本不要直接用于 ``Depends``。
    """
    from app.audio import providers
    from app.audio.registry import TTS as _TTS
    from app.audio.registry import resolve

    settings = settings or _settings()
    providers.ensure_registered()
    requested = provider or getattr(settings, "tts_provider", "edge") or "edge"
    if getattr(settings, "testing", False):
        return _fake_tts(settings, requested)

    return resolve(_TTS, settings, requested, strict=strict).client


def get_tts_client() -> TTSClient:
    """TTS 客户端（零参依赖注入入口，FastAPI ``Depends`` 用）。"""
    return resolve_tts_client()


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
