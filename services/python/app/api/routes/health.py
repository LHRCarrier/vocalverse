"""健康检查：/healthz（liveness）、/readyz（PG/Redis，见 docs/06 第 11 章）。

**`/readyz` 修复（docs/50 §9.4）**：此前是硬编码 ``status:"ready"`` 的**假信号**——
什么都不探，容器编排据此认为"健康"。现改为调用 ``probe_dependencies()``，
并**与控制台 ``GET /api/v1/console/ops/services`` 共用同一函数**，两处口径不可能漂移。

``/healthz`` 返回体**一个字不改**（``tests/test_health.py`` 断言精确相等，且它是
liveness 语义：进程活着就够了，探依赖反而是反模式）。
"""

from typing import Any

from fastapi import APIRouter, Depends

from app.console.ops.probe import probe_dependencies
from app.core.config import Settings, get_settings
from app.core.response import Envelope, ok

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    return {"status": "alive"}


@router.get("/readyz")
async def readyz(settings: Settings = Depends(get_settings)) -> Envelope[Any]:
    """就绪探测：真实探 PG（SELECT 1）与 Redis（PING）；Redis 非必需时降级为 degraded。"""
    del settings
    return ok(await probe_dependencies())
