"""健康检查：/healthz（liveness）、/readyz（PG/Redis，见 docs/06 第 11 章）。"""

from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.core.response import Envelope, ok

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "alive"}


@router.get("/readyz")
async def readyz(settings: Settings = Depends(get_settings)) -> Envelope[Any]:
    # M1：骨架阶段不强制连 PG/Redis；M2 起接入真实探测
    return ok(
        {
            "status": "ready",
            "app_env": settings.app_env,
            "asr": settings.asr_model,
            "tts": settings.tts_provider,
        }
    )
