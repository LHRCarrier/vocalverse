"""OmniVoice 参考件音色引擎（本地 GPU 边车 · 零样本克隆）—— 英语音色来源。

背景（`local/research/xiaohaishi-voice-stack.md`）：参考项目 `HainnuP/xiaohaishi`
的语音栈把音色定义为 **「参考件 wav 字节 + 参考文本 + seed」**，而不是一个 speaker id；
合成由只依赖标准库的 Python 边车 `services/omnivoice-sidecar/server.py` 完成
（`POST /synthesize`，包住本机 GPU 上的 `k2-fsa/OmniVoice`，24 kHz）。本项目复用它
**英语的两把嗓子**：

- ``anchor-en``   → ``male-en.wav``   （The Anchor · 美音中年男）
- ``podcaster-en``→ ``female-en.wav`` （The Podcaster · 澳音年轻女）

契约与纪律（照抄上游，**每一条都有代价**）：

1. **参考件按 sha256 校验后才使用**——字节就是嗓子的身份，参考件被换掉必须大声失败，
   否则玩偶/产品会「静默换一把嗓子」（上游 ``voice-library.service.ts:96-105``）；
2. **参考文本必须来自清单（禁止自动转写）**——ASR 模型漂移会让音色每天都变
   （上游 ``REF_TEXT_REQUIRED``）；
3. clone 模式下**不下发 instruct**（上游 ``INSTRUCT_IN_CLONE`` 直接 400）；
4. 语速不走引擎：``rate`` 参数被忽略，倍速由前端 ``playbackRate`` 承担
   （与本仓 KittenTTS 同一口径，docs/45 §5 拍板：免多档重合成）。

本引擎在 ``auto`` 链中**排在首位**（本地优先），因此 ``is_available()`` 不只查配置，
还以 ``GET {endpoint}/health``（结果按 10s TTL 缓存）确认边车真的在跑——否则参考件目录
配好而边车没起时，``auto`` 会选中它并让每次合成失败。边车不在就自动回落 kitten / edge，
不阻塞任何链路。权重与参考件**一律不入库**（红线：模型权重 / 原始音频），只按运行时路径引用。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.audio.base import TTSClient
from app.audio.registry import TTS as _TTS
from app.audio.registry import ProviderSpec, register

logger = logging.getLogger("vocalverse.tts.omnivoice")

#: 音色清单文件名（上游真相表；参考文本/指令/seed/sha256 都在这里）
MANIFEST_NAME = "VOICES.json"

# ── 边车连通性探测 ────────────────────────────────────────────────────────────
# 为什么必须探测：本引擎在 auto 链**首位**。若只看「配置齐了没」，参考件目录配好
# 而边车没起时，auto 会选中它 → 每次合成都失败。把连通性纳入 is_available() 后，
# 边车没起就自动跳到 kitten/edge，链路不受影响。
# 探测结果按 TTL 缓存：auto 链每次解析都会问一遍 is_available()，不能每请求打网络。
_HEALTH_TTL_S = 10.0
_HEALTH_TIMEOUT_S = 2.0
_health_cache: dict[str, tuple[float, bool]] = {}
_health_lock = threading.Lock()


def reset_health_cache() -> None:
    """清空连通性缓存（测试与配置热变更后调用）。"""
    with _health_lock:
        _health_cache.clear()


def _probe_health(endpoint: str, timeout_s: float = _HEALTH_TIMEOUT_S) -> bool:
    """``GET {endpoint}/health`` 是否 200；结果按 TTL 缓存，绝不抛错。"""
    import time

    now = time.monotonic()
    with _health_lock:
        hit = _health_cache.get(endpoint)
        if hit is not None and hit[0] > now:
            return hit[1]
    ok = False
    try:
        import httpx

        ok = httpx.get(f"{endpoint}/health", timeout=timeout_s).status_code == 200
    except Exception:  # noqa: BLE001 — 连接失败/超时/协议错一律视为未就绪
        ok = False
    with _health_lock:
        _health_cache[endpoint] = (now + _HEALTH_TTL_S, ok)
    return ok


#: 对用户可见的音色 id ↔ 清单里的 ``personaId-lang`` ↔ 口碑别名
_VOICE_IDS: dict[str, tuple[str, str]] = {
    # voice_id: (personaId-lang, 口碑别名)
    "anchor-en": ("male-en", "the-anchor"),
    "podcaster-en": ("female-en", "the-podcaster"),
    "male-zh": ("male-zh", "b3"),
    "female-zh": ("female-zh", "05"),
}

#: 别名 → 规范 id（前端/配置里写别名也能命中）
_ALIASES: dict[str, str] = {
    "male-en": "anchor-en",
    "the-anchor": "anchor-en",
    "anchor": "anchor-en",
    "female-en": "podcaster-en",
    "the-podcaster": "podcaster-en",
    "podcaster": "podcaster-en",
}


def normalize_voice(voice: str) -> str:
    """音色名归一化（别名 → 规范 id）；未知原样返回（由调用方决定是否回落默认）。"""
    key = (voice or "").strip().lower()
    return _ALIASES.get(key, key)


def default_refs_dir() -> str:
    """参考件目录的兜底：仓库内 `data/seed/voices`（随仓库分发，见 `core.paths.voices_dir`）。

    显式配置（`APP_VOICE_REFS_DIR`）永远优先；这里只解决"队友 clone 下来不用配任何东西
    就能用"的问题。目录不存在则返回空串（= 不启用克隆音色，auto 链跳过本引擎）。
    """
    try:
        from app.core.paths import voices_dir

        path = voices_dir()
        return str(path) if path.is_dir() else ""
    except Exception:  # noqa: BLE001 — 路径解析失败不该炸掉引擎构造
        return ""


@dataclass(frozen=True)
class RefVoice:
    """清单里的一条音色（参考件 + 参考文本 + seed）。"""

    voice_id: str
    file: str
    sha256: str
    ref_text: str
    seed: int
    lang: str
    label: str
    is_default: bool = False


def _parse_manifest(payload: Any) -> list[RefVoice]:
    """``VOICES.json`` → :class:`RefVoice` 列表（缺字段的条目跳过，不让脏数据炸掉整表）。"""
    out: list[RefVoice] = []
    if not isinstance(payload, dict):
        return out
    key_to_id = {v[0]: k for k, v in _VOICE_IDS.items()}
    for row in payload.get("voices") or []:
        if not isinstance(row, dict):
            continue
        persona = str(row.get("personaId") or "").strip()
        lang = str(row.get("lang") or "").strip()
        file = str(row.get("file") or "").strip()
        ref_text = str(row.get("refText") or "").strip()
        if not (persona and lang and file and ref_text):
            logger.warning("音色清单条目缺 personaId/lang/file/refText，跳过：%s", row)
            continue
        voice_id = key_to_id.get(f"{persona}-{lang}", f"{persona}-{lang}")
        out.append(
            RefVoice(
                voice_id=voice_id,
                file=file,
                sha256=str(row.get("sha256") or "").strip().lower(),
                ref_text=ref_text,
                seed=int(row.get("seed") or 42),
                lang=lang,
                label=str(row.get("wordOfMouth") or voice_id),
                is_default=voice_id == "anchor-en",
            )
        )
    return out


def read_manifest(refs_dir: str) -> list[RefVoice]:
    """读取音色清单（不构造客户端；音色目录/健康检查复用）。失败 → 空表（绝不抛）。"""
    path = Path(refs_dir) / MANIFEST_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.info("音色清单不存在：%s", path)
        return []
    except Exception as exc:  # noqa: BLE001 — 清单坏了按「无音色」处理，由 is_available 报原因
        logger.warning("音色清单解析失败 %s：%s", path, exc)
        return []
    return _parse_manifest(payload)


class OmniVoiceTTSClient(TTSClient):
    """本地 OmniVoice 边车客户端（零样本克隆；参考件按 sha256 校验）。"""

    provider_id = "omnivoice"
    media_type = "audio/wav"
    ext = "wav"
    is_local = True
    langs = ("en", "zh")

    def __init__(
        self,
        endpoint: str = "",
        refs_dir: str = "",
        voice: str = "anchor-en",
        seed: int | None = None,
        timeout_s: float = 120.0,
        verify_sha256: bool = True,
    ) -> None:
        self._endpoint = (endpoint or "").rstrip("/")
        self._refs_dir = refs_dir
        self._voice = normalize_voice(voice) or "anchor-en"
        self._seed_override = seed
        self._timeout_s = timeout_s
        self._verify_sha256 = verify_sha256
        self._voices: list[RefVoice] | None = None
        self._load_lock = threading.Lock()

    # -- 清单 ----------------------------------------------------------------
    @property
    def manifest_path(self) -> Path:
        return Path(self._refs_dir) / MANIFEST_NAME

    def voices(self) -> list[RefVoice]:
        """加载并缓存音色清单（首次读取磁盘；幂等）。"""
        if self._voices is None:
            with self._load_lock:
                if self._voices is None:
                    self._voices = self._read_manifest()
        return self._voices

    def _read_manifest(self) -> list[RefVoice]:
        return read_manifest(self._refs_dir)

    def resolve_voice(self, voice: str) -> RefVoice | None:
        """把请求里的音色名解析成一条参考件记录；未知 → None（调用方决定回落）。"""
        wanted = normalize_voice(voice) or self._voice
        voices = self.voices()
        for item in voices:
            if item.voice_id == wanted:
                return item
        for item in voices:
            if item.is_default:
                return item
        return voices[0] if voices else None

    # -- 探测 / 生命周期 ------------------------------------------------------
    def is_available(self) -> tuple[bool, str]:
        if not self._endpoint:
            return False, "APP_TTS_OMNIVOICE_ENDPOINT 未配置（本地 OmniVoice 边车地址为空）"
        if not self._refs_dir:
            return False, "APP_VOICE_REFS_DIR 未配置（找不到音色参考件目录）"
        try:
            import httpx  # noqa: F401
        except Exception as exc:  # pragma: no cover - httpx 是必装依赖
            return False, f"httpx 不可用: {exc}"
        voices = self.voices()
        if not voices:
            return False, (
                f"音色清单缺失或为空：{self.manifest_path}（参考文本必须给死，禁止自动转写）"
            )
        default = self.resolve_voice(self._voice)
        if default is None:
            return False, "清单里没有可用音色条目"
        if not (Path(self._refs_dir) / default.file).exists():
            return False, f"参考件缺失：{Path(self._refs_dir) / default.file}"
        if not _probe_health(self._endpoint):
            return False, f"OmniVoice 边车未就绪（{self._endpoint}/health 无响应）"
        return True, "ready"

    def ensure_ready(self) -> None:
        """加载清单并校验参考件 sha256（不合规即抛——绝不用未知字节合成）。"""
        for item in self.voices():
            self._reference_bytes(item)

    def unload(self) -> None:
        self._voices = None  # 幂等

    # -- 合成 ----------------------------------------------------------------
    def _reference_bytes(self, item: RefVoice) -> bytes:
        path = Path(self._refs_dir) / item.file
        data = path.read_bytes()
        if self._verify_sha256 and item.sha256:
            digest = hashlib.sha256(data).hexdigest()
            if digest != item.sha256:
                raise RuntimeError(
                    f"音色参考件校验不过：{item.file} 的 sha256 是 {digest}，"
                    f"清单里写的是 {item.sha256}。参考件被改动过 —— 这会让音色静默换人，"
                    "因此拒绝合成。"
                )
        return data

    def build_request(self, text: str, voice: str = "anchor-en") -> dict[str, Any]:
        """构造 `/synthesize` 请求体（**独立成方法**，好让契约测试直接喂边车校验）。

        形状与边车 `services/omnivoice-sidecar/server.py:validate()` 一一对应：
        clone 模式 + `ref{audioBase64,text}` + seed + `format=wav`，**不含 instruct**
        （边车对 clone+instruct 直接 400）。
        """
        item = self.resolve_voice(voice)
        if item is None:
            raise RuntimeError(f"OmniVoice 无可用音色（请求 voice={voice!r}）")
        ref_bytes = self._reference_bytes(item)
        return {
            "text": text,
            "language": item.lang,
            "mode": "clone",
            "ref": {
                "audioBase64": base64.b64encode(ref_bytes).decode("ascii"),
                "text": item.ref_text,
            },
            "seed": self._seed_override if self._seed_override is not None else item.seed,
            "format": "wav",
        }

    async def synthesize(self, text: str, voice: str = "anchor-en", rate: str = "+0%") -> bytes:
        import httpx

        payload = self.build_request(text, voice)
        url = f"{self._endpoint}/synthesize"
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(url, json=payload)
        except Exception as exc:  # 连接失败/超时
            raise RuntimeError(f"OmniVoice 边车不可达（{url}）：{exc}") from exc
        if resp.status_code != 200:
            raise RuntimeError(
                f"OmniVoice 合成失败 HTTP {resp.status_code}（{url}）：{resp.text[:200]}"
            )
        if not resp.content:
            raise RuntimeError(f"OmniVoice 返回空音频: {text[:40]!r}")
        return resp.content


#: 供音色目录使用：本引擎暴露的音色（只读清单，不构造客户端、不触网）
def supported_voices(settings: Any) -> list[dict[str, Any]]:
    refs_dir = getattr(settings, "voice_refs_dir", "") or default_refs_dir()
    if not refs_dir:
        return []
    return [
        {
            "id": item.voice_id,
            "label": f"{item.label} · 本地克隆",
            "engine": "omnivoice",
            "langs": [item.lang],
        }
        for item in read_manifest(refs_dir)
    ]


# ── 注册表登记 ────────────────────────────────────────────────────────────────
register(
    ProviderSpec(
        name="omnivoice",
        kind=_TTS,
        label="OmniVoice 参考件音色（本地 GPU 边车 · 零样本克隆）",
        factory=lambda settings: OmniVoiceTTSClient(
            endpoint=getattr(settings, "tts_omnivoice_endpoint", ""),
            refs_dir=getattr(settings, "voice_refs_dir", "") or default_refs_dir(),
            voice=getattr(settings, "tts_omnivoice_voice", "") or "anchor-en",
            seed=getattr(settings, "tts_omnivoice_seed", None),
            timeout_s=getattr(settings, "tts_omnivoice_timeout_s", 120.0),
        ),
        priority=10,  # auto 链首位：本地克隆音色优先，不可用则回落 kitten/edge
        is_local=True,
        ext="wav",
        media_type="audio/wav",
        aliases=("omnivoice-sidecar",),
    )
)
