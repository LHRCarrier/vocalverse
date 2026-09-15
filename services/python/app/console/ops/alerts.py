"""预警评估（docs/50 §6.3）。

规则（逐条来自 docs/50 §6.3）：

1. **防抖**：``dedup_key = rule_code + 窗口起点``（``floor(fired_at/window_s)``）——
   同规则同窗口只出一条事件；唯一键 ``uq_ops_alert_events_dedup_key`` 是最后防线；
2. **冷却**：``cooldown_s`` 内同规则不重复出事件（预警不是闹钟）；
3. **样本门槛**：窗口内桶数 < ``min_samples`` 不判定（防冷启动误报）；
4. **恢复不自动 resolve**：闪断会刷屏，且"谁处理的"必须留痕 → 恢复是人工动作；
5. **自监控**：评估自身失败计 ``ops_alert_eval_errors_total``（docs/50 §9.4），
   否则"预警没响"会被误读成"系统很健康"。

**不做硬删除**：``ops_alert_events.rule_id`` 是 ``ON DELETE RESTRICT``（迁移 0013），
历史事件必须活过规则 —— 停用走 ``enabled=false``（见控制台端点），删除直接 409。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console.ops.query import window_value

logger = logging.getLogger("vocalverse.console.ops.alerts")

#: 内置 6 条规则（docs/50 §6.3 表；阈值可改，code 不可改——``dedup_key`` 依赖它）
SEED_RULES: tuple[dict, ...] = (
    {
        "code": "http_p95_slow",
        "name": "HTTP 响应变慢",
        "service": "python",
        "metric": "http.request.duration_ms.p95",
        "comparator": "gt",
        "threshold": 3000.0,
        "window_s": 300,
        "min_samples": 3,
        "severity": "warn",
        "cooldown_s": 900,
        "description": "HTTP p95 > 3000ms（窗口内合并直方图重算）",
    },
    {
        "code": "http_error_rate_high",
        "name": "HTTP 错误率过高",
        "service": "python",
        "metric": "http.request.error_rate",
        "comparator": "gt",
        "threshold": 0.05,
        "window_s": 300,
        "min_samples": 3,
        "severity": "critical",
        "cooldown_s": 900,
        "description": "4xx+5xx 占比 > 5%",
    },
    {
        "code": "llm_error_rate_high",
        "name": "LLM 失败率过高",
        "service": "python",
        "metric": "llm.error_rate",
        "comparator": "gt",
        "threshold": 0.10,
        "window_s": 300,
        "min_samples": 3,
        "severity": "critical",
        "cooldown_s": 900,
        "description": "LLM 尝试失败占比 > 10%（超时/限流/解析失败）",
    },
    {
        "code": "llm_ttft_slow",
        "name": "LLM 首字延迟过高",
        "service": "python",
        "metric": "llm.ttft_ms.p95",
        "comparator": "gt",
        "threshold": 5000.0,
        "window_s": 300,
        "min_samples": 3,
        "severity": "warn",
        "cooldown_s": 900,
        "description": "首 token 延迟 p95 > 5s（流式体感先坏在这里）",
    },
    {
        "code": "db_pool_saturated",
        "name": "数据库连接池饱和",
        "service": "python",
        "metric": "db.pool.utilization",
        "comparator": "gt",
        "threshold": 0.85,
        "window_s": 300,
        "min_samples": 3,
        "severity": "critical",
        "cooldown_s": 600,
        "description": "池占用率 > 85%（含 overflow 容量）",
    },
    {
        "code": "asr_semaphore_saturated",
        "name": "ASR 排队过久",
        "service": "python",
        "metric": "asr.queue.wait_ms.p95",
        "comparator": "gt",
        "threshold": 10000.0,
        "window_s": 600,
        "min_samples": 3,
        "severity": "warn",
        "cooldown_s": 900,
        "description": "whisper 信号量等待 p95 > 10s",
    },
)

_COMPARATORS = {
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
}

_eval_errors = 0


def eval_errors_total() -> int:
    """``ops_alert_eval_errors_total``（自监控计数器，docs/50 §9.4）。"""
    return _eval_errors


def reset_eval_errors_for_tests() -> None:
    global _eval_errors
    _eval_errors = 0


def ensure_seed_rules(db: Session) -> int:
    """幂等播种内置规则（迁移只管 DDL，seed 归 Python 写方，docs/10 §7.1-2）。"""
    from app.models.console_telemetry import OpsAlertRule

    existing = set(db.execute(select(OpsAlertRule.code)).scalars())
    added = 0
    for spec in SEED_RULES:
        if spec["code"] in existing:
            continue
        db.add(OpsAlertRule(**spec))
        added += 1
    if added:
        db.commit()
    return added


def evaluate(
    db: Session,
    *,
    now: datetime | None = None,
    service: str = "python",
) -> list[dict]:
    """评估全部启用规则；返回本条 tick 新建的事件摘要（评估失败仅计数不抛出）。"""
    global _eval_errors
    from app.models.console_telemetry import OpsAlertRule

    moment = now or datetime.now(UTC)
    created: list[dict] = []
    try:
        rules = list(
            db.execute(select(OpsAlertRule).where(OpsAlertRule.enabled.is_(True))).scalars()
        )
    except Exception:  # noqa: BLE001 - 表缺失/库不可用：只计数
        _eval_errors += 1
        logger.warning("预警规则读取失败", exc_info=True)
        return created

    for rule in rules:
        try:
            event = _evaluate_rule(db, rule, moment, service)
            if event is not None:
                created.append(event)
        except Exception:  # noqa: BLE001
            _eval_errors += 1
            logger.warning("预警规则评估失败 code=%s", rule.code, exc_info=True)
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        _eval_errors += 1
        db.rollback()
        logger.warning("预警事件提交失败", exc_info=True)
    return created


def _evaluate_rule(db: Session, rule, moment: datetime, service: str) -> dict | None:
    from app.models.console_telemetry import OpsAlertEvent

    window_s = max(int(rule.window_s or 300), 1)
    window_start = _floor(moment, window_s)
    start = moment - timedelta(seconds=window_s)
    got = window_value(db, metric=rule.metric, start=start, end=moment, service=service)
    if got is None:
        return None  # 无样本 / 无直方图可算（分位指标缺基础直方图时宁可不出警）
    # min_samples 按**窗口内的 60s 桶数**判定（不是观测条数）：少于 N 桶就是冷启动，
    # 单个尖刺不足以定性（docs/50 §5.3.11「样本不足不判定，避免冷启动误报」）。
    if got.buckets < int(rule.min_samples or 1):
        return None
    compare = _COMPARATORS.get(rule.comparator)
    if compare is None or not compare(float(got.value), float(rule.threshold)):
        return None

    dedup_key = f"{rule.code}:{int(window_start.timestamp())}"[:160]
    exists = db.execute(
        select(OpsAlertEvent.id).where(OpsAlertEvent.dedup_key == dedup_key)
    ).first()
    if exists is not None:
        return None  # 同窗口同规则只出一条
    cooldown_s = int(rule.cooldown_s or 0)
    if cooldown_s > 0:
        recent = db.execute(
            select(OpsAlertEvent.id)
            .where(
                OpsAlertEvent.rule_code == rule.code,
                OpsAlertEvent.fired_at >= moment - timedelta(seconds=cooldown_s),
            )
            .limit(1)
        ).first()
        if recent is not None:
            return None

    message = f"{rule.name}: {rule.metric}={got.value:.2f} {rule.comparator} {rule.threshold}"
    row = OpsAlertEvent(
        rule_id=rule.id,
        rule_code=rule.code,
        severity=rule.severity,
        status="firing",
        value=float(got.value),
        threshold=float(rule.threshold),
        window_s=window_s,
        message=message[:255],
        detail={
            "metric": rule.metric,
            "basis": got.basis,
            "samples": got.samples,
            "window_start": window_start.isoformat(),
        },
        dedup_key=dedup_key,
        fired_at=moment,
    )
    db.add(row)
    db.flush()
    logger.info("预警触发 code=%s value=%.2f threshold=%s", rule.code, got.value, rule.threshold)
    return {
        "id": row.id,
        "rule_code": rule.code,
        "severity": rule.severity,
        "value": float(got.value),
        "threshold": float(rule.threshold),
        "dedup_key": dedup_key,
    }


def _floor(moment: datetime, window_s: int) -> datetime:
    epoch = int(moment.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % window_s), UTC)


__all__ = [
    "SEED_RULES",
    "ensure_seed_rules",
    "eval_errors_total",
    "evaluate",
    "reset_eval_errors_for_tests",
]
