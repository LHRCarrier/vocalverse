"""语音管线骨架接口（M1 为 Fake 实现，M2 替换真实现）。

POST /api/v1/asr   上传音频 → 转写
POST /api/v1/score 上传音频 + 参考文本 → 发音评分
POST /api/v1/tts   文本 → 合成音频（bytes）
POST /api/v1/llm/chat 文本 → LLM 回复

docs/19 P0-4（语音链路审计 R-06）：此前四端点**无鉴权、无限流**——任何人可当
DeepSeek / edge-tts / whisper / 讯飞 ISE 的免费代理，账单可被耗光。修复：
1. 逐端点挂 `get_current_user_id`（docs/06 §11 JWT 验签；无 token → 401）；
2. 分桶 `consume`（docs/06 §7：ASR/ISE 60/时·LLM 30/时·TTS 60/时，超限 429 + Retry-After）；
3. **先校验后扣额度**（docs/19 P0-4：空/超限输入不消耗配额；与 placement.py
   L76-83 口径一致，修复审计 R-06 点名的"先扣后校验"）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

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
from app.audio.textproc.normalize import normalize_for_tts
from app.audio.upload import validate_audio_bytes
from app.core.auth import get_current_user_id
from app.core.config import Settings, get_settings
from app.core.ratelimit import consume
from app.core.response import Envelope, ok

router = APIRouter(prefix="/api/v1", tags=["audio"])


async def _read_bounded(upload: UploadFile, max_bytes: int) -> bytes:
    # 无状态管线端点：只守上界，下界沿用历史行为（min_bytes=0），见 app/audio/upload.py
    return validate_audio_bytes(await upload.read(), min_bytes=0, max_bytes=max_bytes)


@router.post("/asr")
async def asr(
    audio: UploadFile = File(...),
    language: str = Form("en"),
    user_id: int = Depends(get_current_user_id),  # docs/19 P0-4：裸端点鉴权（401）
    client: ASRClient = Depends(get_asr_client),
    settings: Settings = Depends(get_settings),
) -> Envelope[ASRResult]:
    data = await _read_bounded(audio, settings.max_upload_bytes)
    # 先校验后扣额度（docs/19 P0-4 / R-06：空/近空/超限不消耗 ASR 配额）
    await consume("asr", settings.asr_rate_per_hour, user_id)
    result = await client.transcribe(data, language=language)
    return ok(result)


@router.post("/score")
async def score(
    audio: UploadFile = File(...),
    reference: str = Form(...),
    user_id: int = Depends(get_current_user_id),  # docs/19 P0-4：裸端点鉴权（401）
    client: ScorerClient = Depends(get_scorer_client),
    settings: Settings = Depends(get_settings),
) -> Envelope[ScoreResult]:
    data = await _read_bounded(audio, settings.max_upload_bytes)
    # 先校验后扣额度（docs/19 P0-4 / R-06：校验失败不消耗 ISE 配额）
    await consume("ise", settings.ise_rate_per_hour, user_id)
    result = await client.score(data, reference)
    return ok(result)


@router.post("/tts")
async def tts(
    text: str = Form(...),
    voice: str = Form("en-US-JennyNeural"),
    rate: str = Form("+0%"),
    user_id: int = Depends(get_current_user_id),  # docs/19 P0-4：裸端点鉴权（401）
    client: TTSClient = Depends(get_tts_client),
    settings: Settings = Depends(get_settings),
) -> Envelope[TTSResult]:
    if not text.strip():
        raise HTTPException(status_code=422, detail="text required")
    # 文本前处理（docs/44 P1-A）：归一化在**合成前**（幂等、绝不抛错），
    # 与对话热路径 _tts_url_from_bytes 同一 choke point。
    text = normalize_for_tts(text, language="en")
    # docs/19 P0-4 / R-06：TTS 桶此前漏计（限流只覆盖 /turns 依赖），此处接线且先校验后扣
    await consume("tts", settings.tts_rate_per_hour, user_id)
    audio_bytes = await client.synthesize(text, voice=voice, rate=rate)
    return ok(TTSResult(audio_bytes=audio_bytes.hex(), length=len(audio_bytes)))


@router.post("/llm/chat")
async def llm_chat(
    message: str = Form(...),
    user_id: int = Depends(get_current_user_id),  # docs/19 P0-4：裸端点鉴权（401）
    client: LLMClient = Depends(get_llm_client),
    settings: Settings = Depends(get_settings),
) -> Envelope[ChatResult]:
    if not message.strip():
        raise HTTPException(status_code=422, detail="message required")
    await consume("llm", settings.llm_rate_per_hour, user_id)
    reply = await client.chat([{"role": "user", "content": message}])
    return ok(ChatResult(reply=reply))
