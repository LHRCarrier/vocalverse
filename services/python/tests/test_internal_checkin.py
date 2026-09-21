"""内部 REST 客户端与手动打卡（docs/21 §4 契约 · P0-6 回归）。

覆盖：camelCase 键名、Authorization Bearer、3s 超时、非 2xx 抛错（禁止静默吞）、
placement P0-6 键名回归；**手动打卡**（2026-09-21 改版）——当日聚合、重复打卡不自增、
无练习也可打卡、Java 失败明确 50002；以及「练习收尾不再自动委托打卡」的回归守卫。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.core.internal_client import post_internal
from app.core.response import BizError
from app.db import get_session_factory
from app.models import Attempt, User
from app.models import Session as DbSession
from app.models.base import AttemptKinds, SessionKinds, SessionStatus
from app.practice import checkin as checkin_service


def _install_fake_post(monkeypatch, resp_status: int = 200):
    captured = {"calls": []}

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
        captured["calls"].append(json or {})
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
# 手动打卡（app.practice.checkin.perform_checkin）
# ----------------------------------------------------------------------


def _new_user() -> int:
    db = get_session_factory()()
    try:
        user = User(username="checkin_u", nickname="c", password_hash="x")
        db.add(user)
        db.flush()
        return int(user.id)
    finally:
        db.close()


def _seed_dialog(
    user_id: int,
    *,
    completed_at: datetime,
    turn_count: int,
    duration_s: int,
    overall: float | None,
    pron: float | None = None,
    gram: float | None = None,
    flu: float | None = None,
) -> int:
    """建 1 个已完成 dialog 会话 + 1 条评分 attempt（overall=None 表示评分失败快照）。"""
    db = get_session_factory()()
    try:
        session = DbSession(
            user_id=user_id,
            kind=SessionKinds.DIALOG,
            status=SessionStatus.COMPLETED,
            started_at=completed_at - timedelta(minutes=5),
            completed_at=completed_at,
            turn_count=turn_count,
            duration_s=duration_s,
        )
        db.add(session)
        db.flush()
        if overall is not None or pron is not None:
            db.add(
                Attempt(
                    user_id=user_id,
                    session_id=session.id,
                    kind=AttemptKinds.DIALOG_SPEECH,
                    overall_score=None if overall is None else Decimal(str(overall)),
                    pron_score=None if pron is None else Decimal(str(pron)),
                    gram_score=None if gram is None else Decimal(str(gram)),
                    flu_score=None if flu is None else Decimal(str(flu)),
                )
            )
        db.commit()
        return int(session.id)
    finally:
        db.close()


def _seed_null_attempt(session_id: int, user_id: int) -> None:
    """评分失败快照（overall NULL）：不得参与当日最佳分/最新子分。"""
    db = get_session_factory()()
    try:
        db.add(
            Attempt(
                user_id=user_id,
                session_id=session_id,
                kind=AttemptKinds.DIALOG_SPEECH,
            )
        )
        db.commit()
    finally:
        db.close()


def test_manual_checkin_aggregates_day_and_delegates(monkeypatch):
    captured = _install_fake_post(monkeypatch)
    uid = _new_user()
    now = datetime.now(UTC)
    # 当日两个会话（一个 81.5 分、一个 90 分）+ 一条评分失败 attempt（overall NULL 不参与最佳分）
    _seed_dialog(
        uid,
        completed_at=now - timedelta(hours=3),
        turn_count=6,
        duration_s=200,
        overall=81.5,
        pron=83.0,
        gram=79.5,
        flu=82.0,
    )
    latest = _seed_dialog(
        uid,
        completed_at=now - timedelta(hours=1),
        turn_count=8,
        duration_s=260,
        overall=90.0,
        pron=84.0,
        gram=80.0,
        flu=81.0,
    )
    _seed_null_attempt(latest, uid)
    # 昨天一个会话：不得计入今天
    _seed_dialog(
        uid,
        completed_at=now - timedelta(days=1),
        turn_count=5,
        duration_s=150,
        overall=99.0,
        pron=99.0,
        gram=99.0,
        flu=99.0,
    )

    result = checkin_service.perform_checkin(uid, now.date())

    body = captured["json"]
    assert list(body) == ["userId", "practiceDate", "sessionId", "snapshot"]
    assert body["userId"] == uid
    assert body["sessionId"] == latest  # 最近一次会话
    assert body["practiceDate"] == now.date().isoformat()
    assert body["snapshot"] == {
        "overall": 90.0,  # 当日最佳（不是最后一次 90？是——两次 81.5/90 取最大）
        "pron": 84.0,
        "gram": 80.0,
        "fluency": 81.0,
        "turns": 14,  # 6 + 8（合计）
        "durationS": 460,  # 200 + 260
        "practiceCount": 2,  # 当日已完成会话数（显式回传，Java 侧不再自增）
    }
    assert result == {"date": now.date().isoformat(), "practiceCount": 2, "overall": 90.0}


def test_manual_checkin_repeat_is_idempotent(monkeypatch):
    """同一天重复打卡：两次 payload 的 practiceCount 相同（不自增）——旧自动委托的 +1 语义已废。"""
    captured = _install_fake_post(monkeypatch)
    uid = _new_user()
    now = datetime.now(UTC)
    _seed_dialog(uid, completed_at=now, turn_count=4, duration_s=100, overall=70.0)

    checkin_service.perform_checkin(uid, now.date())
    checkin_service.perform_checkin(uid, now.date())

    assert len(captured["calls"]) == 2
    assert captured["calls"][0]["snapshot"]["practiceCount"] == 1
    assert captured["calls"][1]["snapshot"]["practiceCount"] == 1


def test_manual_checkin_without_practice_still_checks_in(monkeypatch):
    captured = _install_fake_post(monkeypatch)
    uid = _new_user()

    result = checkin_service.perform_checkin(uid, datetime.now(UTC).date())

    snap = captured["json"]["snapshot"]
    assert snap["practiceCount"] == 0
    assert snap["overall"] is None
    assert captured["json"]["sessionId"] is None
    assert result["practiceCount"] == 0


def test_manual_checkin_delegate_failure_raises_50002(monkeypatch):
    monkeypatch.setattr(
        "app.core.internal_client.httpx.post",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("java down")),
    )
    uid = _new_user()
    with pytest.raises(BizError) as exc:
        checkin_service.perform_checkin(uid, datetime.now(UTC).date())
    assert exc.value.code == 50002


def test_parse_practice_date_defaults_to_utc_today_and_rejects_bad_format():
    assert checkin_service.parse_practice_date(None) == datetime.now(UTC).date()
    assert checkin_service.parse_practice_date("2026-09-21").isoformat() == "2026-09-21"
    with pytest.raises(BizError) as exc:
        checkin_service.parse_practice_date("09/21/2026")
    assert exc.value.code == 42201


def test_complete_session_no_longer_triggers_checkin(monkeypatch):
    """回归守卫（2026-09-21）：练习收尾不得再自动委托打卡（「没操作却自动打卡」的根因）。"""
    captured = _install_fake_post(monkeypatch)
    uid = _new_user()
    session_id = _seed_dialog(
        uid,
        completed_at=datetime.now(UTC),
        turn_count=6,
        duration_s=200,
        overall=80.0,
        pron=80.0,
        gram=80.0,
        flu=80.0,
    )

    from app.practice import service

    service.complete_session(session_id, llm=None)  # type: ignore[arg-type]

    assert captured["calls"] == []  # 没有任何 /internal/checkin 调用
    assert not hasattr(service, "_post_session_checkin")


# ----------------------------------------------------------------------
# 路由（POST /api/v1/checkin）
# ----------------------------------------------------------------------


def test_post_checkin_route_envelope_and_default_date(client, monkeypatch):
    captured = _install_fake_post(monkeypatch)
    resp = client.post(
        "/api/v1/checkin",
        json={"date": "2026-09-21"},
        headers={"X-Test-User-Id": "1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    assert body["data"] == {"date": "2026-09-21", "practiceCount": 0, "overall": None}
    assert captured["json"]["userId"] == 1
    assert captured["json"]["practiceDate"] == "2026-09-21"


def test_post_checkin_route_rejects_bad_date(client, monkeypatch):
    _install_fake_post(monkeypatch)
    resp = client.post(
        "/api/v1/checkin",
        json={"date": "21-09-2026"},
        headers={"X-Test-User-Id": "1"},
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 42201
