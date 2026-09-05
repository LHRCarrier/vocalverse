"""自由对话（MVP，2026-09-05）：语音/打字 → ASR（可选）→ LLM 流式回复（docs/14 §12）。

产品定位（组长拍板 2026-09-05）：口语 = 场景对话（固定出题）+ 自由对话（LLM + TTS）。
本接口是**无状态「LLM 转发器」**：客户端自带滚动 history，服务端不建会话、不入库、
不出报告（MVP 约定：刷新即失忆；评分/报告分期见 docs/14 §12）。

实现：
- POST /api/v1/free-chat/turn —— multipart：audio（可选）/ text（可选）/ history（JSON 字符串）；
- SSE 复用 practice/events.py 协议子集：user_transcript / text_delta / turn_end / error
  （前端手写同类型，与 docs/14 §3.3 同款双端同步约定）；
- LLM 复用 agent.runtime.TurnRunner（META 泄漏门免费拿到；自由对话不注入 corpus，
  system 全静态人设 —— docs/26「动态内容不进 system」姿势复用）；
- ASR 走既有 get_asr_client（无 Key 时 Fake 桩）；TTS 由前端用 /api/v1/tts 自理
  （本流只回文本，避免音频归属/过期链路（GET /audio 需 attempts 引用））。
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agent.runtime.turn_runner import TurnRunner
from app.audio.base import get_asr_client, get_llm_client
from app.audio.upload import validate_audio_bytes
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.ratelimit import bucket_limits, consume
from app.core.response import BizError
from app.practice import events as ev

router = APIRouter(prefix="/api/v1/free-chat", tags=["free-chat"])
logger = logging.getLogger("vocalverse")

# 自由对话人设：全静态 system（动态内容（history/当前轮）全部走 messages，不进 system）
_SYSTEM_PROMPT = (
    "You are a friendly and patient English conversation partner in a speaking practice app. "
    "Keep replies short (1-3 sentences), use simple words, be natural and encouraging. "
    "Pick up on what the learner just said, ask a short follow-up or share your own thought, "
    "and help them keep the conversation going. Reply in plain English ONLY."
)

_MAX_HISTORY = 24  # 防 prompt 膨胀：只带最近 24 条消息
_MAX_TEXT = 2000


class _HistoryMsg(BaseModel):
    role: Literal["user", "assistant"]
    content: str


async def _rl_asr(user_id: int = Depends(get_current_user_id)) -> None:
    await consume("asr", bucket_limits()["asr"], user_id)


async def _rl_llm(user_id: int = Depends(get_current_user_id)) -> None:
    await consume("llm", bucket_limits()["llm"], user_id)


@router.post("/turn")
async def free_chat_turn(
    audio: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    history: str = Form(default="[]"),
    user_id: int = Depends(get_current_user_id),
    _a: None = Depends(_rl_asr),
    _l: None = Depends(_rl_llm),
):
    """单轮自由对话：audio / text 至少其一（都空 → 422，流外预检）。

    流内事件序（音频轮）：user_transcript → text_delta* → turn_end；打字轮：text_delta* → turn_end。
    """
    try:
        hist = [_HistoryMsg.model_validate(m) for m in json.loads(history or "[]")]
    except (ValueError, TypeError) as exc:
        raise BizError(
            http_status=422,
            code=42203,
            message="history must be a JSON array of {role, content}",
        ) from exc
    hist = hist[-_MAX_HISTORY:]  # 只保留最近 N 条（客户端已截断，双保险）
    kind = "text" if (text or "").strip() else ("audio" if audio is not None else None)
    if kind is None:
        raise BizError(http_status=422, code=42204, message="audio or text is required")

    data = None
    if kind == "audio":
        settings = get_settings()
        data = await audio.read()  # type: ignore[union-attr]
        data = validate_audio_bytes(
            data,
            min_bytes=settings.min_upload_bytes,
            max_bytes=settings.max_upload_bytes,
        )

    typed = (text or "").strip()[:_MAX_TEXT] or None
    turn_index = sum(1 for m in hist if m.role == "user") + 1

    async def event_stream():
        try:
            user_text = typed
            if kind == "audio":
                asr = await get_asr_client().transcribe(data)  # type: ignore[arg-type]
                user_text = asr.text
                yield ev.sse_payload(ev.UserTranscript(turn_index=turn_index, text=user_text))
            runner = TurnRunner(get_llm_client())
            messages: list[dict[str, str]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
            messages += [{"role": m.role, "content": m.content} for m in hist]
            messages.append({"role": "user", "content": user_text or "(no speech)"})
            async for delta in runner.run(messages):
                yield ev.sse_payload(ev.TextDelta(text=delta))
            yield ev.sse_payload(ev.TurnEnd(turn_index=turn_index, score_status="unavailable"))
        except Exception as exc:
            logger.exception("free-chat turn failed: %s", exc)
            yield ev.sse_payload(ev.StreamError(code="internal", recoverable=True))

    headers = {"X-Accel-Buffering": "no", "Cache-Control": "no-cache"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)
