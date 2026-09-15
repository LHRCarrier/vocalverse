"""预警端点契约测试（评审两项：ack 请求体 / notify_channels 形状）。

1. ``POST /alerts/events/{id}/ack`` **刻意无请求体** —— 旧控制台带 ``{note}`` 时必须
   **显式报错**而不是静默丢备注（"以为存了其实丢了"是本仓反复踩的坑）；
2. ``ops_alert_rules.notify_channels`` 形状裁定为 **字符串数组**（白名单 inbox|webhook），
   写侧校验 + 读侧兜底，两端都不再出现 dict。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db import get_session_factory
from app.models.console_telemetry import OpsAlertEvent, OpsAlertRule
from sqlalchemy import select

from .helpers import console_headers

RULE_PERMS = ("ops:alert:read", "ops:alert:write")
ACK_PERMS = ("ops:alert:write",)


def _seed_event(status: str = "firing") -> int:
    db = get_session_factory()()
    try:
        rule = OpsAlertRule(
            code="t_rule",
            name="t",
            service="python",
            metric="http.request.error_rate",
            comparator="gt",
            threshold=0.05,
            window_s=300,
            min_samples=1,
            severity="warn",
            cooldown_s=0,
        )
        db.add(rule)
        db.flush()
        row = OpsAlertEvent(
            rule_id=rule.id,
            rule_code=rule.code,
            severity="warn",
            status=status,
            value=0.9,
            threshold=0.05,
            window_s=300,
            message="m",
            dedup_key=f"t_rule:{int(datetime.now(UTC).timestamp())}",
            fired_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _event(event_id: int) -> OpsAlertEvent:
    db = get_session_factory()()
    try:
        return db.execute(select(OpsAlertEvent).where(OpsAlertEvent.id == event_id)).scalar_one()
    finally:
        db.close()


def test_ack_without_body_succeeds(client) -> None:
    """无请求体（控制台现状）→ 正常认领。"""
    event_id = _seed_event()
    resp = client.post(
        f"/api/v1/console/ops/alerts/events/{event_id}/ack",
        headers=console_headers(perms=ACK_PERMS),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["status"] == "acknowledged"
    assert data["acked_by"] == "ops-admin"
    assert data["resolved_at"] is None


def test_ack_with_empty_object_succeeds(client) -> None:
    """``{}`` 也放行（幂等调用不该因为多一个空对象就 422）。"""
    event_id = _seed_event()
    resp = client.post(
        f"/api/v1/console/ops/alerts/events/{event_id}/ack",
        json={},
        headers=console_headers(perms=ACK_PERMS),
    )
    assert resp.status_code == 200


def test_ack_with_note_is_rejected_not_silently_ignored(client) -> None:
    """旧控制台带 ``{note}`` → 明确 46007 指路 resolve，**不静默丢备注**。"""
    event_id = _seed_event()
    resp = client.post(
        f"/api/v1/console/ops/alerts/events/{event_id}/ack",
        json={"note": "我看到了，正在查"},
        headers=console_headers(perms=ACK_PERMS),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 46007
    assert body["data"]["unexpected_keys"] == ["note"]
    assert body["data"]["use"] == "resolve"
    # 事件状态未被改动（拒绝发生在任何写之前）
    assert _event(event_id).status == "firing"


def test_resolve_accepts_and_persists_note(client) -> None:
    """处置备注归 resolve：``{note}`` 真的落库（与 ack 的分工是刻意的）。"""
    event_id = _seed_event()
    resp = client.post(
        f"/api/v1/console/ops/alerts/events/{event_id}/resolve",
        json={"note": "已扩容连接池"},
        headers=console_headers(perms=ACK_PERMS),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["status"] == "resolved"
    assert data["resolved_note"] == "已扩容连接池"
    assert data["resolved_at"] is not None


def _create_rule(client, **overrides) -> object:
    payload = {
        "code": "nc_rule",
        "name": "形状测试",
        "metric": "http.request.error_rate",
        "comparator": "gt",
        "threshold": 0.05,
        "severity": "warn",
    }
    payload.update(overrides)
    return client.post(
        "/api/v1/console/ops/alerts/rules", json=payload, headers=console_headers(perms=RULE_PERMS)
    )


def test_notify_channels_accepts_string_array(client) -> None:
    resp = _create_rule(client, notify_channels=["inbox", "webhook"])
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["notify_channels"] == ["inbox", "webhook"]


def test_notify_channels_rejects_dict(client) -> None:
    """dict 形状 → 46007（否则会存进去、到控制台渲染时才炸）。"""
    resp = _create_rule(client, notify_channels={"inbox": True})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 46007
    assert body["data"]["shape"] == "string[]"
    # 没有落库（拒绝发生在写之前）
    db = get_session_factory()()
    try:
        assert (
            db.execute(select(OpsAlertRule).where(OpsAlertRule.code == "nc_rule")).first() is None
        )
    finally:
        db.close()


def test_notify_channels_rejects_unknown_channel_and_dedups(client) -> None:
    bad = _create_rule(client, notify_channels=["email"])
    assert bad.status_code == 422
    assert bad.json()["data"]["allowed"] == ["inbox", "webhook"]

    ok = _create_rule(client, notify_channels=["inbox", "inbox"])
    assert ok.status_code == 200
    assert ok.json()["data"]["notify_channels"] == ["inbox"]


def test_notify_channels_read_path_coerces_legacy_dirty_row(client) -> None:
    """历史脏行（曾被写成 dict）读出来退化为 ``[]``，不再把错误形状传给前端。"""
    db = get_session_factory()()
    try:
        db.add(
            OpsAlertRule(
                code="legacy_dirty",
                name="脏行",
                service="python",
                metric="http.request.error_rate",
                comparator="gt",
                threshold=0.05,
                window_s=300,
                min_samples=1,
                severity="warn",
                cooldown_s=0,
                notify_channels={"inbox": True},
            )
        )
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/v1/console/ops/alerts/rules", headers=console_headers(perms=RULE_PERMS))
    assert resp.status_code == 200
    items = {r["code"]: r for r in resp.json()["data"]["items"]}
    assert items["legacy_dirty"]["notify_channels"] == []
    assert all(isinstance(r["notify_channels"], list) for r in items.values())


def test_notify_channels_partial_patch_also_validated(client) -> None:
    """PATCH 也必须校验（不能只在 POST 上把关）。"""
    created = _create_rule(client, notify_channels=["inbox"])
    rule_id = created.json()["data"]["id"]
    resp = client.patch(
        f"/api/v1/console/ops/alerts/rules/{rule_id}",
        json={"notify_channels": "inbox"},
        headers=console_headers(perms=RULE_PERMS),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 46007
