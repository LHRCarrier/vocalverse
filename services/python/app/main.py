"""VocalVerse Python API 入口。

启动：uv run uvicorn app.main:app --reload --port 8000
文档：http://localhost:8000/docs
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import audio, defense, events, health, placement, practice, recommendations
from app.core.config import get_settings
from app.core.response import BizError
from app.core.trace import RequestIdLogFilter, RequestIdMiddleware

# HF 缓存约定（docs/06 §8：huggingface 被墙，一律本地缓存）——区分两种部署布局：
# · 方式 B 本地（services/python/app/main.py → 仓库根）：默认 HF_HOME=<仓库>/data/models
#   （宿主预下载的 HF 缓存结构）+ HF_HUB_OFFLINE=1；scripts/dev-up.ps1 显式注入同款。
# · 容器（Dockerfile WORKDIR /app + COPY . . → /app/app/main.py）：无「仓库根」概念，
#   不注入 HF_HOME/HF_HUB_OFFLINE，维持 HF 默认缓存路径（docs/06 §8 hf-cache 卷约定；
#   compose 当前未注入 HF 变量/未挂载 models——K03 未闭合，另立整改）。
# · HF_HUB_DISABLE_XET=1 两布局通用（docs/18：xet 通道 401 绕过，经典 HTTP 下载）。
# 必须在任何 huggingface_hub / faster_whisper 导入之前生效；用户进程已显式设置时尊重之
# (setdefault)。未设时首次 ASR 会尝试连 huggingface.co → SSL/连接失败 → items/audio 500
# （2026-09-04 实测）。
try:
    _repo_root = Path(__file__).resolve().parents[3]
except IndexError:
    _repo_root = None  # 容器布局：无第四级父目录（/app/app/main.py 只有 3 级），跳过本地缓存注入
if _repo_root is not None:
    os.environ.setdefault("HF_HOME", str(_repo_root / "data" / "models"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

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
app.add_middleware(RequestIdMiddleware)  # X-Request-Id 透传（docs/06 §11）
