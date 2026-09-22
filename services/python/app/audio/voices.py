"""音色目录（voice catalog）—— 全站「有哪些嗓子」的单一真源。

重构前音色清单散在三处：``app/api/routes/reading.py:list_edge_voices`` 硬编码 5 个
edge 音色、同文件内联拼 KittenTTS 清单、前端 ``useChapterTts.ts`` 又硬编码默认
``'en-US-JennyNeural'``。于是「加一个本地引擎的音色」要改 3 个文件，且路由层不得不
import 引擎实现类（分层倒置）。

现在：引擎各自声明 ``supported_voices(settings)``，本模块负责聚合与去重，
路由只做「转成响应模型」。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("vocalverse.audio.voices")

#: 默认音色（全站兜底；前端也读这个值，不再各写一份）
DEFAULT_VOICE = "en-US-JennyNeural"


@dataclass(frozen=True)
class VoiceSpec:
    """一个可选音色。``engine`` 即 provider 名（进缓存键/响应头）。"""

    id: str
    label: str
    engine: str
    langs: tuple[str, ...] = field(default_factory=lambda: ("en",))
    is_local: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "engine": self.engine,
            "langs": list(self.langs),
        }


#: edge-tts 音色清单（在线档；languages 用 BCP-47 区域码，与既有契约一致）
EDGE_VOICES: tuple[VoiceSpec, ...] = (
    VoiceSpec("en-US-JennyNeural", "Jenny · 美式女声", "edge", ("en-US",)),
    VoiceSpec("en-US-AriaNeural", "Aria · 美式女声", "edge", ("en-US",)),
    VoiceSpec("en-US-GuyNeural", "Guy · 美式男声", "edge", ("en-US",)),
    VoiceSpec("en-GB-SoniaNeural", "Sonia · 英式女声", "edge", ("en-GB",)),
    VoiceSpec("en-GB-RyanNeural", "Ryan · 英式男声", "edge", ("en-GB",)),
)


def _kitten_voices(settings: Any) -> list[VoiceSpec]:
    """KittenTTS 内置音色（仅当本地模型就绪时暴露，避免前端选到发不出声的音色）。"""
    try:
        from app.audio.tts_local import KITTEN_VOICES, KittenTTSClient
    except Exception:  # pragma: no cover - 引擎模块缺失
        return []
    client = KittenTTSClient(getattr(settings, "voice_models_dir", ""))
    available, _ = client.is_available()
    if not available:
        return []
    return [
        VoiceSpec(name, f"{name} · 本地音色", "kitten", ("en",), is_local=True)
        for name in KITTEN_VOICES
    ]


def _omnivoice_voices(settings: Any) -> list[VoiceSpec]:
    """OmniVoice 参考件音色（读清单；不触网、不加载权重）。"""
    try:
        from app.audio.tts_omnivoice import supported_voices
    except Exception:  # pragma: no cover
        return []
    out: list[VoiceSpec] = []
    for row in supported_voices(settings):
        out.append(
            VoiceSpec(
                str(row["id"]),
                str(row["label"]),
                "omnivoice",
                tuple(row.get("langs") or ("en",)),
                is_local=True,
            )
        )
    return out


def list_voices(settings: Any = None) -> list[VoiceSpec]:
    """全站音色（edge 在线档 + 已就绪的本地引擎档）；按 id 去重、保持稳定顺序。"""
    if settings is None:
        from app.core.config import get_settings

        settings = get_settings()
    collected: list[VoiceSpec] = [
        *EDGE_VOICES,
        *_kitten_voices(settings),
        *_omnivoice_voices(settings),
    ]
    seen: set[str] = set()
    out: list[VoiceSpec] = []
    for item in collected:
        if item.id in seen:
            continue
        seen.add(item.id)
        out.append(item)
    return out


__all__ = ["DEFAULT_VOICE", "EDGE_VOICES", "VoiceSpec", "list_voices"]
