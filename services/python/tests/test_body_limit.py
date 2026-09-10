"""请求体大小护栏测试（2026-09-10 · P0-6）。

背景：FastAPI 解析 body 早于依赖求解（`.venv/.../fastapi/routing.py:430` vs `:481`），
Starlette 对 >1MB 的 multipart part 落盘且无总量上限 → **匿名**大 body 可打爆容器
（拷问报告 §1 Top 6）。修复：`app/core/body_limit.py` 的 ASGI 中间件在路由前拦截。

**修复前必失败证据**：`test_oversized_content_length_rejected_before_app`（无中间件时
内层 app 会被调用且不会产生 413）与 `test_oversized_body_end_to_end_413`
（实测 21MB body 打到普通端点：修复前是 422/200，修复后 413 + envelope 41301）。

依据：docs/06 §8（≤20MB）、docs/api/error-codes.md:22（41301）、docs/api/envelope.md。
"""

from __future__ import annotations

import json

from app.core.body_limit import BodySizeLimitMiddleware

LIMIT = 1024  # 单测用 1KB 上限，避免造 20MB 数据


async def _run(app, *, headers, messages):
    """装配中间件并回放一段 ASGI 交换，返回 (sent_messages, app_called)。"""
    sent: list[dict] = []
    stats = {"calls": 0, "bytes": 0}
    queue = list(messages)

    async def receive():
        return queue.pop(0)

    async def send(message):
        sent.append(message)

    async def inner(scope, recv, snd):
        # 内层 app **读完 body**（模拟 FastAPI 解析 multipart 的真实行为）：
        # 护栏只在下游读取时计数，若假 app 不读，chunked 用例会假绿。
        stats["calls"] += 1
        while True:
            msg = await recv()
            stats["bytes"] += len(msg.get("body", b"") or b"")
            if not msg.get("more_body"):
                break
        await snd({"type": "http.response.start", "status": 200, "headers": []})
        await snd({"type": "http.response.body", "body": b"ok"})

    mw = BodySizeLimitMiddleware(inner, max_bytes=LIMIT)
    await mw({"type": "http", "headers": headers}, receive, send)
    return sent, stats


def _status(sent: list[dict]) -> int:
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _body(sent: list[dict]) -> dict:
    raw = next(m["body"] for m in sent if m["type"] == "http.response.body")
    return json.loads(raw)


async def test_oversized_content_length_rejected_before_app():
    """声明超限 → 立即 413（**内层 app 根本不被调用**，即不解析/不落盘）。"""
    sent, stats = await _run(
        None,
        headers=[(b"content-length", str(LIMIT + 1).encode())],
        messages=[{"type": "http.request", "body": b"x" * (LIMIT + 1), "more_body": False}],
    )
    assert _status(sent) == 413
    body = _body(sent)
    assert body["code"] == 41301 and body["data"] is None
    assert stats["calls"] == 0, "超限请求不得进入下游（不解析 body）"


async def test_within_limit_passes_through():
    sent, stats = await _run(
        None,
        headers=[(b"content-length", b"16")],
        messages=[{"type": "http.request", "body": b"x" * 16, "more_body": False}],
    )
    assert _status(sent) == 200
    assert stats["calls"] == 1


async def test_chunked_body_without_content_length_is_counted():
    """分块传输（无 Content-Length）：累计超限 → 413（护栏在 receive 层计数）。"""
    sent, stats = await _run(
        None,
        headers=[],
        messages=[
            {"type": "http.request", "body": b"x" * 600, "more_body": True},
            {"type": "http.request", "body": b"x" * 600, "more_body": False},
        ],
    )
    assert _status(sent) == 413
    assert _body(sent)["code"] == 41301


async def test_understated_content_length_still_guarded():
    """声明值小于实际（伪造 Content-Length）→ 仍被 receive 层护栏拦住。"""
    sent, _ = await _run(
        None,
        headers=[(b"content-length", b"10")],  # 撒谎：声称只有 10 字节
        messages=[
            {"type": "http.request", "body": b"x" * 800, "more_body": True},
            {"type": "http.request", "body": b"x" * 800, "more_body": False},
        ],
    )
    assert _status(sent) == 413


async def test_websocket_scope_passthrough():
    """非 http scope（websocket/lifespan）直通，不干预。"""
    sent: list[dict] = []
    called = {"n": 0}

    async def inner(scope, recv, snd):
        called["n"] += 1

    mw = BodySizeLimitMiddleware(inner, max_bytes=LIMIT)
    await mw({"type": "websocket"}, None, None)
    assert called["n"] == 1 and sent == []


# ---------------------------------------------------------------------------
# 端到端：真实应用 + 真实请求（不依赖鉴权端点，走 /api/v1/events）
# ---------------------------------------------------------------------------
def test_oversized_body_end_to_end_413(client):
    """21MB body（超 20MB+1MB 上限）→ 413 + envelope 41301，且**早于**鉴权/校验。"""
    payload = b"x" * (22 * 1024 * 1024)
    resp = client.post(
        "/api/v1/events",
        content=payload,
        headers={"Content-Type": "application/json"},
    )
    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert body["code"] == 41301
    assert set(body) == {"code", "message", "data"}


def test_normal_sized_request_unaffected(client, auth_headers):
    """正常体积请求不受影响（回归护栏：不误杀业务请求）。"""
    import time

    resp = client.post(
        "/api/v1/events",
        json={
            "event_type": "page_view",
            "client_event_id": "size-ok",
            "occurred_at": int(time.time()),
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
