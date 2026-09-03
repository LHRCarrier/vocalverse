"""内部回调 ``POST /internal/level`` 请求体契约单测（C2 修复：键名 userId）。

docs/21 §5 / local/34 D-2 契约真源：``{userId, level, source, levelAt}``。
本测试锁定「键名必须是 userId（而非 user_id）」——这是 C2/P0-6 曾导致定档回写 100% 断的点。
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.api.routes.placement import _level_callback_payload


def test_callback_payload_uses_user_id():
    p = _level_callback_payload(7, "L3", datetime(2026, 1, 1, tzinfo=UTC))
    assert p["userId"] == 7
    assert "user_id" not in p  # C2：原 user_id 键名错误
    assert p["level"] == "L3"
    assert p["source"] == "placement"
    assert p["levelAt"] == "2026-01-01T00:00:00+00:00"


def test_callback_payload_roundtrips_json():
    """JSON 序列化后键名仍为 userId（前端/Java jackson 反序列化的关键）。"""
    import json

    body = json.loads(json.dumps(_level_callback_payload(1, "L4", datetime.now(UTC))))
    assert body["userId"] == 1
    assert body["source"] == "placement"
