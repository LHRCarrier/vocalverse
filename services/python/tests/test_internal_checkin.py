"""内部 REST 客户端与打卡触发（docs/21 §4 契约 · P0-6 回归）。

覆盖：camelCase 键名、Authorization Bearer、3s 超时、非 2xx 抛错（禁止静默吞）、
触发点幂等（一次成功/已同步短路/失败不阻塞收尾）、placement P0-6 键名回归。
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from app.core.internal_client import post_internal


def _install_fake_post(monkeypatch, resp_status: int = 200):
    captured = {}

    class FakeResp:
        status_code = resp_status

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"upstream {self.status_code}")

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json or {}
        captured["headers"] = headers or {}
        captured["timeout"] = timeout
        return FakeResp()

    monkeypatch.setattr("app.core.internal_client.httpx.post", fake_post)
    return captured


def test_post_internal_camelcase_bearer_timeout(monkeypatch):
    captured = _install_fake_post(monkeypatch)
    post_internal(
        "/internal/checkin",
        {"userId": 1, "practiceDate": "2026-09-06", "snapshot": {"overall": 80.0}},
    )
    assert captured["url"].endswith("/internal/checkin")
    assert captured["json"] == {
        "userId": 1,
        "practiceDate": "2026-09-06",
        "snapshot": {"overall": 80.0},
    }
    assert captured["headers"]["Authorization"].startswith("Bearer ")
    assert captured["timeout"] == 3.0


def test_post_internal_non_2xx_raises(monkeypatch):
    _install_fake_post(monkeypatch, resp_status=500)
    with pytest.raises(RuntimeError):
        post_internal("/internal/checkin", {"userId": 1})


@pytest.mark.asyncio
async def test_callback_level_sends_userId_not_user_id(monkeypatch):
    """P0-6 回归：placement 档位回写必须发 camelCase userId（Java DTO 期望键名）。"""
    captured = _install_fake_post(monkeypatch)

    from app.api.routes.placement import _callback_level

    await _callback_level(42, "L3")
    assert captured["json"] == {"userId": 42, "level": "L3"}
    assert "user_id" not in captured["json"]


# ----------------------------------------------------------------------
# 触发点（app.practice.service._post_session_checkin）
# ----------------------------------------------------------------------


def _session():
    return SimpleNamespace(
        kind="dialog", checkin_synced_at=None, user_id=1, id=7, turn_count=5, duration_s=120
    )


def _fake_db(rows):
    class _ScalarIter:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return iter(self._items)

    class FakeDb:
        def __init__(self):
            self.committed = False
            self.rolled = False

        def execute(self, stmt):
            return _ScalarIter(rows)

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled = True

    return FakeDb()


def _attempt():
    return SimpleNamespace(
        overall_score=Decimal("81.5"),
        pron_score=Decimal("83.0"),
        gram_score=Decimal("79.5"),
        flu_score=Decimal("82.0"),
    )


@pytest.mark.asyncio
def test_checkin_trigger_success_syncs_once(monkeypatch):
    captured = _install_fake_post(monkeypatch)
    db = _fake_db([_attempt()])
    session = _session()

    from app.practice import service

    service._post_session_checkin(db, session)

    body = captured["json"]
    assert list(body) == ["userId", "practiceDate", "sessionId", "snapshot"]
    assert body["userId"] == 1
    assert body["sessionId"] == 7
    assert body["snapshot"] == {
        "overall": 81.5,
        "pron": 83.0,
        "gram": 79.5,
        "fluency": 82.0,
        "turns": 5,
        "durationS": 120,
    }
    assert body["practiceDate"].count("-") == 2  # ISO 日期
    assert session.checkin_synced_at is not None
    assert db.committed


@pytest.mark.asyncio
def test_checkin_trigger_skips_when_already_synced(monkeypatch):
    _install_fake_post(monkeypatch)
    db = _fake_db([_attempt()])
    session = _session()
    session.checkin_synced_at = "already"  # 非 None 即短路（真实值为 datetime）

    from app.practice import service

    service._post_session_checkin(db, session)
    assert not db.committed


@pytest.mark.asyncio
def test_checkin_trigger_skips_non_dialog(monkeypatch):
    _install_fake_post(monkeypatch)
    db = _fake_db([_attempt()])
    session = _session()
    session.kind = "sing"

    from app.practice import service

    service._post_session_checkin(db, session)
    assert not db.committed


@pytest.mark.asyncio
def test_checkin_trigger_failure_does_not_block(monkeypatch):
    monkeypatch.setattr(
        "app.core.internal_client.httpx.post",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("java down")),
    )
    db = _fake_db([_attempt()])
    session = _session()

    from app.practice import service

    service._post_session_checkin(db, session)
    assert session.checkin_synced_at is None  # 留 NULL：P2 补扫可重试
    assert db.rolled
