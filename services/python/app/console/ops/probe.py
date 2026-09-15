"""依赖探测（docs/50 §9.4：``probe_dependencies()`` 单点真源）。

**为什么抽成函数**：既有 ``/readyz`` 是硬编码 ``status:"ready"`` 的假信号（探针为空），
而控制台 ``ops/services`` 又要展示依赖状态。两处各自实现必然漂移，所以规定
**``/readyz`` 与 ``GET /api/v1/console/ops/services`` 共用本函数**，
口径永远一致；``/healthz`` 返回体**一个字都不改**（``tests/test_health.py`` 断言精确相等）。

Redis 的"必需性"取自 ``APP_REDIS_REQUIRED``（默认 false = 内存 fallback 可起，
docs/06 §10.2 降级语义）：不可用但非必需 → 总体仍 ``ready``，条目里如实报 ``ok=false``。
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings

STATUS_READY = "ready"
STATUS_DEGRADED = "degraded"
STATUS_NOT_READY = "not_ready"


async def probe_dependencies(redis_timeout_s: float = 1.0) -> dict[str, Any]:
    """探测数据库与 Redis，返回结构化结果（``/readyz`` 与控制台共用）。"""
    settings = get_settings()
    items = [
        await _probe_database(),
        await _probe_redis(redis_timeout_s),
    ]
    required_failed = [i for i in items if i["required"] and not i["ok"]]
    optional_failed = [i for i in items if not i["required"] and not i["ok"]]
    if required_failed:
        status = STATUS_NOT_READY
    elif optional_failed:
        status = STATUS_DEGRADED
    else:
        status = STATUS_READY
    return {
        "status": status,
        "checked_at": datetime.now(UTC).isoformat(),
        "items": items,
        # 兼容既有 /readyz 响应体字段（tests/test_health.py 只断言 status，但前端在用）
        "app_env": settings.app_env,
        "asr": settings.asr_model,
        "tts": settings.tts_provider,
    }


async def _probe_database() -> dict[str, Any]:
    started = time.perf_counter()
    ok = False
    detail = ""
    try:
        ok = await asyncio.to_thread(_select_one)
    except Exception as exc:  # noqa: BLE001 - 探测失败即如实上报，绝不冒泡
        detail = f"{exc.__class__.__name__}: {exc}"[:200]
    return {
        "name": "database",
        "ok": bool(ok),
        "required": True,
        "detail": detail or ("ok" if ok else "SELECT 1 失败"),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def _select_one() -> bool:
    from sqlalchemy import text

    from app.db import get_engine

    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))
    return True


async def _probe_redis(timeout_s: float) -> dict[str, Any]:
    from app.core.redis_client import redis_ping

    settings = get_settings()
    # "没配 Redis"与"配了但连不上"必须区分（docs/06 §10.2：内存 backend 是**合法**运行模式）：
    # 前者不该把容器标成不健康（否则本地/CI 永远 degraded），后者才是真故障。
    if settings.testing or not settings.redis_url:
        return {
            "name": "redis",
            "ok": True,
            "required": False,
            "detail": "未启用（testing 或未配置 URL）：使用内存 fallback",
            "latency_ms": 0,
        }
    started = time.perf_counter()
    ok = await redis_ping(timeout_s)
    return {
        "name": "redis",
        "ok": ok,
        "required": bool(settings.redis_required),
        "detail": "PING ok" if ok else "已配置但 PING 失败",
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def probe_dependencies_sync(redis_timeout_s: float = 1.0) -> dict[str, Any]:
    """同步探测（供非 async 上下文/脚本；``SELECT 1`` 走独立短连接直接阻塞调用方）。"""
    settings = get_settings()
    started = time.perf_counter()
    try:
        ok = _select_one()
        detail = "ok" if ok else "SELECT 1 失败"
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{exc.__class__.__name__}: {exc}"[:200]
    db_item = {
        "name": "database",
        "ok": bool(ok),
        "required": True,
        "detail": detail,
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }
    from app.core.redis_client import redis_available

    r_started = time.perf_counter()
    if settings.testing or not settings.redis_url:
        r_ok, r_detail = True, "未启用（testing 或未配置 URL）：使用内存 fallback"
    else:
        r_ok = redis_available(redis_timeout_s)
        r_detail = "PING ok" if r_ok else "已配置但 PING 失败"
    redis_item = {
        "name": "redis",
        "ok": r_ok,
        "required": bool(settings.redis_required) and not settings.testing,
        "detail": r_detail,
        "latency_ms": int((time.perf_counter() - r_started) * 1000),
    }
    items = [db_item, redis_item]
    if any(i["required"] and not i["ok"] for i in items):
        status = STATUS_NOT_READY
    elif any(not i["ok"] for i in items):
        status = STATUS_DEGRADED
    else:
        status = STATUS_READY
    return {
        "status": status,
        "checked_at": datetime.now(UTC).isoformat(),
        "items": items,
        "app_env": settings.app_env,
        "asr": settings.asr_model,
        "tts": settings.tts_provider,
    }


__all__ = [
    "STATUS_DEGRADED",
    "STATUS_NOT_READY",
    "STATUS_READY",
    "probe_dependencies",
    "probe_dependencies_sync",
]
