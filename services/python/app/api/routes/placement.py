"""入学测试路由（docs/06 §9.2：5 句固定朗读 + 1 轮 QA；判定=综合分公式）。

- GET 题库（published）；POST 单题录音评分；POST finalize 计算综合分 S → 水平档。
- 档位回写 user_profiles 由 Java 负责（Java 唯一写者）；本服务落 placements 事实 +
  通过内部 REST（service-token）委托 Java 更新（Java 就绪前仅落库，前端读 placements）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from app.audio.base import get_asr_client, get_scorer_client
from app.audio.fluency import compute_fluency_features
from app.audio.upload import validate_audio_bytes
from app.core.auth import get_current_user_id
from app.core.config import get_settings
from app.core.ratelimit import consume
from app.core.response import ok
from app.db import get_session_factory
from app.models import Attempt, Placement, PlacementQuestion
from app.models.base import AttemptKinds, Levels

router = APIRouter(prefix="/api/v1/placement", tags=["placement"])

QA_REF = "The candidate's answer should be short and coherent."


def _level_for(s: float) -> str:
    """docs/06 §9.2：S≥85→L4、70~84→L3、55~69→L2、<55→L1。"""
    if s >= 85:
        return Levels.L4
    if s >= 70:
        return Levels.L3
    if s >= 55:
        return Levels.L2
    return Levels.L1


@router.get("/questions")
async def questions(user_id: int = Depends(get_current_user_id)):
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(PlacementQuestion)
            .where(PlacementQuestion.status == "published")
            .order_by(PlacementQuestion.exam_revision, PlacementQuestion.item_index)
        ).scalars()
        return ok(
            [
                {
                    "id": q.id,
                    "kind": q.kind,
                    "prompt": q.prompt,
                    "reference_answer": q.reference_answer,
                }
                for q in rows
            ]
        )
    finally:
        db.close()


@router.post("/items/{item_id}/audio")
async def score_item(
    item_id: int,
    audio: UploadFile = File(...),
    user_id: int = Depends(get_current_user_id),
):
    settings = get_settings()
    # 先校验再扣额度：空/近空录音不该消耗 ASR/ISE 配额，也不该推进题目
    data = validate_audio_bytes(
        await audio.read(),
        min_bytes=settings.min_upload_bytes,
        max_bytes=settings.max_upload_bytes,
    )
    await consume("asr", settings.asr_rate_per_hour, user_id)
    await consume("ise", settings.ise_rate_per_hour, user_id)
    db = get_session_factory()()
    try:
        q = db.get(PlacementQuestion, item_id)
        if q is None or q.status != "published":
            raise HTTPException(status_code=404, detail="question not found")
        asr = get_asr_client()
        asr_res = await asr.transcribe(data)
        text = asr_res.text
        # 流利度时间戳特征（docs/06 §9.3 辅助口径；与对话链路同源）
        fluency = compute_fluency_features(asr_res.words or [], float(asr_res.duration or 0.0))
        scorer = get_scorer_client()
        try:
            score = await scorer.score(data, q.prompt)
        except Exception:
            score = None
        attempt = Attempt(
            user_id=user_id,
            kind=AttemptKinds.PLACEMENT_ITEM,
            transcript=text,
            pron_score=_dec(score.pronunciation) if score else None,
            flu_score=_dec(score.fluency) if score else None,
            gram_score=_dec(score.grammar) if score else None,
            overall_score=_dec(score.overall) if score else None,
            wpm=_dec(fluency["wpm"]) if fluency else None,
            details={"fluency": fluency},
            error={} if score else {"reason": "score_unavailable"},
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)
        return ok(
            {
                "attempt_id": attempt.id,
                "transcript": text,
                "pron": float(score.pronunciation) if score else None,
                "flu": float(score.fluency) if score else None,
                "gram": float(score.grammar) if score else None,
                "wpm": float(attempt.wpm) if attempt.wpm is not None else None,
            }
        )
    finally:
        db.close()


class FinalizeIn(BaseModel):
    attempts: list[int]


@router.post("/finalize")
async def finalize(body: FinalizeIn, user_id: int = Depends(get_current_user_id)):
    """综合分 S = 0.4·发音 + 0.3·语法 + 0.3·流利度（docs/06 §9.2）。"""
    db = get_session_factory()()
    try:
        rows = db.execute(
            select(Attempt).where(Attempt.id.in_(body.attempts), Attempt.user_id == user_id)
        ).scalars()
        scored = [a for a in rows if a.pron_score is not None]
        if not scored:
            raise HTTPException(status_code=422, detail="no scored attempts")

        def avg(f):
            vals = [float(getattr(a, f)) for a in scored if getattr(a, f) is not None]
            return sum(vals) / len(vals) if vals else 0.0

        pron, flu, gram = avg("pron_score"), avg("flu_score"), avg("gram_score")
        s = 0.4 * pron + 0.3 * gram + 0.3 * flu
        level = _level_for(s)
        from datetime import UTC, datetime

        placement = Placement(
            user_id=user_id,
            status="completed",
            completed_at=datetime.now(UTC),
            level=level,
            overall_score=round(_dec(s), 2),
            pron_score=round(_dec(pron), 2),
            flu_score=round(_dec(flu), 2),
            gram_score=round(_dec(gram), 2),
            details={"attempt_ids": body.attempts},
        )
        db.add(placement)
        db.commit()
        # Java 回写 user_profiles（service-token 内部 REST；未就绪时静默降级——M2 演示读本表）
        await _callback_level(user_id, level)
        return ok(
            {
                "placement_id": placement.id,
                "level": level,
                "total_score": round(s, 2),
                "pron": round(pron, 2),
                "flu": round(flu, 2),
                "gram": round(gram, 2),
            }
        )
    finally:
        db.close()


async def _callback_level(user_id: int, level: str) -> None:
    """委托 Java 更新 user_profiles.level（Java 是唯一写者；内部 service-token）。"""
    import httpx

    from app.core.config import get_settings

    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            await client.post(
                f"{settings.java_base_url}/internal/level",
                json={"user_id": user_id, "level": level},
                headers={"Authorization": f"Bearer {settings.service_token}"},
            )
    except Exception:  # Java 未就绪/网络异常：静默（M2 演示不阻塞）
        return


def _dec(v):
    from decimal import Decimal

    if v is None:
        return None
    return Decimal(str(round(float(v), 2)))
