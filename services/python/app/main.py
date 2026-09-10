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
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    audio,
    defense,
    events,
    free_chat,
    health,
    media,
    placement,
    practice,
    reading,
    reading_tts,
    recommendations,
)
from app.console.api.deps import ConsoleBizError
from app.console.ops.middleware import HttpMetricsMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging
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

# 日志先配置再用（docs/48 B4：此前无 handler → logger.info 零输出）
configure_logging()
logger = logging.getLogger("vocalverse")
logger.addFilter(RequestIdLogFilter())  # 每条日志带 request_id（docs/06 §11）


async def _prewarm_asr() -> None:
    """预热 whisper（首个请求免 30s 卡顿）；失败仅告警不阻塞启动（docs/06 §8）。

    vasr-09：模型加载是 CPU 重活 → 必须进线程（旧实现同步 `_get_model()` 跑在事件循环，
    阻塞就绪探测 10~30s）；显式 `warm()` 替代 `getattr(client, '_get_model')` 脆弱探针。
    """
    import asyncio

    try:
        settings = get_settings()
        if settings.testing or settings.asr_model == "":
            return
        from app.audio.base import get_asr_client

        client = get_asr_client()
        if client is not None:
            await asyncio.to_thread(client.warm)
            logger.info("whisper 模型预热完成")
    except Exception as exc:
        logger.warning("whisper 预热失败（不阻塞启动）: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("vocalverse python-api %s starting (env=%s)", __version__, settings.app_env)
    await _prewarm_asr()  # whisper 预热（docs/06 §8：防首个请求卡 30s；testing/无模型跳过）
    # TTS 预合成预热（docs/06 §8「开场/常用句预合成」；后台异步不阻塞启动；testing 跳过）
    from app.audio.warmup import schedule_startup_warmup

    app.state.tts_warm_task = schedule_startup_warmup()
    # 听书任务孤儿清扫（docs/45 §5.2：进程崩溃残留 running/queued → failed，不假转圈）
    from app.reading import orchestrator as reading_orchestrator

    try:
        swept = reading_orchestrator.sweep_orphans()
        if swept:
            logger.info("听书预合成任务孤儿清扫完成：%s 个", swept)
    except Exception as exc:  # 数据库未就绪等：仅告警不阻塞启动
        logger.warning("听书任务孤儿清扫跳过（%s）", exc)
    # 控制台采集（docs/50 §8.3/§8.4）：trace sink 消费者 + 指标采集器
    from app.console.ops.runtime import start_collector, stop_collector
    from app.console.trace.sink import get_sink

    await get_sink().start()
    await start_collector()
    try:
        yield
    finally:
        # docs/50 §8.3 的排水必须在 finally：
        # uvicorn 会先等完在途连接再跑 lifespan shutdown，且 --timeout-graceful-shutdown
        # 默认无限 → 正常退出路径**也可能**根本不走到这里。故：
        # ① 排水自带超时（有界，绝不挂住进程）；② 超时未写出的条数计入 trace_dropped_total
        # （"丢了多少"必须在控制台可见，而不是静默消失）；③ 用 finally 保证异常退出也尝试。
        await stop_collector()
        try:
            remaining = await get_sink().stop()
            if remaining:
                logger.warning(
                    "trace sink 关闭超时，丢弃 %s 条（已计入 trace_dropped_total）", remaining
                )
        except Exception as exc:  # 采集关闭失败不得影响进程退出
            logger.warning("trace sink 关闭异常：%s", exc)
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


@app.exception_handler(ConsoleBizError)
async def console_error_handler(_: Request, exc: ConsoleBizError) -> JSONResponse:
    """控制台错误：比通用 BizError 多一个 ``data``（如 46002 的 ``required``、
    46007 的 ``suggestedStep``、46011 的 ``violations[]`` —— docs/50 §10.4 明确要求回传）。"""
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": exc.data},
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
app.include_router(free_chat.router)  # 自由对话（MVP，docs/14 §12：无状态 LLM 转发器）
app.include_router(defense.router)
app.include_router(placement.router)
app.include_router(events.router)
app.include_router(recommendations.router)
app.include_router(reading.router)  # 读书域（docs/45：书架/查词/生词/批注/进度/音色）
app.include_router(reading_tts.router)  # 听书（单句音频/预合成 SSE/任务）
app.include_router(media.router)  # 媒体（社区 S3 · docs/47 §4.1：图片/视频/头像上传与读取）
# 管理端控制台 · Python 侧端点（docs/50 §10.3）：运维/遥测 + 内容治理（library）。
# 鉴权走独立的控制台令牌（get_console_admin），与学习者 JWT 双密钥双 audience；
# 端点内部各自做功能位闸门（APP_OPS_TELEMETRY_ENABLED / APP_LLM_TRACE_ENABLED → 46014）。
from app.console.api.routes import library as console_library  # noqa: E402
from app.console.api.routes import ops as console_ops  # noqa: E402

app.include_router(console_ops.router)
app.include_router(console_library.router)
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
# HTTP 指标（docs/50 §8.4：http.request.* / http.inflight）——纯 ASGI，不缓冲 SSE 响应
app.add_middleware(HttpMetricsMiddleware)
# CORS（2026-09-10 打包壳方案 B：页面源 https://localhost、API 打到本机 http://<IP>:8000，
# 跨域 → 需 CORS）。开发靠 Vite 代理同源、容器靠 nginx 同源，均不触发；仅打包壳直连后端需要。
# allow_credentials=True ⇒ 禁止 allow_origins=["*"]，需精确列出后端地址（含 https://localhost）。
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://localhost",
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://192.168.0.104:5173",
        "http://192.168.0.104:8088",
        "http://localhost:8088",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
