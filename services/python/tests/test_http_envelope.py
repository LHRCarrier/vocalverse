"""HTTP 层异常 → envelope 契约测试（2026-09-10 · P0-5）。

背景（`local/唱歌模块全链路拷问报告-2026-09-10.md` §1 Top 5）：鉴权/限流等 24 处走
`raise HTTPException(...)`，FastAPI 默认 handler 返回 `{"detail": ...}` → **已登记的
40101/42901/50003 永不出现**，前端 `client.ts` 拿到 undefined code → 抛
`ApiError(-1, 'HTTP 429')`，文案映射变死代码。

**修复前必失败证据**：本文件 `test_unauthenticated_returns_envelope_401`（修复前 body 为
`{"detail":"missing bearer token"}`、无 `code` 键）与
`test_http_exception_429_maps_and_keeps_retry_after`（修复前无 handler，直接抛默认响应）。

依据：docs/api/envelope.md（统一 envelope）、docs/api/error-codes.md（映射目标均已登记，
本 handler 不新增码）、docs/21 §1.1 例外登记 / §6 码集对账。
"""

from __future__ import annotations

from app.core.response import Envelope
from fastapi import HTTPException


def test_unauthenticated_returns_envelope_401(client):
    """无令牌 → 401 且 body 为 envelope（code=40101），不再是 `{"detail": ...}`。"""
    resp = client.get("/api/v1/songs")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == 40101, body
    assert body["data"] is None
    assert isinstance(body["message"], str) and body["message"]
    # 形状与成功响应同源（envelope 三键）
    assert set(body) == {"code", "message", "data"}


def test_http_exception_404_maps_to_40401(client, auth_headers):
    """defense 路由的 HTTPException(404) → envelope code=40401（与 BizError 的 404 同形状）。"""
    resp = client.get("/api/v1/defense/profiles/999999", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert body["code"] == 40401, body
    assert set(body) == {"code", "message", "data"}


def test_http_exception_429_maps_and_keeps_retry_after():
    """429 → 42901 且 **保留 Retry-After 头**（限流契约：前端要显示剩余秒数）。

    直接调 handler（避免真扣限流额度）：`ratelimit._limit_error` 抛的 HTTPException
    带 `Retry-After`，handler 必须透传 headers，否则前端拿不到重试时间。
    """
    import asyncio

    from app.main import http_error_handler

    exc = HTTPException(
        status_code=429, detail="rate limited (sing)", headers={"Retry-After": "3600"}
    )
    resp = asyncio.run(http_error_handler(None, exc))  # type: ignore[arg-type]
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "3600"
    import json

    body = json.loads(bytes(resp.body))
    assert body["code"] == 42901
    assert body["message"] == "rate limited (sing)"


def test_error_envelope_matches_biz_error_shape(client):
    """BizError 与 HTTPException 两条路径产出**同一 envelope 形状**（docs/api/envelope.md）。"""
    schema = set(Envelope.model_fields)
    assert schema == {"code", "message", "data"}
    biz = client.get("/api/v1/songs/999999", headers={"X-Test-User-Id": "1"})
    assert biz.status_code == 404 and biz.json()["code"] == 40401
    unauth = client.get("/api/v1/songs")
    assert unauth.status_code == 401 and unauth.json()["code"] == 40101
