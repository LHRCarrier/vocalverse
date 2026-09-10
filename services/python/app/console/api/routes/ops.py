"""控制台 · 运维端点（docs/50 §10.3 Python 段：``/api/v1/console/ops/**``）。

约定（docs/50 §10.1）：
- Envelope ``{code,message,data}``；分页 ``PageView``（``page`` 从 1 起，``page_size<=100``）；
- 时间参数一律 ISO-8601 with offset；请求/响应字段 snake_case；
- **功能位**：``APP_OPS_TELEMETRY_ENABLED=false`` 时本文件全部端点 46014；
  trace 端点额外受 ``APP_LLM_TRACE_ENABLED`` 约束；
- **权限码**逐端点绑定（§10.3 表）。
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Body, Depends, Path, Query
from sqlalchemy import delete, func, select

from app.console.api.deps import ConsoleAdmin, ConsoleBizError, console_guard
from app.console.ops import alerts as alerts_mod
from app.console.ops.catalog import catalog_list, spec_of
from app.console.ops.probe import probe_dependencies
from app.console.ops.query import (
    MAX_METRICS_PER_REQUEST,
    MAX_POINTS,
    MAX_ROWS_FETCH,
    percentile_q,
    series_points,
    suggested_step,
)
from app.core.config import get_settings
from app.core.response import Envelope, ok
from app.db import get_session_factory

router = APIRouter(prefix="/api/v1/console/ops", tags=["console-ops"])


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_ts(raw: str | None, default: datetime) -> datetime:
    if not raw:
        return default
    try:
        text = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ConsoleBizError(422, 46007, f"invalid timestamp: {raw}") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def _db_call(fn):
    """短事务：会话创建/关闭在事件循环，SQL 在 worker 线程（docs/19 P0-2 口径）。"""

    def _run():
        db = get_session_factory()()
        try:
            return fn(db)
        finally:
            db.close()

    return await asyncio.to_thread(_run)


# ---------------------------------------------------------------------------
# 总览 / 依赖 / 并发额度
# ---------------------------------------------------------------------------
@router.get("/overview", response_model=Envelope[dict])
async def overview(
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:overview:read")),
) -> Envelope:
    """版本 / uptime / 依赖 / 并发额度 / 采集自监控（docs/50 §10.3 第一行）。"""
    del admin
    import time

    from app import __version__
    from app.console.ops.collector import _PROCESS_START
    from app.console.ops.metrics import get_registry
    from app.console.trace.sink import get_sink

    probe = await probe_dependencies()
    settings = get_settings()
    sink_stats = get_sink().stats()
    return ok(
        {
            "version": __version__,
            "app_env": settings.app_env,
            "uptime_s": int(time.monotonic() - _PROCESS_START),
            "dependencies": probe,
            "concurrency": await _concurrency_view(),
            "collector": {
                "enabled": settings.ops_telemetry_enabled,
                "interval_s": settings.ops_telemetry_interval_s,
                "inflight_gauges": get_registry().gauges(),
            },
            "self_monitoring": {
                "trace_dropped_total": sink_stats["dropped"],
                "trace_written_total": sink_stats["written"],
                "trace_buffered": sink_stats["buffered"],
                "trace_write_errors_total": sink_stats["write_errors"],
                "metric_collector_errors_total": _collector_errors(),
                "ops_alert_eval_errors_total": alerts_mod.eval_errors_total(),
            },
            "flags": {
                "llm_trace_enabled": settings.llm_trace_enabled,
                "llm_trace_content_capture": settings.llm_trace_content_capture,
            },
        }
    )


@router.get("/services", response_model=Envelope[dict])
async def services(
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:overview:read")),
) -> Envelope:
    """依赖明细 —— 与 ``/readyz`` **同一函数**（docs/50 §9.4，口径必然一致）。"""
    del admin
    return ok(await probe_dependencies())


@router.get("/concurrency", response_model=Envelope[dict])
async def concurrency(
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:metric:read")),
) -> Envelope:
    del admin
    return ok(await _concurrency_view())


async def _concurrency_view() -> dict[str, Any]:
    """信号量额度与在途（额度是常量，在途取进程内 gauge）。"""
    from app.audio.asr import _ASR_CONCURRENCY
    from app.audio.ise import _ISE_CONCURRENCY
    from app.console.ops.metrics import get_registry
    from app.reading.orchestrator import MAX_CONCURRENCY as READING_TTS_CONCURRENCY

    gauges = get_registry().gauges()
    inflight = sum(v for k, v in gauges.items() if k.startswith("http.inflight|"))
    return {
        "http.inflight": int(inflight),
        "asr.limit": int(_ASR_CONCURRENCY),
        "ise.limit": int(_ISE_CONCURRENCY),
        "reading_tts.limit": int(READING_TTS_CONCURRENCY),
        "db.pool.capacity": _db_pool_capacity(),
        "note": "额度为进程内常量；在途为进程内 gauge（多副本时按副本独立）",
    }


def _db_pool_capacity() -> int | None:
    try:
        from app.console.ops.collector import _pool_capacity
        from app.db import get_engine

        return _pool_capacity(get_engine().pool)
    except Exception:  # noqa: BLE001
        return None


def _collector_errors() -> int:
    from app.console.ops.runtime import get_collector

    collector = get_collector()
    return collector.errors_total if collector is not None else 0


# ---------------------------------------------------------------------------
# 指标
# ---------------------------------------------------------------------------
@router.get("/metrics/catalog", response_model=Envelope[list])
async def metrics_catalog(
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:metric:read")),
) -> Envelope:
    """可用指标目录（名称/单位/**口径**）—— 分位指标必须如实标注其定义来源。"""
    del admin
    return ok(catalog_list())


@router.get("/metrics", response_model=Envelope[dict])
async def metrics(
    metric: list[str] = Query(default_factory=list),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    step: int = Query(default=60, ge=1, le=86400),
    labels_key: str | None = Query(default=None),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:metric:read")),
) -> Envelope:
    """时间窗 + step 聚合查询（docs/50 §8.5）。

    两道闸门：**点数** ``(to-from)/step ≤ 5000``（超限 46007 + ``data.suggestedStep``）、
    **成本** 单请求最多 ``MAX_METRICS_PER_REQUEST`` 个指标且总扫描行数 ≤ ``MAX_ROWS_FETCH``。
    """
    del admin
    if not metric:
        raise ConsoleBizError(422, 46007, "metric 必填（可重复）")
    if len(metric) > MAX_METRICS_PER_REQUEST:
        raise ConsoleBizError(
            422,
            46007,
            f"metric 数量超限（≤{MAX_METRICS_PER_REQUEST}）：控制台看板与业务共池，"
            "一次扫描多个指标会挤压学习者热路径",
            {"maxMetrics": MAX_METRICS_PER_REQUEST, "requested": len(metric)},
        )
    unknown = [m for m in metric if spec_of(m) is None]
    if unknown:
        raise ConsoleBizError(422, 46007, f"未知指标: {unknown}")

    now = _now()
    start = _parse_ts(from_, now - timedelta(hours=1))
    end = _parse_ts(to, now)
    if end <= start:
        raise ConsoleBizError(422, 46007, "to 必须晚于 from")
    span_s = (end - start).total_seconds()
    if span_s / step > MAX_POINTS:
        raise ConsoleBizError(
            422,
            46007,
            f"时间窗过大：({MAX_POINTS} 点上限)",
            {"suggestedStep": suggested_step(span_s, step), "maxPoints": MAX_POINTS},
        )

    def _run(db):
        return series_points(
            db,
            metrics=metric,
            start=start,
            end=end,
            step_s=step,
            labels_key=labels_key,
        )

    result = await _db_call(_run)
    if result["refusals"]:
        # 分位指标但没有直方图真源 → 拒绝（而不是回退成"p95 的平均"这种假数字）
        raise ConsoleBizError(
            422,
            46007,
            "分位指标缺少直方图样本，拒绝返回（口径不可靠）",
            {"refusals": result["refusals"], "reason": "percentile_requires_histogram"},
        )
    if result["rows_read"] > MAX_ROWS_FETCH:
        raise ConsoleBizError(
            422,
            46007,
            "窗口内样本行数超出单请求预算，请增大 step 或缩小时间窗",
            {
                "suggestedStep": suggested_step(span_s, max(step * 2, 60)),
                "maxRows": MAX_ROWS_FETCH,
            },
        )
    return ok(
        {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "step": step,
            "series": result["series"],
            "rows_read": result["rows_read"],
            "catalog": {m: (spec_of(m).as_dict() if spec_of(m) else None) for m in metric},
        }
    )


# ---------------------------------------------------------------------------
# 预警规则 / 事件
# ---------------------------------------------------------------------------
@router.get("/alerts/rules", response_model=Envelope[dict])
async def list_rules(
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:read")),
) -> Envelope:
    del admin
    from app.models.console_telemetry import OpsAlertRule

    def _run(db):
        rows = list(db.execute(select(OpsAlertRule).order_by(OpsAlertRule.id)).scalars())
        return [_rule_view(r) for r in rows]

    return ok({"items": await _db_call(_run)})


@router.post("/alerts/rules", response_model=Envelope[dict])
async def create_rule(
    body: dict[str, Any] = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:write")),
) -> Envelope:
    del admin
    from app.models.console_telemetry import OpsAlertRule

    payload = _validate_rule(body, partial=False)

    def _run(db):
        exists = db.execute(
            select(OpsAlertRule.id).where(OpsAlertRule.code == payload["code"])
        ).first()
        if exists is not None:
            raise ConsoleBizError(409, 46005, f"规则 code 已存在: {payload['code']}")
        row = OpsAlertRule(**payload)
        db.add(row)
        db.commit()
        db.refresh(row)
        return _rule_view(row)

    return ok(await _db_call(_run))


@router.patch("/alerts/rules/{rule_id}", response_model=Envelope[dict])
async def patch_rule(
    rule_id: int = Path(...),
    body: dict[str, Any] = Body(...),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:write")),
) -> Envelope:
    """改阈值/窗口/冷却/严重级/启停（``enabled=false`` 即"停用"，替代删除）。"""
    del admin
    from app.models.console_telemetry import OpsAlertRule

    changes = _validate_rule(body, partial=True)

    def _run(db):
        row = db.get(OpsAlertRule, rule_id)
        if row is None:
            raise ConsoleBizError(404, 46009, "alert rule not found")
        for k, v in changes.items():
            setattr(row, k, v)
        db.commit()
        db.refresh(row)
        return _rule_view(row)

    return ok(await _db_call(_run))


@router.delete("/alerts/rules/{rule_id}", response_model=Envelope[dict])
async def delete_rule(
    rule_id: int = Path(...),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:write")),
) -> Envelope:
    """**不实现硬删除**（docs/50 §5.3.12 + 迁移 0013：FK 改 ``RESTRICT``，历史事件须活过规则）。

    返回 46010（"该状态下不允许的动作"）并指向停用姿势；控制台前端按此渲染"停用"按钮。
    """
    del rule_id, admin
    raise ConsoleBizError(
        409,
        46010,
        "预警规则不支持删除（历史事件必须保留）：请改用 PATCH enabled=false 停用",
        {"use": "PATCH", "field": "enabled"},
    )


@router.get("/alerts/events", response_model=Envelope[dict])
async def list_events(
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    rule_code: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:read")),
) -> Envelope:
    del admin
    from app.models.console_telemetry import OpsAlertEvent

    now = _now()
    start = _parse_ts(from_, now - timedelta(days=7))
    end = _parse_ts(to, now)

    def _run(db):
        conds = [
            OpsAlertEvent.fired_at >= start,
            OpsAlertEvent.fired_at <= end,
        ]
        if status:
            conds.append(OpsAlertEvent.status == status)
        if severity:
            conds.append(OpsAlertEvent.severity == severity)
        if rule_code:
            conds.append(OpsAlertEvent.rule_code == rule_code)
        total = db.execute(select(func.count()).select_from(OpsAlertEvent).where(*conds)).scalar()
        rows = list(
            db.execute(
                select(OpsAlertEvent)
                .where(*conds)
                .order_by(OpsAlertEvent.fired_at.desc(), OpsAlertEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return {
            "items": [_event_view(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    return ok(await _db_call(_run))


@router.post("/alerts/events/{event_id}/ack", response_model=Envelope[dict])
async def ack_event(
    event_id: int = Path(...),
    body: dict[str, Any] | None = Body(default=None),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:write")),
) -> Envelope:
    """认领（firing → acknowledged）；``acked_by`` 存管理员**用户名快照**（跨服务不加 FK）。

    **无请求体是刻意的**，不是漏写：``ops_alert_events`` 只有 ``resolved_note`` 一列备注
    （确认语义是"我看到了"，处置说明属于 resolve，docs/50 §5.3.12）。
    旧控制台会随手带 ``{note}`` —— 若静默忽略，调用方会以为备注存下了而实际丢了
    （"无痕写成功"正是本仓库反复踩的类型），故此处**显式拒绝非空请求体**并指路 resolve。
    空体/``{}`` 一律放行（幂等调用不应因为多一个空对象就 422）。
    """
    if body:
        raise ConsoleBizError(
            422,
            46007,
            "ack 不接受请求体（认领无语义载荷）；处置备注请用 POST .../resolve 的 {note}",
            {"unexpected_keys": sorted(str(k) for k in body), "use": "resolve"},
        )
    return ok(await _transition_event(event_id, "acknowledged", admin, None))


@router.post("/alerts/events/{event_id}/resolve", response_model=Envelope[dict])
async def resolve_event(
    event_id: int = Path(...),
    body: dict[str, Any] = Body(default_factory=dict),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:alert:write")),
) -> Envelope:
    """处置完成（→ resolved）。**恢复不自动**：只有人点这一下才会 resolve（docs/50 §6.3）。"""
    note = (body or {}).get("note")
    return ok(await _transition_event(event_id, "resolved", admin, note))


async def _transition_event(event_id: int, target: str, admin: ConsoleAdmin, note: str | None):
    from app.models.console_telemetry import OpsAlertEvent

    def _run(db):
        row = db.get(OpsAlertEvent, event_id)
        if row is None:
            raise ConsoleBizError(404, 46009, "alert event not found")
        if row.status == "resolved":
            raise ConsoleBizError(409, 46010, "事件已 resolved（终态）")
        if target == "acknowledged" and row.status == "acknowledged":
            return _event_view(row)
        now = _now()
        row.status = target
        row.acked_at = row.acked_at or now
        row.acked_by = admin.username or f"admin#{admin.admin_id}"
        if target == "resolved":
            row.resolved_at = now
            row.resolved_note = (note or "")[:255] or None
        db.commit()
        db.refresh(row)
        return _event_view(row)

    return await _db_call(_run)


def _rule_view(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "service": row.service,
        "metric": row.metric,
        "comparator": row.comparator,
        "threshold": row.threshold,
        "window_s": row.window_s,
        "min_samples": row.min_samples,
        "severity": row.severity,
        "enabled": row.enabled,
        "cooldown_s": row.cooldown_s,
        "notify_channels": _notify_channels_view(row.notify_channels),
        "description": row.description,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _event_view(row) -> dict[str, Any]:
    return {
        "id": row.id,
        "rule_id": row.rule_id,
        "rule_code": row.rule_code,
        "severity": row.severity,
        "status": row.status,
        "value": row.value,
        "threshold": row.threshold,
        "window_s": row.window_s,
        "message": row.message,
        "detail": row.detail,
        "dedup_key": row.dedup_key,
        "fired_at": row.fired_at.isoformat() if row.fired_at else None,
        "acked_at": row.acked_at.isoformat() if row.acked_at else None,
        "acked_by": row.acked_by,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolved_note": row.resolved_note,
    }


def _notify_channels_view(value: Any) -> list[str]:
    """``notify_channels`` 对外**恒为字符串数组**。

    **形状裁定**：``["inbox", "webhook"]``（数组），不是 dict ——
    ``ck`` 无关、``server_default`` 是 ``'[]'``、docs/50 §5.3.11 的预留值也是数组；
    旧实现直接回显列值，于是 dict 也能存进去并在读取端炸（控制台的 ``string[]`` 类型
    会被打破）。现在：写侧校验（见 ``_validate_rule``）、读侧兜底
    （历史脏行退化为 ``[]``，不把错误形状继续传给前端）。
    """
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, str)]


def _validate_rule(body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    """规则入参校验（枚举/范围/指标必须在目录内）。"""
    allowed = {
        "code",
        "name",
        "service",
        "metric",
        "comparator",
        "threshold",
        "window_s",
        "min_samples",
        "severity",
        "enabled",
        "cooldown_s",
        "notify_channels",
        "description",
    }
    out = {k: v for k, v in (body or {}).items() if k in allowed}
    if not partial:
        for required in ("code", "name", "metric", "comparator", "threshold", "severity"):
            if required not in out:
                raise ConsoleBizError(422, 46007, f"缺少必填字段: {required}")
    if "comparator" in out and out["comparator"] not in ("gt", "gte", "lt", "lte"):
        raise ConsoleBizError(422, 46007, "comparator 非法（gt|gte|lt|lte）")
    if "severity" in out and out["severity"] not in ("info", "warn", "critical"):
        raise ConsoleBizError(422, 46007, "severity 非法（info|warn|critical）")
    if "service" in out and out["service"] not in ("python", "java"):
        raise ConsoleBizError(422, 46007, "service 非法（python|java）")
    # 自定义指标名允许（Java 侧指标），但分位指标必须能在目录里找到真源
    if (
        "metric" in out
        and spec_of(out["metric"]) is None
        and percentile_q(str(out["metric"])) is not None
    ):
        raise ConsoleBizError(422, 46007, f"指标不在目录中，无法确定直方图真源: {out['metric']}")
    if "window_s" in out and int(out["window_s"]) < 60:
        raise ConsoleBizError(422, 46007, "window_s 不得小于 60（桶宽）")
    if "notify_channels" in out:
        out["notify_channels"] = _validate_notify_channels(out["notify_channels"])
    return out


#: 通知渠道白名单（与 docs/50 §5.3.11 预留值一致；本期只做控制台角标）
NOTIFY_CHANNELS = ("inbox", "webhook")


def _validate_notify_channels(value: Any) -> list[str]:
    """``notify_channels`` **只接受字符串数组**，元素必须在白名单内。

    不校验的话，客户端可以塞 ``{"a": 1}``：写入成功、读取端（控制台声明的 ``string[]``）
    在渲染时才炸 —— 错误在离现场最远的地方暴露，是排查成本最高的一类失败。
    """
    if not isinstance(value, list):
        raise ConsoleBizError(
            422,
            46007,
            "notify_channels 必须是字符串数组（如 ['inbox']），不接受对象",
            {"allowed": list(NOTIFY_CHANNELS), "shape": "string[]"},
        )
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in NOTIFY_CHANNELS:
            raise ConsoleBizError(
                422,
                46007,
                f"notify_channels 元素非法: {item!r}（允许 {'|'.join(NOTIFY_CHANNELS)}）",
                {"allowed": list(NOTIFY_CHANNELS)},
            )
        if item not in out:
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# trace
# ---------------------------------------------------------------------------
@router.get("/traces/stats", response_model=Envelope[dict])
async def trace_stats(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    admin: ConsoleAdmin = Depends(
        console_guard(telemetry=True, llm_trace=True, perm="ops:trace:read")
    ),
) -> Envelope:
    """调用量 / 错误率 / p95 / token + **随时间趋势** + 按模型/状态分解（趋势与调优数据源）。

    新增块（既有字段**一个没动**，控制台已按老形状消费）：

    - ``trend``：按 **UTC 日**分桶、覆盖整个窗口、**缺失日补 0**（图要连续才读得出趋势）；
      每日 ``duration_ms_p95`` 由该日 ``llm.duration_ms`` 直方图**合并后插值**得到，
      该日无直方图样本时为 ``null``（不写 0 —— 0 会被读成"当天飞快"，是假信号）；
    - ``by_model``：按主模型聚合，``trace_count`` 降序（同名次按 model 字典序，保证稳定）；
      ``model IS NULL`` 归入 ``"(unknown)"``；
    - ``by_status``：``ok|error|aborted|incomplete`` **四条恒在**（计数为 0 也返回），
      控制台的图例因此不会随数据抖动。

    **成本**：全部在**一次** ``asyncio.to_thread`` 里用一个会话跑 **4 条 SQL**
    （状态聚合 / 日×状态聚合 / 模型聚合 / 直方图行），不是一次往返 —— 是 4 次
    SQL 往返但只占 1 次线程与连接借还；相比改前的 4 条（count / count≠ok / sum / 直方图）
    **净增 0**。直方图行有硬预算 ``MAX_HISTOGRAM_ROWS``：超预算则整段 p95 置 ``null``
    并在 ``trend_meta.p95_available=false`` 说明，绝不拿部分直方图算一个错的 p95。
    """
    del admin
    import math

    from app.models.console_telemetry import LlmTrace

    now = _now()
    start = _parse_ts(from_, now - timedelta(days=1)).astimezone(UTC)
    end = _parse_ts(to, now).astimezone(UTC)
    if end <= start:
        raise ConsoleBizError(422, 46007, "to 必须晚于 from")

    span_s = (end - start).total_seconds()
    buckets = math.ceil(span_s / 86400)
    if buckets > MAX_TREND_BUCKETS:
        raise ConsoleBizError(
            422,
            46007,
            f"时间窗过大：trend 按天分桶，最多 {MAX_TREND_BUCKETS} 天（当前 {buckets} 天）",
            {
                "maxTrendBuckets": MAX_TREND_BUCKETS,
                "requestedBuckets": buckets,
                # 与指标查询同款的"给个建议值"口径（单位：秒）
                "suggestedStep": max(int(span_s // MAX_TREND_BUCKETS), 86400),
                "suggestedFrom": (end - timedelta(days=MAX_TREND_BUCKETS)).isoformat(),
            },
        )

    def _run(db):
        return _trace_stats(db, LlmTrace, start, end)

    return ok(await _db_call(_run))


#: trend 最大桶数（按天分桶，约半年）；超出直接 46007 + 建议窗口，不做静默降采样
MAX_TREND_BUCKETS = 180
#: 直方图行硬预算（跨桶分位数必须拿到完整直方图，拿不全就置 null，不猜）
MAX_HISTOGRAM_ROWS = 20000
#: 状态取值（与 ``ck_llm_traces_status`` 一致；by_status 恒返回这四条）
TRACE_STATUSES = ("ok", "error", "aborted", "incomplete")
#: model 为空时的归并桶（控制台按此字符串显示）
UNKNOWN_MODEL = "(unknown)"
#: 趋势 p95 的直方图真源（与指标目录 llm.duration_ms 一致）
_TREND_P95_METRIC = "llm.duration_ms"


def _trace_stats(db, trace_model, start: datetime, end: datetime) -> dict[str, Any]:
    """4 条 SQL 组装 stats：状态聚合 / 日×状态聚合 / 模型聚合 / 直方图行。"""
    from app.console.ops.metrics import histogram_percentile, merge_histograms
    from app.models.console_telemetry import OpsMetricSample

    conds = [trace_model.started_at >= start, trace_model.started_at <= end]

    # Q1：按状态聚合（同时给出既有 trace_count / error_count / token 总量，省掉 2 条独立 count）
    status_rows = db.execute(
        select(
            trace_model.status,
            func.count(),
            func.coalesce(func.sum(trace_model.llm_call_count), 0),
            func.coalesce(func.sum(trace_model.prompt_tokens), 0),
            func.coalesce(func.sum(trace_model.completion_tokens), 0),
        )
        .where(*conds)
        .group_by(trace_model.status)
    ).all()
    per_status = {str(r[0]): r for r in status_rows}
    total = sum(int(r[1]) for r in status_rows)
    errors = total - int(per_status.get("ok", (None, 0))[1])
    llm_calls = sum(int(r[2]) for r in status_rows)
    prompt_tokens = sum(int(r[3]) for r in status_rows)
    completion_tokens = sum(int(r[4]) for r in status_rows)

    # Q2：日 × 状态聚合 → trend 的计数列
    day_expr = func.date(trace_model.started_at)
    daily_rows = db.execute(
        select(
            day_expr,
            trace_model.status,
            func.count(),
            func.coalesce(func.sum(trace_model.llm_call_count), 0),
        )
        .where(*conds)
        .group_by(day_expr, trace_model.status)
    ).all()
    daily: dict[str, dict[str, Any]] = {}
    for day, status, count, calls in daily_rows:
        slot = daily.setdefault(
            _day_key(day),
            {"trace_count": 0, "error_count": 0, "llm_call_count": 0},
        )
        slot["trace_count"] += int(count)
        slot["llm_call_count"] += int(calls)
        if str(status) != "ok":
            slot["error_count"] += int(count)

    # Q3：按模型聚合
    model_rows = db.execute(
        select(
            trace_model.model,
            func.count(),
            func.coalesce(func.sum(trace_model.llm_call_count), 0),
            func.coalesce(func.sum(trace_model.prompt_tokens), 0),
            func.coalesce(func.sum(trace_model.completion_tokens), 0),
        )
        .where(*conds)
        .group_by(trace_model.model)
    ).all()
    by_model = sorted(
        (
            {
                "model": str(r[0]) if r[0] else UNKNOWN_MODEL,
                "trace_count": int(r[1]),
                "llm_call_count": int(r[2]),
                "prompt_tokens": int(r[3]),
                "completion_tokens": int(r[4]),
            }
            for r in model_rows
        ),
        key=lambda m: (-m["trace_count"], m["model"]),
    )

    # Q4：直方图行（窗口级 p95 与逐日 p95 共用同一批数据）
    hist_rows = db.execute(
        select(OpsMetricSample.bucket_start, OpsMetricSample.buckets)
        .where(
            OpsMetricSample.service == "python",
            OpsMetricSample.metric == _TREND_P95_METRIC,
            OpsMetricSample.bucket_start >= start,
            OpsMetricSample.bucket_start <= end,
        )
        .order_by(OpsMetricSample.bucket_start)
        .limit(MAX_HISTOGRAM_ROWS + 1)
    ).all()
    p95_available = len(hist_rows) <= MAX_HISTOGRAM_ROWS
    if not p95_available:
        hist_rows = []

    per_day_hist: dict[str, list] = {}
    for bucket_start, buckets_json in hist_rows:
        if buckets_json:
            per_day_hist.setdefault(_day_key(bucket_start), []).append(buckets_json)
    window_hist = merge_histograms([b for _, b in hist_rows if b])
    window_p95 = histogram_percentile(window_hist, 0.95) if window_hist else None

    trend = _dense_trend(start, end, daily, per_day_hist, histogram_percentile, merge_histograms)

    return {
        "from": start.isoformat(),
        "to": end.isoformat(),
        "trace_count": total,
        "error_count": errors,
        "error_rate": (errors / total) if total else 0.0,
        "llm_call_count": llm_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "duration_ms_p95": window_p95,
        "duration_ms_p95_basis": (
            f"histogram_merge({_TREND_P95_METRIC})" if window_p95 is not None else None
        ),
        "trend": trend,
        "trend_meta": {
            "bucket": "day",
            "timezone": "UTC",
            "buckets": len(trend),
            "p95_metric": _TREND_P95_METRIC,
            "p95_available": p95_available,
            "rows_budget": MAX_HISTOGRAM_ROWS,
            "note": (
                "duration_ms_p95 为该日直方图合并后插值；无样本日为 null（缺口即真相）"
                if p95_available
                else "直方图行数超出单请求预算，p95 全部置 null（不返回基于部分直方图的错值）"
            ),
        },
        "by_model": by_model,
        "by_status": [
            {"status": s, "count": int(per_status.get(s, (None, 0))[1])} for s in TRACE_STATUSES
        ],
    }


def _dense_trend(start, end, daily, per_day_hist, percentile_fn, merge_fn) -> list[dict[str, Any]]:
    """按 UTC 日**补零**成连续序列（缺日不跳过，否则折线会把断层画成斜坡）。"""
    out: list[dict[str, Any]] = []
    cursor = start.date()
    last = end.date()
    while cursor <= last:
        key = cursor.isoformat()
        slot = daily.get(key) or {"trace_count": 0, "error_count": 0, "llm_call_count": 0}
        hist = merge_fn(per_day_hist.get(key) or [])
        out.append(
            {
                "date": key,
                "trace_count": int(slot["trace_count"]),
                "error_count": int(slot["error_count"]),
                "llm_call_count": int(slot["llm_call_count"]),
                "duration_ms_p95": (percentile_fn(hist, 0.95) if hist else None),
            }
        )
        cursor += timedelta(days=1)
    return out


def _day_key(value) -> str:
    """SQL ``date()`` 的返回值归一为 ``YYYY-MM-DD``（PG 回 date、SQLite 回字符串）。"""
    return str(value)[:10]


@router.get("/traces", response_model=Envelope[dict])
async def list_traces(
    kind: str | None = Query(default=None),
    status: str | None = Query(default=None),
    model: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    min_duration_ms: int | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    admin: ConsoleAdmin = Depends(
        console_guard(telemetry=True, llm_trace=True, perm="ops:trace:read")
    ),
) -> Envelope:
    del admin
    from app.models.console_telemetry import LlmTrace

    now = _now()
    start = _parse_ts(from_, now - timedelta(days=1))
    end = _parse_ts(to, now)

    def _run(db):
        conds = [LlmTrace.started_at >= start, LlmTrace.started_at <= end]
        if kind:
            conds.append(LlmTrace.kind == kind)
        if status:
            conds.append(LlmTrace.status == status)
        if model:
            conds.append(LlmTrace.model == model)
        if session_id:
            conds.append(LlmTrace.session_id == session_id)
        if min_duration_ms is not None:
            conds.append(LlmTrace.duration_ms >= min_duration_ms)
        total = db.execute(select(func.count()).select_from(LlmTrace).where(*conds)).scalar()
        rows = list(
            db.execute(
                select(LlmTrace)
                .where(*conds)
                .order_by(LlmTrace.started_at.desc(), LlmTrace.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return {
            "items": [_trace_view(r) for r in rows],
            "total": int(total or 0),
            "page": page,
            "page_size": page_size,
        }

    return ok(await _db_call(_run))


@router.get("/traces/{trace_id}", response_model=Envelope[dict])
async def trace_detail(
    trace_id: str = Path(..., min_length=8, max_length=64),
    span_limit: int = Query(default=500, ge=1, le=500),
    admin: ConsoleAdmin = Depends(
        console_guard(telemetry=True, llm_trace=True, perm="ops:trace:read")
    ),
) -> Envelope:
    """trace + span 树（一次 ``(trace_id, seq)`` 取全树，内存组树；硬上限 500 span）。"""
    del admin
    from app.models.console_telemetry import LlmSpan, LlmTrace

    def _run(db):
        trace = db.execute(
            select(LlmTrace).where(LlmTrace.trace_id == trace_id)
        ).scalar_one_or_none()
        if trace is None:
            raise ConsoleBizError(404, 46012, "trace 不存在或已过保留期")
        spans = list(
            db.execute(
                select(LlmSpan)
                .where(LlmSpan.trace_id == trace_id)
                .order_by(LlmSpan.seq)
                .limit(span_limit + 1)
            ).scalars()
        )
        truncated = len(spans) > span_limit
        spans = spans[:span_limit]
        return {
            "trace": _trace_view(trace),
            "spans": [_span_view(s) for s in spans],
            "truncated": truncated,
            "span_limit": span_limit,
        }

    return ok(await _db_call(_run))


@router.get("/traces/{trace_id}/contents", response_model=Envelope[dict])
async def trace_contents(
    trace_id: str = Path(..., min_length=8, max_length=64),
    admin: ConsoleAdmin = Depends(
        console_guard(telemetry=True, llm_trace=True, perm="ops:trace:content:read")
    ),
) -> Envelope:
    """内容流（**独立权限码** ``ops:trace:content:read``）。

    未捕获时返回 ``data.captured=false``（而非空表 —— 让界面能区分"没采"与"采了但为空"）。
    **每次读取都审计**：``admin_audit_logs`` 是 Java 写方，Python 侧只能 best-effort ——
    本实现同时落 ``llm_traces.attrs.content_reads``（环形，最近 10 条）与一条带 admin id 的日志。
    """
    from app.console.api import audit
    from app.models.console_telemetry import LlmSpanContent, LlmTrace

    def _run(db):
        trace = db.execute(
            select(LlmTrace).where(LlmTrace.trace_id == trace_id)
        ).scalar_one_or_none()
        if trace is None:
            raise ConsoleBizError(404, 46012, "trace 不存在或已过保留期")
        rows = list(
            db.execute(
                select(LlmSpanContent)
                .where(LlmSpanContent.trace_id == trace_id)
                .order_by(LlmSpanContent.span_id, LlmSpanContent.direction, LlmSpanContent.seq)
                .limit(1000)
            ).scalars()
        )
        audit.record_content_read(db, trace, admin)
        db.commit()
        return {
            "captured": bool(trace.content_captured),
            "content_capture_enabled": get_settings().llm_trace_content_capture,
            "deny_reason": (trace.attrs or {}).get("content_capture_reason"),
            "items": [
                {
                    "span_id": r.span_id,
                    "direction": r.direction,
                    "seq": r.seq,
                    "role": r.role,
                    "content": r.content,
                    "content_chars": r.content_chars,
                    "truncated": r.truncated,
                    "redacted": r.redacted,
                }
                for r in rows
            ],
            "total": len(rows),
        }

    return ok(await _db_call(_run))


def _trace_view(row) -> dict[str, Any]:
    return {
        "trace_id": row.trace_id,
        "request_id": row.request_id,
        "kind": row.kind,
        "status": row.status,
        "session_id": row.session_id,
        "user_id": row.user_id,
        "model": row.model,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_ms": row.duration_ms,
        "ttft_ms": row.ttft_ms,
        "span_count": row.span_count,
        "llm_call_count": row.llm_call_count,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "total_tokens": row.total_tokens,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "content_captured": row.content_captured,
        "attrs": row.attrs,
    }


def _span_view(row) -> dict[str, Any]:
    return {
        "span_id": row.span_id,
        "parent_span_id": row.parent_span_id,
        "name": row.name,
        "span_kind": row.span_kind,
        "seq": row.seq,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "ended_at": row.ended_at.isoformat() if row.ended_at else None,
        "duration_ms": row.duration_ms,
        "ttft_ms": row.ttft_ms,
        "status": row.status,
        "retry_index": row.retry_index,
        "model": row.model,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "finish_reason": row.finish_reason,
        "tool_name": row.tool_name,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "attrs": row.attrs,
    }


# ---------------------------------------------------------------------------
# 维护：保留期清理
# ---------------------------------------------------------------------------
@router.post("/maintenance/purge", response_model=Envelope[dict])
async def purge(
    body: dict[str, Any] = Body(default_factory=dict),
    admin: ConsoleAdmin = Depends(console_guard(telemetry=True, perm="ops:maintenance:write")),
) -> Envelope:
    """清理过期数据（docs/50 §9.3：trace 30 天 / 内容 72h / 指标 7 天）。"""
    del admin
    settings = get_settings()
    now = _now()
    targets = (body or {}).get("targets") or ["traces", "contents", "metrics"]
    dry_run = bool((body or {}).get("dry_run"))
    trace_cut = now - timedelta(days=settings.llm_trace_retention_days)
    content_cut = now - timedelta(hours=settings.llm_span_content_retention_hours)
    metric_cut = now - timedelta(days=settings.ops_metric_retention_days)

    from app.models.console_telemetry import LlmSpan, LlmSpanContent, LlmTrace, OpsMetricSample

    def _run(db):
        result: dict[str, Any] = {}
        if "contents" in targets:
            result["contents"] = _purge_count(
                db, LlmSpanContent, LlmSpanContent.created_at < content_cut, dry_run
            )
        if "traces" in targets:
            result["spans"] = _purge_count(db, LlmSpan, LlmSpan.started_at < trace_cut, dry_run)
            result["traces"] = _purge_count(db, LlmTrace, LlmTrace.started_at < trace_cut, dry_run)
        if "metrics" in targets:
            result["metrics"] = _purge_count(
                db, OpsMetricSample, OpsMetricSample.bucket_start < metric_cut, dry_run
            )
        if not dry_run:
            db.commit()
        else:
            db.rollback()
        return {
            "dry_run": dry_run,
            "deleted": result,
            "policy": {
                "llm_trace_retention_days": settings.llm_trace_retention_days,
                "llm_span_content_retention_hours": settings.llm_span_content_retention_hours,
                "ops_metric_retention_days": settings.ops_metric_retention_days,
            },
        }

    return ok(await _db_call(_run))


def _purge_count(db, model, cond, dry_run: bool) -> int:
    if dry_run:
        return int(db.execute(select(func.count()).select_from(model).where(cond)).scalar() or 0)
    return int(db.execute(delete(model).where(cond)).rowcount or 0)
