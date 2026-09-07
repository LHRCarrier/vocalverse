"""P0-3 越权(P0-8 幂等)失败用例(docs/19 P0-3/P0-8 · 审计 R-05,2026-09-07)。

修复前(2026-09-07 复现逻辑):report 读取无归属过滤 → 任何登录用户按 id 可读任意报告;
turn/complete 无归属校验(StateStore 按 session_id 为键、无归属概念)→ 可操作他人会话;
complete_session 重复调用撞 uq_reports_scope_period → 500。

修复后:
- 越权统一按"资源不存在"处理 → 404/40401(docs/api/error-codes.md 40301 行登记口径,
  不泄露存在性);
- 重复 complete → 200 且返回同一 report_id(短路 + upsert 兜底)。
"""

from __future__ import annotations

from app.db import get_session_factory
from app.models import Report, Scenario
from fastapi.testclient import TestClient
from sqlalchemy import select

_OTHER_HEADERS = {"X-Test-User-Id": "2"}


def _create_dialog_session(client: TestClient, auth_headers) -> int:
    """建一个已发布场景 + 建会话(返回 session_id)。"""
    db = get_session_factory()()
    try:
        scenario = Scenario(
            title="归属测试场景",
            scene_type="cafe",
            difficulty=1,
            system_prompt="You are Bella, a friendly barista.",
            opening_line="Hi there!",
            target_corpus="I'd like a coffee, please.|请给我来杯咖啡",
            interest_tags=[],
            status="published",
        )
        db.add(scenario)
        db.commit()
        sid = scenario.id
    finally:
        db.close()
    resp = client.post(
        "/api/v1/sessions", json={"kind": "dialog", "scenario_id": sid}, headers=auth_headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


def test_report_not_visible_to_other_user(client, auth_headers) -> None:
    """P0-3 失败用例:user1 的报告,user2 读取 → 404/40401(修复前 200 可拖走)。"""
    session_id = _create_dialog_session(client, auth_headers)
    resp = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    report_id = resp.json()["data"]["report_id"]

    resp = client.get(f"/api/v1/reports/{report_id}", headers=_OTHER_HEADERS)
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == 40401


def test_turn_rejects_other_user(client, auth_headers) -> None:
    """P0-3 失败用例:user2 向 user1 的会话提交回合(action=start)→ 404/40401(修复前可通过预检)。"""
    session_id = _create_dialog_session(client, auth_headers)
    resp = client.post(
        f"/api/v1/sessions/{session_id}/turns",
        data={"action": "start"},
        headers=_OTHER_HEADERS,
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == 40401


def test_complete_rejects_other_user(client, auth_headers) -> None:
    """P0-3 失败用例:user2 收尾 user1 的会话 → 404/40401(修复前 200 且不耗 LLM 摘要)。"""
    session_id = _create_dialog_session(client, auth_headers)
    resp = client.post(f"/api/v1/sessions/{session_id}/complete", headers=_OTHER_HEADERS)
    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == 40401


def test_complete_twice_returns_same_report(client, auth_headers) -> None:
    """P0-8 失败用例:重复 complete → 200 且同一 report_id(修复前第二次撞约束 500)。"""
    session_id = _create_dialog_session(client, auth_headers)
    first = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers)
    assert first.status_code == 200, first.text
    second = client.post(f"/api/v1/sessions/{session_id}/complete", headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()["data"]["report_id"] == first.json()["data"]["report_id"]
    # 快照语义:报告行不因二次 complete 重算而新增(仍 1 行)
    db = get_session_factory()()
    try:
        rows = list(db.execute(select(Report)).scalars())
        assert len(rows) == 1
    finally:
        db.close()
