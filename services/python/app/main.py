"""VocalVerse Python API 入口。

启动：uv run uvicorn app.main:app --reload --port 8000
文档：http://localhost:8000/docs
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import (
    audio,
    defense,
    events,
    free_chat,
    health,
    placement,
    practice,
    recommendations,
    singing,
)
from app.core.body_limit import BodySizeLimitMiddleware
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
    # 参考旋律提取扫描（唱歌 P0 D2/D6：启动扫描 + 周期扫描；testing 跳过）
    extract_stop = asyncio.Event()
    scanner_task: asyncio.Task | None = None
    if not settings.testing:
        from app.sing.jobs import run_due_jobs_until_stopped

        scanner_task = asyncio.create_task(run_due_jobs_until_stopped(extract_stop))
        logger.info(
            "pitch extract scanner started (interval=%ss)",
            settings.pitch_extract_scan_interval_s,
        )
    yield
    if scanner_task is not None:
        extract_stop.set()
        try:
            await asyncio.wait_for(scanner_task, timeout=5)
        except TimeoutError:
            scanner_task.cancel()
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


# HTTP 层异常（HTTPException）→ 统一 envelope（2026-09-10 · P0-5 修复）
#
# 背景：鉴权（core/auth.py）、限流（core/ratelimit.py）等 24 处走 `raise HTTPException(...)`，
# 而 FastAPI 默认 handler 返回 `{"detail": ...}`（非 envelope）→ **已登记的 40101/42901 永不出现**，
# 前端 `client.ts` 只能拿到 `body.code === undefined` → 抛 `ApiError(-1, 'HTTP 429')`，
# `api/sing.ts` 里「每小时 5 次」的 42901 分支成为死代码（拷问报告 §1 Top 5，
# 见 `local/唱歌模块全链路拷问报告-2026-09-10.md`）。
#
# 映射目标**全部取自已登记码表**（docs/api/error-codes.md，本 handler 不新增任何码）；
# 未登记的 4xx 兜底 40001、5xx 兜底 50002（安全网，实际抛出的状态码集合见下表注释）。
# `headers` 必须透传：42901 的契约要求携带 `Retry-After`（docs/api/error-codes.md:28）。
# 依据：docs/api/envelope.md（所有端点统一 envelope）、docs/21 §1.1 例外登记与 §6 码集对账。
_HTTP_STATUS_TO_CODE: dict[int, int] = {
    400: 40001,  # 参数错误
    401: 40101,  # 未登录 / token 失效（auth.py 三处）
    403: 40301,  # 无权限 / 非本资源归属
    404: 40401,  # 资源不存在（defense/placement/service 共 9 处）
    405: 40501,  # 方法不允许（Starlette 路由层）
    409: 40902,  # 会话状态不允许（站点语义更细者应改抛 BizError）
    410: 41001,  # 音频过期
    413: 41301,  # 音频超过 20MB（唱歌 41302 由 service 层 BizError 给出）
    422: 42201,  # 请求体校验（audio/placement：text required / no scored attempts 等）
    429: 42901,  # 限流（ratelimit.py；必须回 Retry-After）
    502: 50301,  # 上游（TTS/ASR）失败
    503: 50301,  # ASR/TTS 服务不可用
}


@app.exception_handler(HTTPException)
async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    """HTTPException → envelope（保留 Retry-After 等响应头）。"""
    code = _HTTP_STATUS_TO_CODE.get(exc.status_code)
    if code is None:
        code = 50002 if exc.status_code >= 500 else 40001
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": code, "message": str(exc.detail), "data": None},
        headers=getattr(exc, "headers", None),
    )


app.include_router(health.router)
app.include_router(audio.router)
app.include_router(practice.router)
app.include_router(
    singing.router
)  # 唱歌：整首上传/状态轮询/结果（M3 P0 D7；docs/21 §2.1 op 22~24）
app.include_router(free_chat.router)  # 自由对话（MVP，docs/14 §12：无状态 LLM 转发器）
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

# 请求体大小护栏（2026-09-10 · P0-6）：**必须在路由/依赖之前拦截**——FastAPI 解析 body
# （`request.form()`）早于鉴权依赖，Starlette 会把 >1MB 的 part spool 到临时盘且无总量上限，
# 匿名大 body 可打爆容器（细节与依据见 app/core/body_limit.py 模块说明）。
# 上限 = 音频上限 + 1MB：`max_upload_bytes`(20MB) 约束的是**音频文件本身**，multipart 封装
# （boundary/头部/其它字段）天然多出若干字节，留 1MB 余量避免"合规上传被边界拒绝"。
# 与 nginx `client_max_body_size 21m`（apps/web/nginx.conf）构成纵深防御：nginx 挡边缘、
# 本中间件挡直连（vite dev / 容器内网 / 其它入口）。
app.add_middleware(BodySizeLimitMiddleware, max_bytes=get_settings().max_upload_bytes + 1024 * 1024)
