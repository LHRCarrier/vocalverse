"""VocalVerse Python API 入口。

启动：uv run uvicorn app.main:app --reload --port 8000
文档：http://localhost:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import audio, defense, events, health, placement, practice, recommendations
from app.core.config import get_settings
from app.core.response import BizError
from app.core.trace import RequestIdLogFilter, RequestIdMiddleware

logger = logging.getLogger("vocalverse")
logger.addFilter(RequestIdLogFilter())  # 每条日志带 request_id（docs/06 §11）


def _prewarm_asr() -> None:
    """预热 whisper（首个请求免 30s 卡顿）；失败仅告警不阻塞启动（docs/06 §8）。"""
    try:
        settings = get_settings()
        if settings.testing or settings.asr_model == "":
            return
        from app.audio.base import get_asr_client

        client = get_asr_client()
        if client and getattr(client, "_get_model", None):
            client._get_model()  # noqa: SLF001 - 预热专用
            logger.info("whisper 模型预热完成")
    except Exception as exc:
        logger.warning("whisper 预热失败（不阻塞启动）: %s", exc)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info("vocalverse python-api %s starting (env=%s)", __version__, settings.app_env)
    _prewarm_asr()  # whisper 预热（docs/06 §8：防首个请求卡 30s；testing/无模型跳过）
    yield
    logger.info("vocalverse python-api stopped")


app = FastAPI(
    title="VocalVerse Python API",
    version=__version__,
    description="语音管线 / LLM 场景扮演 / 唱歌评分 / 推荐（docs/06 第 1 章：热路径直连 Python）",
    lifespan=lifespan,
)


@app.exception_handler(BizError)
async def biz_error_handler(_: Request, exc: BizError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"code": 42201, "message": "request validation failed", "data": exc.errors()},
    )


app.include_router(health.router)
app.include_router(audio.router)
app.include_router(practice.router)
app.include_router(defense.router)
app.include_router(placement.router)
app.include_router(events.router)
app.include_router(recommendations.router)
# Agent Lab（test-only 测试台；默认关闭，开启才注册 → 404；删除无影响，见 agent_lab.py 删除清单）
if get_settings().agent_lab_enabled:
    from app.api.routes import agent_lab

    app.include_router(agent_lab.router)
# 流利度特征测试台（test-only 前端联调；默认关闭，开启才注册 → 404；删除无影响，
# 见 fluency_preview.py 删除清单）
if get_settings().fluency_preview_enabled:
    from app.api.routes import fluency_preview

    app.include_router(fluency_preview.router)
# 影子跟读测试台（test-only 前端联调；默认关闭，开启才注册 → 404；删除无影响，
# 见 shadow_preview.py 删除清单）
if get_settings().shadow_preview_enabled:
    from app.api.routes import shadow_preview

    app.include_router(shadow_preview.router)
# Placement Lab（入学测试联调测试台；test-only；默认关闭，开启才注册 → 404；删除无影响，
# 见 placement_lab.py 删除清单）
if get_settings().placement_lab_enabled:
    from app.api.routes import placement_lab

    app.include_router(placement_lab.router)
app.add_middleware(RequestIdMiddleware)  # X-Request-Id 透传（docs/06 §11）
