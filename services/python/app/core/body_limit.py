"""请求体大小护栏（纯 ASGI 中间件）——2026-09-10 · P0-6 修复。

背景（`local/唱歌模块全链路拷问报告-2026-09-10.md` §1 Top 6）：
FastAPI 在**解析 body 之后**才求解依赖（`.venv/.../fastapi/routing.py:430` 的
`await request.form()` 先于 `:481` 的 `solve_dependencies`），且 Starlette 对 >1MB 的
multipart part 会 spool 到临时盘（`starlette/formparsers.py:147`）而没有总量上限 →
**匿名**请求即可让 8000 端口把任意大小数据落盘并读进内存（`mem_limit 2g` + 宿主 bind
mount），可打死 uvicorn（连带 SSE/评分全断）。`app/api/routes/singing.py` 的 20MB 校验
发生在 `await audio.read()` **之后**，是"读完再判"，挡不住这一点。

修法（组长 2026-09-10 拍板方案 A）：**路由前**拦——
1. 有 `Content-Length` → 直接比对上限，超限立即 413（**不读 body**）；
2. 分块传输（无 `Content-Length`）→ 包一层 `receive` 计数护栏，累计超限即中断并 413。

设计约束：
- **纯 ASGI**（不依赖 FastAPI/Starlette 内部 API）→ 可用假 scope/receive/send 直接单测；
- 响应体仍是统一 envelope（`{code:41301,message,data:null}`），与 `docs/api/envelope.md` /
  `docs/api/error-codes.md:22`（41301 = 音频超过 20MB）一致；
- 若下游**已开始**响应（`http.response.start` 已发出）则不再抢发 413，改为原样抛出
  （避免"双响应"破坏连接语义）。

依据：docs/06 §8（音频上传 ≤20MB/180s）、docs/api/error-codes.md:22、docs/21 §2.1 op24。
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["BodySizeLimitMiddleware", "BodyTooLargeError"]


class BodyTooLargeError(Exception):
    """下游（解析阶段）触发的超限信号：由本中间件统一转 413。"""


class BodySizeLimitMiddleware:
    """按字节数限制请求体的 ASGI 中间件（全局生效，默认上限见 main.py 注册处）。"""

    def __init__(self, app: Any, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":  # websocket/lifespan 直通
            await self.app(scope, receive, send)
            return

        # ① 快路径：Content-Length 已声明 → 不读 body 直接判定
        declared = self._declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._send_413(send)
            return

        # ② 慢路径：分块/未声明/声明值不可信 → 计数护栏（声明值小于实际时也拦得住）
        seen = 0
        started = False

        async def limited_receive() -> dict:
            nonlocal seen
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body", b"") or b"")
                if seen > self.max_bytes:
                    raise BodyTooLargeError(self.max_bytes)
            return message

        async def send_wrapper(message: dict) -> None:
            nonlocal started
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, send_wrapper)
        except BodyTooLargeError:
            if started:  # 已经回了头，无法再改状态码
                raise
            await self._send_413(send)

    @staticmethod
    def _declared_length(scope: dict) -> int | None:
        for key, value in scope.get("headers") or []:
            if key.lower() == b"content-length":
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
        return None

    @staticmethod
    async def _send_413(send: Any) -> None:
        body = json.dumps(
            {"code": 41301, "message": "audio too large (> 20MB)", "data": None},
            ensure_ascii=False,
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
