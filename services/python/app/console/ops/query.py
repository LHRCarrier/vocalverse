"""指标窗口聚合与查询（docs/50 §8.4/§8.5）。

**跨桶分位数的唯一合法口径**（P0-3）：不能对每桶已算好的 ``p95`` 再取平均或取 p95。
正确做法是取**基础分布指标**（如 ``http.request.duration_ms``）落在窗口内的所有直方图，
**先合并再插值**。因此：

- ``.pNN`` 指标一律通过 ``spec.percentile_of`` 找到基础直方图指标重算；
- 基础直方图行在窗口内**不存在**时，接口**拒绝**（46007 + ``reason``），
  绝不回退成"p95 的平均"这种看起来像 p95、实则不是的数字。

**成本闸门**（P0-3 附加要求）：控制台看板 15s 轮询，与学习者热路径共用 ``pool_size=20``，
所以除点数上限外还限制单请求行预算 ``MAX_ROWS_FETCH``（一次最多扫 20000 行样本）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.console.ops.catalog import (
    SHAPE_AVG,
    SHAPE_DISTRIBUTION,
    SHAPE_GAUGE,
    SHAPE_SUM,
    spec_of,
)
from app.console.ops.metrics import histogram_percentile, merge_histograms

#: 单请求 metric 参数个数上限（每多一个 metric = 多一轮窗口扫描）
MAX_METRICS_PER_REQUEST = 8
#: 时间窗点数上限（docs/50 §8.5：超出 → 46007 + data.suggestedStep）
MAX_POINTS = 5000
#: 单请求最多扫描的样本行数（成本闸门：与业务共池，不能无界扫）
MAX_ROWS_FETCH = 20000


@dataclass
class WindowValue:
    """窗口聚合结果（``basis`` 记录口径，接口原样返回给前端副标题）。

    ``samples`` = 窗口内**观测数**（各桶 ``sample_count`` 之和，用于展示）；
    ``buckets`` = 窗口内**样本桶数**（行数）—— 预警的 ``min_samples`` 按它判定：
    "窗口内至少要有 N 个 60s 桶的数据"才判越界，防冷启动/单点抖动误报。
    """

    value: float
    basis: str
    samples: int
    buckets: int = 0


def percentile_q(metric: str) -> float | None:
    """``x.p95`` → 0.95；非分位指标返回 None。"""
    if "." not in metric:
        return None
    tail = metric.rsplit(".", 1)[-1]
    if len(tail) == 3 and tail[0] == "p" and tail[1:].isdigit():
        q = int(tail[1:]) / 100
        return q if 0 < q < 1 else None
    return None


def as_utc(dt: datetime) -> datetime:
    """SQLite 会把 ``timestamptz`` 读回**naive**（PG 不会）—— 跨方言比较前统一补 UTC。"""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _fetch(
    session: Session,
    *,
    metrics: list[str],
    start: datetime,
    end: datetime,
    service: str,
    labels_key: str | None = None,
    limit: int = MAX_ROWS_FETCH,
):
    from app.models.console_telemetry import OpsMetricSample

    stmt = (
        select(
            OpsMetricSample.metric,
            OpsMetricSample.labels_key,
            OpsMetricSample.labels,
            OpsMetricSample.bucket_start,
            OpsMetricSample.value_avg,
            OpsMetricSample.value_max,
            OpsMetricSample.value_min,
            OpsMetricSample.sample_count,
            OpsMetricSample.buckets,
        )
        .where(
            OpsMetricSample.service == service,
            OpsMetricSample.metric.in_(metrics),
            OpsMetricSample.bucket_start >= start,
            OpsMetricSample.bucket_start < end,
        )
        .order_by(OpsMetricSample.bucket_start)
        .limit(limit + 1)
    )
    if labels_key:
        stmt = stmt.where(OpsMetricSample.labels_key == labels_key)
    return session.execute(stmt).all()


def fetch_buckets_json(session: Session, *, metric: str, start, end, service: str = "python"):
    """取窗口内某基础分布指标的 ``buckets`` 列表（供合并重算分位数）。"""
    from app.models.console_telemetry import OpsMetricSample

    if not hasattr(OpsMetricSample, "buckets"):
        return []
    rows = session.execute(
        select(OpsMetricSample.buckets).where(
            OpsMetricSample.service == service,
            OpsMetricSample.metric == metric,
            OpsMetricSample.bucket_start >= start,
            OpsMetricSample.bucket_start < end,
        )
    ).all()
    return [r[0] for r in rows if r[0]]


def window_value(
    session: Session,
    *,
    metric: str,
    start: datetime,
    end: datetime,
    service: str = "python",
) -> WindowValue | None:
    """窗口聚合；无法给出**可信**数字时返回 None（由调用方拒绝或跳过，不猜）。"""
    spec = spec_of(metric)
    q = percentile_q(metric)

    if spec is not None and spec.percentile_of:
        hist_rows = fetch_buckets_json(
            session, metric=spec.percentile_of, start=start, end=end, service=service
        )
        hist = merge_histograms(hist_rows)
        if not hist:
            return None
        assert q is not None
        value = histogram_percentile(hist, q)
        if value is None:
            return None
        total = int(hist[-1][1])
        return WindowValue(
            value=float(value),
            basis=f"histogram_merge({spec.percentile_of})",
            samples=total,
            buckets=len(hist_rows),
        )

    rows = _fetch(session, metrics=[metric], start=start, end=end, service=service)
    if not rows:
        return None
    shape = spec.shape if spec else SHAPE_GAUGE
    samples = sum(int(r.sample_count or 0) for r in rows)
    nbuckets = len(rows)
    if shape == SHAPE_DISTRIBUTION:
        hist = merge_histograms([r.buckets for r in rows if r.buckets])
        if not hist:
            return None
        mean = (
            sum(float(r.value_avg) * int(r.sample_count or 0) for r in rows) / samples
            if samples
            else 0.0
        )
        return WindowValue(
            value=mean, basis="histogram_merge(mean)", samples=samples, buckets=nbuckets
        )
    if shape == SHAPE_SUM:
        return WindowValue(
            value=sum(float(r.value_avg) for r in rows),
            basis="sum(avg)",
            samples=samples,
            buckets=nbuckets,
        )
    if shape == SHAPE_AVG:
        weighted = sum(float(r.value_avg) * max(int(r.sample_count or 0), 1) for r in rows)
        denom = sum(max(int(r.sample_count or 0), 1) for r in rows)
        return WindowValue(
            value=weighted / denom if denom else 0.0,
            basis="avg_of_avgs",
            samples=samples,
            buckets=nbuckets,
        )
    # gauge：窗口内峰值（水位型告警要的是峰值，不是均值）
    return WindowValue(
        value=max(float(r.value_max) for r in rows),
        basis="max(value_max)",
        samples=samples,
        buckets=nbuckets,
    )


def suggested_step(span_s: float, step_s: int) -> int:
    """超限时给前端的建议 step（秒）：向上取整到桶宽的整数倍。"""
    needed = math.ceil(span_s / MAX_POINTS)
    base = max(int(step_s or 60), 1)
    if needed <= base:
        return base
    return int(math.ceil(needed / 60.0) * 60)


def series_points(
    session: Session,
    *,
    metrics: list[str],
    start: datetime,
    end: datetime,
    step_s: int,
    labels_key: str | None = None,
    service: str = "python",
) -> dict[str, Any]:
    """按 step 二次聚合（服务端 ``date_trunc`` 等价物：按秒取整分组，docs/50 §8.1）。

    返回 ``{series, rows_read, refusals}``；分位指标走直方图合并。
    ``refusals`` 非空表示"请求了分位数但窗口内没有直方图"——**拒绝而不是给个错数**
    （P0-3：绝不能回退成"p95 的平均"，那是个看起来像 p95 却谁也不是的数字）。
    """
    out: dict[str, list[dict[str, Any]]] = {m: [] for m in metrics}
    refusals: list[dict[str, Any]] = []
    fetched = 0
    for metric in metrics:
        spec = spec_of(metric)
        if spec is not None and spec.percentile_of:
            # 分位：逐 step 窗口合并直方图（每点一个 SELECT，点数已由 MAX_POINTS 约束）
            base = spec.percentile_of
            q = percentile_q(metric)
            cursor = start
            saw_histogram = False
            while cursor < end and q is not None:
                nxt = min(cursor + timedelta(seconds=step_s), end)
                hist = merge_histograms(
                    fetch_buckets_json(session, metric=base, start=cursor, end=nxt, service=service)
                )
                if hist:
                    saw_histogram = True
                value = histogram_percentile(hist, q) if hist else None
                out[metric].append(
                    {
                        "t": cursor.isoformat(),
                        "value": value,
                        "samples": int(hist[-1][1]) if hist else 0,
                        "basis": f"histogram_merge({base})",
                    }
                )
                cursor = nxt
            if not saw_histogram:
                refusals.append(
                    {
                        "metric": metric,
                        "reason": "percentile_requires_histogram",
                        "histogram_metric": base,
                        "message": (
                            f"{metric} 是分位指标，其真源是 {base} 的直方图；"
                            "该窗口内没有直方图样本，拒绝返回（分位数无法由每桶 pNN 跨桶求得）"
                        ),
                    }
                )
            continue
        rows = _fetch(
            session,
            metrics=[metric],
            start=start,
            end=end,
            service=service,
            labels_key=labels_key,
            limit=MAX_ROWS_FETCH,
        )
        fetched += len(rows)
        shape = spec.shape if spec else SHAPE_GAUGE
        grouped: dict[int, dict[str, float]] = {}
        for r in rows:
            idx = int((as_utc(r.bucket_start) - start).total_seconds()) // max(step_s, 1)
            slot = grouped.setdefault(
                idx, {"sum": 0.0, "max": float("-inf"), "min": float("inf"), "n": 0.0, "wsum": 0.0}
            )
            n = max(int(r.sample_count or 0), 1)
            slot["sum"] += float(r.value_avg)
            slot["max"] = max(slot["max"], float(r.value_max))
            slot["min"] = min(slot["min"], float(r.value_min))
            slot["n"] += n
            slot["wsum"] += float(r.value_avg) * n
        for idx in sorted(grouped):
            slot = grouped[idx]
            n = slot["n"] or 1
            if shape == SHAPE_SUM:
                value, basis = slot["sum"], "sum(value_avg) over step"
            elif shape == SHAPE_AVG:
                value, basis = slot["wsum"] / n, "sample-weighted avg over step"
            else:
                value, basis = slot["max"], "max(value_max) over step"
            out[metric].append(
                {
                    "t": (start + timedelta(seconds=idx * step_s)).isoformat(),
                    "value": value,
                    "samples": int(slot["n"]),
                    "basis": basis,
                }
            )
    return {"series": out, "rows_read": fetched, "refusals": refusals}


__all__ = [
    "MAX_METRICS_PER_REQUEST",
    "MAX_POINTS",
    "MAX_ROWS_FETCH",
    "WindowValue",
    "fetch_buckets_json",
    "percentile_q",
    "series_points",
    "suggested_step",
    "window_value",
]
