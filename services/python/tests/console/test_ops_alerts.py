"""预警评估测试（docs/50 §6.3）。

锁定的四条规则语义：
1. **防抖**：``dedup_key = rule_code + 窗口起点`` → 同窗口同规则只出一条；
2. **冷却**：``cooldown_s`` 内即使进入新窗口也不重复出事件；
3. **样本门槛**：窗口内桶数 < ``min_samples`` 不判定（防冷启动误报）；
4. **恢复不自动 resolve**：指标恢复正常后事件仍是 ``firing``（人工处置留痕）。

另含自监控：评估失败计 ``ops_alert_eval_errors_total``（docs/50 §9.4）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.console.ops import alerts as alerts_mod
from app.db import get_session_factory
from app.models.console_telemetry import OpsAlertEvent, OpsAlertRule
from sqlalchemy import select


def _session():
    return get_session_factory()()


def _seed_rule(**overrides) -> int:
    spec = dict(alerts_mod.SEED_RULES[1])  # http_error_rate_high
    spec.update(overrides)
    db = _session()
    try:
        row = OpsAlertRule(**spec)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _seed_samples(metric: str, value: float, now: datetime, count: int = 3) -> None:
    from app.models.console_telemetry import OpsMetricSample

    db = _session()
    try:
        for i in range(count):
            db.add(
                OpsMetricSample(
                    service="python",
                    metric=metric,
                    labels_key="",
                    labels={},
                    bucket_start=now - timedelta(seconds=60 * (i + 1)),
                    bucket_s=60,
                    value_avg=value,
                    value_max=value,
                    value_min=value,
                    sample_count=10,
                )
            )
        db.commit()
    finally:
        db.close()


def _events() -> list[OpsAlertEvent]:
    db = _session()
    try:
        return list(db.execute(select(OpsAlertEvent)).scalars())
    finally:
        db.close()


def test_ensure_seed_rules_is_idempotent() -> None:
    db = _session()
    try:
        assert alerts_mod.ensure_seed_rules(db) == 6
        assert alerts_mod.ensure_seed_rules(db) == 0
        assert len(db.execute(select(OpsAlertRule)).scalars().all()) == 6
    finally:
        db.close()


def test_rule_fires_once_per_window_then_cools_down() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    other = _seed_rule()
    assert other  # 只评估这一条（seed 未播种）
    _seed_samples("http.request.error_rate", 0.5, now)

    db = _session()
    try:
        first = alerts_mod.evaluate(db, now=now)
        assert len(first) == 1
        assert first[0]["rule_code"] == "http_error_rate_high"
        # 同窗口再评估 → 不重复（dedup_key 唯一）
        assert alerts_mod.evaluate(db, now=now + timedelta(seconds=10)) == []
        # 新窗口但仍在 cooldown（900s）内 → 不重复
        assert alerts_mod.evaluate(db, now=now + timedelta(seconds=400)) == []
    finally:
        db.close()

    rows = _events()
    assert len(rows) == 1
    assert rows[0].dedup_key.startswith("http_error_rate_high:")
    assert rows[0].status == "firing"


def test_min_samples_blocks_cold_start() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    _seed_rule(min_samples=3)
    _seed_samples("http.request.error_rate", 0.9, now, count=2)  # 只有 2 桶
    db = _session()
    try:
        assert alerts_mod.evaluate(db, now=now) == []
    finally:
        db.close()
    assert _events() == []


def test_disabled_rule_not_evaluated() -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    _seed_rule(enabled=False)
    _seed_samples("http.request.error_rate", 0.9, now)
    db = _session()
    try:
        assert alerts_mod.evaluate(db, now=now) == []
    finally:
        db.close()


def test_recovery_does_not_auto_resolve() -> None:
    """指标恢复 → 事件仍是 firing（docs/50 §6.3：恢复是人工动作，闪断不刷屏）。"""
    now = datetime.now(UTC).replace(microsecond=0)
    _seed_rule(cooldown_s=0)
    _seed_samples("http.request.error_rate", 0.5, now)
    db = _session()
    try:
        assert len(alerts_mod.evaluate(db, now=now)) == 1
    finally:
        db.close()

    # 又过了一个窗口，样本已经健康（新窗口内没有越界样本）
    later = now + timedelta(seconds=600)
    db = _session()
    try:
        assert alerts_mod.evaluate(db, now=later) == []
    finally:
        db.close()

    rows = _events()
    assert len(rows) == 1
    assert rows[0].status == "firing", "恢复不得自动 resolve（人工处置才留痕）"
    assert rows[0].resolved_at is None


def test_eval_errors_counter_increments_on_failure(monkeypatch) -> None:
    """自监控：评估自身失败必须计数（否则"没响"会被误读成"很健康"）。"""
    alerts_mod.reset_eval_errors_for_tests()
    _seed_rule()
    now = datetime.now(UTC)

    monkeypatch.setattr(
        alerts_mod,
        "window_value",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    db = _session()
    try:
        assert alerts_mod.evaluate(db, now=now) == []
    finally:
        db.close()
    assert alerts_mod.eval_errors_total() == 1


def test_missing_histogram_does_not_fire_percentile_rule() -> None:
    """无直方图可算的分位规则 → 不出警（宁可沉默，也不报一个错的数）。"""
    now = datetime.now(UTC).replace(microsecond=0)
    db = _session()
    try:
        db.add(
            OpsAlertRule(
                code="llm_ttft_slow",
                name="LLM 首字延迟过高",
                service="python",
                metric="llm.ttft_ms.p95",
                comparator="gt",
                threshold=1.0,
                window_s=300,
                min_samples=1,
                severity="warn",
                cooldown_s=0,
            )
        )
        db.commit()
    finally:
        db.close()

    # 只写"每桶 p95"行、不写基础直方图行 → window_value 找不到真源 → 返回 None
    _seed_samples("llm.ttft_ms.p95", 9999.0, now)
    db = _session()
    try:
        assert alerts_mod.evaluate(db, now=now) == []
    finally:
        db.close()
    assert _events() == []
