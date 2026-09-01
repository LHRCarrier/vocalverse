"""答辩档案路由（docs/14 §4：极简版——异步知识包生成 + 软删脱敏 + 重生成）。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import update

from app.audio.base import get_llm_client
from app.core.auth import get_current_user_id
from app.core.response import ok
from app.db import get_session_factory
from app.models import DefenseProfile
from app.practice.service import generate_bank

router = APIRouter(prefix="/api/v1/defense", tags=["defense"])
logger = logging.getLogger("vocalverse")

MAX_THESIS = 8000  # docs/14 §4.1：论文文本 ≤8000 字（服务层硬校验）


class ProfileIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    abstract: str = Field(min_length=20)
    outline: str = Field(min_length=5)
    highlights: str = Field(min_length=5)
    thesis_text: str | None = Field(default=None, max_length=MAX_THESIS)
    question_count: int = Field(default=6, ge=5, le=8)
    emphasis: str = Field(default="balanced")


def _generate_task(profile_id: int, body: ProfileIn) -> None:
    """后台生成知识包（asyncio task；失败置 failed，成功置 active + bank_version+1）。"""

    async def runner():
        db = get_session_factory()()
        try:
            llm = get_llm_client()
            bank = await generate_bank(
                llm,
                body.title,
                body.abstract,
                body.outline,
                body.highlights,
                body.thesis_text or "",
                body.question_count,
                body.emphasis,
            )
            db.execute(
                update(DefenseProfile)
                .where(DefenseProfile.id == profile_id)
                .values(
                    knowledge_bank=bank,
                    bank_version=DefenseProfile.bank_version + 1,
                    status="active",
                )
            )
        except Exception as exc:
            logger.warning("bank generation failed: %s", exc)
            db.execute(
                update(DefenseProfile)
                .where(DefenseProfile.id == profile_id)
                .values(status="failed")
            )
        finally:
            db.commit()
            db.close()

    asyncio.create_task(runner())


@router.post("/profiles")
async def create_profile(
    body: ProfileIn,
    user_id: int = Depends(get_current_user_id),
):
    db = get_session_factory()()
    try:
        profile = DefenseProfile(
            user_id=user_id,
            title=body.title,
            abstract=body.abstract,
            outline=body.outline,
            highlights=body.highlights,
            thesis_text=body.thesis_text,
            question_count=body.question_count,
            emphasis=body.emphasis,
            status="generating",
            bank_version=0,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        _generate_task(profile.id, body)
        return ok({"id": profile.id, "status": profile.status})
    finally:
        db.close()


@router.get("/profiles/{profile_id}")
async def get_profile(
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
):
    db = get_session_factory()()
    try:
        profile = db.get(DefenseProfile, profile_id)
        if profile is None or profile.user_id != user_id:
            raise HTTPException(status_code=404, detail="profile not found")
        bank = profile.knowledge_bank if profile.status == "active" else {}
        return ok(
            {
                "id": profile.id,
                "title": profile.title,
                "status": profile.status,
                "question_count": profile.question_count,
                "bank_version": profile.bank_version,
                "knowledge_bank": bank,
            }
        )
    finally:
        db.close()


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """软删 + 脱敏（docs/17 §4-D2：status=deleted + 清空 thesis_text/knowledge_bank）。"""
    db = get_session_factory()()
    try:
        profile = db.get(DefenseProfile, profile_id)
        if profile is None or profile.user_id != user_id:
            raise HTTPException(status_code=404, detail="profile not found")
        profile.status = "deleted"
        profile.thesis_text = None
        profile.knowledge_bank = {}
        db.commit()
        return ok({"id": profile.id, "status": profile.status})
    finally:
        db.close()


@router.post("/profiles/{profile_id}/bank")
async def regenerate_bank(
    profile_id: int,
    user_id: int = Depends(get_current_user_id),
):
    """重生成（可用现有字段重建；body 可选覆盖）。"""
    db = get_session_factory()()
    try:
        profile = db.get(DefenseProfile, profile_id)
        if profile is None or profile.user_id != user_id:
            raise HTTPException(status_code=404, detail="profile not found")
        body = ProfileIn(
            title=profile.title,
            abstract=profile.abstract,
            outline=profile.outline,
            highlights=profile.highlights,
            thesis_text=profile.thesis_text,
            question_count=profile.question_count,
            emphasis=profile.emphasis,
        )
        profile.status = "generating"
        profile.knowledge_bank = {}
        db.commit()
        _generate_task(profile.id, body)
        return ok({"id": profile.id, "status": "generating"})
    finally:
        db.close()
