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
from app.audio.upload import validate_audio_bytes
from app.core.auth import get_current_user_id
from app.core.config import Settings, get_settings
from app.core.ratelimit import bucket_limits, consume
from app.core.response import Envelope, ok

router = APIRouter(prefix="/api/v1", tags=["audio"])


async def _read_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    # 无状态管线端点：只守上界，下界沿用历史行为（min_bytes=0），见 app/audio/upload.py
    return validate_audio_bytes(await upload.read(), min_bytes=0, max_bytes=max_bytes)


@router.post("/asr")
async def asr(
    audio: UploadFile = File(...),
    language: str = Form("en"),
    client: ASRClient = Depends(get_asr_client),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(get_current_user_id),
) -> Envelope[ASRResult]:
    await consume("asr", bucket_limits()["asr"], user_id)  # P0-6 鉴权+限流（付费 whisper）
    data = await _read_bounded(audio, settings.max_upload_bytes)
    result = await client.transcribe(data, language=language)
    return ok(result)


@router.post("/score")
async def score(
    audio: UploadFile = File(...),
    reference: str = Form(...),
    client: ScorerClient = Depends(get_scorer_client),
    settings: Settings = Depends(get_settings),
    user_id: int = Depends(get_current_user_id),
) -> Envelope[ScoreResult]:
    await consume("ise", bucket_limits()["ise"], user_id)  # P0-6 鉴权+限流（付费 ISE）
    data = await _read_bounded(audio, settings.max_upload_bytes)
    result = await client.score(data, reference)
    return ok(result)


@router.post("/tts")
async def tts(
    text: str = Form(...),
    voice: str = Form("en-US-JennyNeural"),
    rate: str = Form("+0%"),
    client: TTSClient = Depends(get_tts_client),
    user_id: int = Depends(get_current_user_id),
) -> Envelope[TTSResult]:
    await consume("tts", bucket_limits()["tts"], user_id)  # P0-6 鉴权+限流（付费/TTS）
    audio_bytes = await client.synthesize(text, voice=voice, rate=rate)
    return ok(TTSResult(audio_bytes=audio_bytes.hex(), length=len(audio_bytes)))


@router.post("/llm/chat")
async def llm_chat(
    message: str = Form(...),
    client: LLMClient = Depends(get_llm_client),
    user_id: int = Depends(get_current_user_id),
) -> Envelope[ChatResult]:
    await consume("llm", bucket_limits()["llm"], user_id)  # P0-6 鉴权+限流（付费 DeepSeek）
    reply = await client.chat([{"role": "user", "content": message}])
    return ok(ChatResult(reply=reply))
