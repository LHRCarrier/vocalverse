"""语音管线骨架接口（M1 为 Fake 实现，M2 替换真实现）。

POST /api/v1/asr   上传音频 → 转写
POST /api/v1/score 上传音频 + 参考文本 → 发音评分
POST /api/v1/tts   文本 → 合成音频（bytes）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.audio.base import (
    ASRClient,
    ASRResult,
    ChatResult,
    LLMClient,
    ScorerClient,
    ScoreResult,
    TTSClient,
    TTSResult,
    get_asr_client,
    get_llm_client,
    get_scorer_client,
    get_tts_client,
)
from app.core.config import Settings, get_settings
from app.core.response import BizError, Envelope, ok

router = APIRouter(prefix="/api/v1", tags=["audio"])


async def _read_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    data = await upload.read()
    if len(data) > max_bytes:
        raise BizError(http_status=413, code=41301, message="audio too large")
    return data


@router.post("/asr")
async def asr(
    audio: UploadFile = File(...),
    language: str = Form("en"),
    client: ASRClient = Depends(get_asr_client),
    settings: Settings = Depends(get_settings),
) -> Envelope[ASRResult]:
    data = await _read_bounded(audio, settings.max_upload_bytes)
    result = await client.transcribe(data, language=language)
    return ok(result)


@router.post("/score")
async def score(
    audio: UploadFile = File(...),
    reference: str = Form(...),
    client: ScorerClient = Depends(get_scorer_client),
    settings: Settings = Depends(get_settings),
) -> Envelope[ScoreResult]:
    data = await _read_bounded(audio, settings.max_upload_bytes)
    result = await client.score(data, reference)
    return ok(result)


@router.post("/tts")
async def tts(
    text: str = Form(...),
    voice: str = Form("en-US-JennyNeural"),
    rate: str = Form("+0%"),
    client: TTSClient = Depends(get_tts_client),
) -> Envelope[TTSResult]:
    audio_bytes = await client.synthesize(text, voice=voice, rate=rate)
    return ok(TTSResult(audio_bytes=audio_bytes.hex(), length=len(audio_bytes)))


@router.post("/llm/chat")
async def llm_chat(
    message: str = Form(...),
    client: LLMClient = Depends(get_llm_client),
) -> Envelope[ChatResult]:
    reply = await client.chat([{"role": "user", "content": message}])
    return ok(ChatResult(reply=reply))
