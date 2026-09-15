"""HTTP 观测中间件（docs/50 §8.4：http.request.* 指标的数据源）。

纯 ASGI（不用 ``BaseHTTPMiddleware``）——既有 ``RequestIdMiddleware`` 同款理由：
``BaseHTTPMiddleware`` 会把 SSE 包成 anyio 内存流，破坏流式节奏（docs/06 §11 先例）。
本中间件只做计数/计时，**不碰响应体**，对 SSE 零影响。
"""

from __future__ import annotations

import re
import time

from app.console.ops.metrics import get_registry

#: 路径段归一（防 label 基数爆炸）：纯数字 / 长十六进制 → {id}
_ID_SEG = re.compile(r"^(?:\d+|[0-9a-fA-F]{8,})$")

REGISTRY = get_registry()


def normalize_route(path: str, route: object = None) -> str:
    """优先用路由模板（如 ``/api/v1/media/{public_id}``），无则按段归一。"""
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path[:120]
    parts = [("{id}" if _ID_SEG.match(p) else p) for p in path.split("/")]
    return "/".join(parts)[:120]


class HttpMetricsMiddleware:
    """记录请求数/时长直方图/错误数/在途数（collector 每 60s 快照成桶）。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        registry = get_registry()
        registry.add_gauge("http.inflight", 1)
        started = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = int(message.get("status", 0))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            registry.add_gauge("http.inflight", -1)
            try:
                route = normalize_route(scope.get("path", ""), scope.get("route"))
                labels = {"route": route}
                duration_ms = (time.perf_counter() - started) * 1000
                registry.incr("http.request.count", 1, labels)
                registry.observe("http.request.duration_ms", duration_ms, labels)
                status = status_holder["status"]
                if status >= 400:
                    registry.incr("http.request.error.count", 1, labels)
            except Exception:  # noqa: BLE001 - 观测失败绝不影响请求
                pass


__all__ = ["HttpMetricsMiddleware", "normalize_route"]
