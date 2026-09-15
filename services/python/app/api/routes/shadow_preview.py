"""影子跟读联调测试台（test-only，团队测试用，可整体删除；DoD ④，2026-09-04）。

与 Agent Lab / flow-preview 同规格：`include_in_schema=False`（契约快照零影响）、
无表/无迁移、不碰既有路由、默认关闭（`shadow_preview_enabled=False` → 404）、
生产禁止开启；删除清单见本文件末尾注释。

能力（供 `/preview/shadow` 联调页走通「选素材 → 听示范 → 录音跟读 → 三维评分」）：
- GET  /api/v1/shadow-preview/materials  已发布素材列表（含句数与原声 wpm）
- POST /api/v1/shadow-preview/tts        句子 → 示范音频（edge-tts，原始字节）
- POST /api/v1/shadow-preview/analyze    跟读音频 → ASR + 特征 + ISE(题卡原文) + 三维评分
"""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.audio.base import get_asr_client, get_scorer_client, get_tts_client
from app.audio.fluency import compute_fluency_features
from app.audio.upload import validate_audio_bytes
from app.core.config import get_settings
from app.core.response import Envelope, ok
from app.db import get_session_factory
from app.models import ShadowMaterial
from app.practice.shadow import coach_note, shadow_scores, split_sentences

router = APIRouter(
    prefix="/api/v1/shadow-preview", tags=["shadow-preview"], include_in_schema=False
)  # include_in_schema=False：不进 OpenAPI 契约快照（同 agent-lab 测试台约束）


class TtsIn(BaseModel):
    text: str
    voice: str = ""
    rate: str = ""


@router.get("/materials")
async def materials() -> Envelope[list]:
    """已发布影子素材（联调页下拉用；读侧，含句数与原声 wpm）。"""
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(ShadowMaterial)
            .where(ShadowMaterial.status == "published")
            .order_by(ShadowMaterial.level, ShadowMaterial.id)
        ).scalars()
        return ok(
            [
                {
                    "id": int(m.id),
                    "title": m.title,
                    "level": m.level,
                    "wpm": m.wpm,
                    "duration_s": m.duration_s,
                    "audio_url": m.audio_url,
                    "text_content": m.text_content,
                    "sentence_count": len(split_sentences(m.text_content)),
                }
                for m in rows
            ]
        )
    finally:
        db.close()


@router.post("/tts")
async def tts(body: TtsIn) -> Response:
    """句子 → 示范音频（edge-tts；返回原始字节，联调页 Blob 播放）。"""
    settings = get_settings()
    data = await get_tts_client().synthesize(
        body.text, voice=body.voice or settings.tts_voice, rate=body.rate or settings.tts_rate
    )
    return Response(content=data, media_type="audio/mpeg")


@router.post("/analyze")
async def analyze(
    audio: UploadFile = File(...),
    material_id: int = Form(...),
    sentence_index: int = Form(default=0),
) -> Envelope[dict]:
    """跟读音频 → ASR + 流利度特征 + ISE（reference=题卡句）+ 三维评分。

    与生产 `_shadow_turn` 的评分核心同构（shadow_scores 同一函数）；无状态、不落库。
    """
    data = validate_audio_bytes(
        await audio.read(), min_bytes=0, max_bytes=get_settings().max_upload_bytes
    )
    db = get_session_factory()()
    try:
        material = db.get(ShadowMaterial, material_id)
    finally:
        db.close()
    sentences = split_sentences(material.text_content) if material else []
    if not sentences or not (0 <= sentence_index < len(sentences)):
        raise HTTPException(
            status_code=422, detail=f"sentence index out of range ({sentence_index})"
        )
    sentence = sentences[sentence_index]

    asr_res = await get_asr_client().transcribe(data)
    features = compute_fluency_features(asr_res.words or [], float(asr_res.duration or 0.0))

    score = None
    if asr_res.text.strip():
        try:
            score = await get_scorer_client().score(data, sentence)
        except Exception:
            score = None
    sc = shadow_scores(
        float(score.pronunciation) if score else None,
        features.get("wpm") or None,
        material.wpm,
        features.get("pause_ratio") or None,
    )

    return ok(
        {
            "material": {"id": int(material.id), "title": material.title, "wpm": material.wpm},
            "sentence": sentence,
            "sentence_index": sentence_index,
            "transcript": asr_res.text,
            "features": features,
            "shadow": sc.as_dict(),
            "coach": coach_note(sc),
            "ise": {
                "overall": float(score.overall),
                "pron": float(score.pronunciation),
                "flu": float(score.fluency),
                "word_level": score.word_level,
            }
            if score
            else None,
        }
    )


"""
删除清单（影子跟读联调测试台整删无影响）：
1. 删 `apps/web/src/views/preview/ShadowPreview.vue` + `views/preview/registry.ts` 该行
   + `router/preview.ts` 该路由（dev-only 子树，生产构建零体积）；
2. 删本文件 + `main.py` 的 `shadow_preview` import 与 `include_router` 两行；
3. 删 `app/core/config.py` 的 `shadow_preview_enabled` 一行；
4. 收尾：全量 pytest / pnpm typecheck / lint；契约快照零 diff（include_in_schema=False）。
"""

__all__ = ["router"]
