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
from app.api.routes import audio, health
from app.core.config import get_settings
from app.core.response import BizError
from app.core.trace import RequestIdLogFilter, RequestIdMiddleware

logger = logging.getLogger("vocalverse")
logger.addFilter(RequestIdLogFilter())  # 每条日志带 request_id（docs/06 §11）


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    logger.info("vocalverse python-api %s starting (env=%s)", __version__, settings.app_env)
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
app.add_middleware(RequestIdMiddleware)  # X-Request-Id 透传（docs/06 §11）
