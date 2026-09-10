"""运维指标与依赖探测测试（docs/50 §14.2 第 3、5 条）。

- ``redis_available()`` **必须真 PING**（回归既有缺陷：旧实现只判客户端对象非空）；
- ``db.pool.utilization`` 直读池属性（不解析 ``pool.status()`` 人读文本）；
- 指标查询点数上限 → 46007 + ``data.suggestedStep``；
- 直方图跨桶合并重算分位数（不是"p95 的平均"）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.console.ops.collector import _pool_capacity, _pool_checked_out, _scalar_row
from app.console.ops.metrics import (
    Series,
    histogram_percentile,
    merge_histograms,
)
from app.console.ops.query import MAX_POINTS, percentile_q, suggested_step
from app.core import redis_client
from app.core.config import get_settings
from sqlalchemy import select

from .helpers import console_headers


# ---------------------------------------------------------------------------
# redis_available：真实 PING（回归既有缺陷）
# ---------------------------------------------------------------------------
def test_redis_available_returns_false_when_ping_fails(monkeypatch) -> None:
    """**回归用例**：Redis 进程已死（PING 抛 ConnectionError）时必须返回 False。

    修复前实现是 ``return get_redis() is not None`` —— 而 ``from_url`` 不做网络 IO，
    于是本用例在修复前返回 True（红）。
    """
    redis_client.reset_probe_cache()
    monkeypatch.setattr(redis_client, "get_redis", lambda: object())

    class _DeadClient:
        def ping(self) -> bool:
            raise ConnectionError("connection refused")

    monkeypatch.setattr(redis_client, "_probe_sync_client", lambda timeout_s: _DeadClient())
    assert redis_client.redis_available() is False


def test_redis_available_true_when_ping_ok(monkeypatch) -> None:
    redis_client.reset_probe_cache()
    monkeypatch.setattr(redis_client, "get_redis", lambda: object())

    class _OkClient:
        def ping(self) -> bool:
            return True

    monkeypatch.setattr(redis_client, "_probe_sync_client", lambda timeout_s: _OkClient())
    assert redis_client.redis_available() is True


def test_redis_available_false_without_client(monkeypatch) -> None:
    redis_client.reset_probe_cache()
    monkeypatch.setattr(redis_client, "get_redis", lambda: None)
    assert redis_client.redis_available() is False


@pytest.mark.asyncio
async def test_probe_dependencies_reports_database_and_redis(client) -> None:
    """依赖探测两个条目都在，且 /readyz 与控制台 ops/services 同源。"""
    resp = client.get("/readyz")
    assert resp.status_code == 200
    data = resp.json()["data"]
    names = [i["name"] for i in data["items"]]
    assert names == ["database", "redis"]
    assert data["status"] == "ready"  # testing 档：sqlite 可连 + redis 未启用（内存 fallback）

    console = client.get(
        "/api/v1/console/ops/services",
        headers=console_headers(perms=("ops:overview:read",)),
    ).json()["data"]

    # 同源同口径：除耗时/时间戳外逐字段一致（latency_ms 是实时测量值，天然会抖）
    def _strip(items):
        return [{k: v for k, v in i.items() if k != "latency_ms"} for i in items]

    assert _strip(console["items"]) == _strip(data["items"])


# ---------------------------------------------------------------------------
# 连接池：直读属性
# ---------------------------------------------------------------------------
def test_pool_utilization_reads_attributes_not_status_string() -> None:
    """``engine.pool.status()`` 是人读字符串，解析它会随 SQLAlchemy 改版碎掉。"""

    class _FakePool:
        def checkedout(self) -> int:
            return 5

        def size(self) -> int:
            return 20

        _max_overflow = 10

    assert _pool_checked_out(_FakePool()) == 5
    assert _pool_capacity(_FakePool()) == 30
    # 占用率 = 5/30（而不是从 "Pool size: 20\nConnections in pool: …" 里抠数字）
    assert round(5 / _pool_capacity(_FakePool()), 4) == round(5 / 30, 4)


def test_pool_helpers_tolerate_unknown_pool_type() -> None:
    class _Weird:
        pass

    assert _pool_checked_out(_Weird()) is None
    assert _pool_capacity(_Weird()) is None


# ---------------------------------------------------------------------------
# 直方图：跨桶合并重算分位数
# ---------------------------------------------------------------------------
def test_histogram_percentile_interpolates_within_bucket() -> None:
    s = Series(boundaries=(10, 100, 1000))
    for v in (5, 20, 30, 900):
        s.observe(v)
    hist = s.buckets_json()
    assert hist[-1][0] is None  # +Inf 溢出桶用 null（JSON 无 Infinity 字面量）
    assert hist[-1][1] == 4
    p50 = histogram_percentile(hist, 0.5)
    # 50 分位落在 (10, 100] 桶内 → 桶内线性插值结果必须还在该桶区间里
    assert p50 is not None and 10 <= p50 <= 100


def test_merge_histograms_then_percentile_not_average_of_percentiles() -> None:
    """跨桶分位数**必须**合并直方图重算：两桶样本量悬殊时，"p95 的平均"会明显偏。"""
    a = Series(boundaries=(10, 100, 1000))
    for _ in range(99):
        a.observe(5)  # 99 个快样本
    a.observe(900)
    b = Series(boundaries=(10, 100, 1000))
    for _ in range(100):
        b.observe(900)  # 100 个慢样本

    hist_a, hist_b = a.buckets_json(), b.buckets_json()
    merged = merge_histograms([hist_a, hist_b])
    p95_merged = histogram_percentile(merged, 0.95)
    avg_of_p95 = (histogram_percentile(hist_a, 0.95) + histogram_percentile(hist_b, 0.95)) / 2

    assert p95_merged is not None and avg_of_p95 is not None
    # 合并后总共 200 个样本，199 个是慢的 → 真 p95 落在慢桶里；"平均 p95"被快桶拉低
    assert p95_merged > avg_of_p95
    assert p95_merged > 100


def test_percentile_q_parsing() -> None:
    assert percentile_q("http.request.duration_ms.p95") == 0.95
    assert percentile_q("llm.ttft_ms.p50") == 0.5
    assert percentile_q("llm.call.count") is None


def test_suggested_step_grows_with_window() -> None:
    assert suggested_step(3600, 60) == 60
    big = suggested_step(MAX_POINTS * 60 * 3, 60)
    assert big > 60 and (MAX_POINTS * 60 * 3) / big <= MAX_POINTS


# ---------------------------------------------------------------------------
# 指标查询端点：点数闸门 + 成本闸门
# ---------------------------------------------------------------------------
def _seed_metric_row(metric: str, value: float, when: datetime, labels: dict | None = None):
    from app.db import get_session_factory
    from app.models.console_telemetry import OpsMetricSample

    db = get_session_factory()()
    try:
        db.add(
            OpsMetricSample(
                service="python",
                metric=metric,
                labels_key="",
                labels=labels or {},
                bucket_start=when,
                bucket_s=60,
                value_avg=value,
                value_max=value,
                value_min=value,
                sample_count=1,
            )
        )
        db.commit()
    finally:
        db.close()


def test_metrics_query_rejects_too_many_points(client) -> None:
    """``(to-from)/step > 5000`` → 46007，且 ``data.suggestedStep`` 给出建议 step。"""
    now = datetime.now(UTC)
    frm = (now - timedelta(days=7)).isoformat()
    to = now.isoformat()
    resp = client.get(
        "/api/v1/console/ops/metrics",
        params={"metric": "http.request.count", "from": frm, "to": to, "step": 60},
        headers=console_headers(),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 46007
    assert body["data"]["suggestedStep"] > 60
    assert body["data"]["maxPoints"] == MAX_POINTS


def test_metrics_query_rejects_too_many_metric_params(client) -> None:
    """成本闸门：单请求 metric 个数上限（看板 15s 轮询与业务共池，不能无限扫）。"""
    now = datetime.now(UTC)
    resp = client.get(
        "/api/v1/console/ops/metrics",
        params={
            "metric": ["http.request.count"] * 9,
            "from": (now - timedelta(minutes=10)).isoformat(),
            "to": now.isoformat(),
            "step": 60,
        },
        headers=console_headers(),
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == 46007


def test_metrics_query_returns_series_and_honest_basis(client) -> None:
    """正常查询返回 series，并附上该指标的**口径字典**（shape/percentile_supported）。"""
    now = datetime.now(UTC)
    _seed_metric_row("http.request.count", 12.0, now - timedelta(seconds=120))
    resp = client.get(
        "/api/v1/console/ops/metrics",
        params={
            "metric": "http.request.count",
            "from": (now - timedelta(minutes=10)).isoformat(),
            "to": now.isoformat(),
            "step": 300,
        },
        headers=console_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["series"]["http.request.count"]
    assert data["catalog"]["http.request.count"]["shape"] == "sum"


def test_catalog_marks_distribution_metrics_with_histogram_source(client) -> None:
    """分位指标必须声明其真源（``percentile_of``），否则接口无法正确重算。"""
    resp = client.get("/api/v1/console/ops/metrics/catalog", headers=console_headers()).json()[
        "data"
    ]
    by_name = {m["name"]: m for m in resp}
    assert by_name["http.request.duration_ms.p95"]["percentile_of"] == "http.request.duration_ms"
    assert by_name["http.request.duration_ms"]["shape"] == "distribution"
    assert by_name["process.rss_mb"]["percentile_supported"] is False


def test_percentile_request_without_histogram_is_refused(client) -> None:
    """**拒绝而不是给个错数**（P0-3）：只有每桶 p95 行、没有基础直方图 → 46007。"""
    now = datetime.now(UTC)
    _seed_metric_row("llm.ttft_ms.p95", 999.0, now - timedelta(seconds=120))
    resp = client.get(
        "/api/v1/console/ops/metrics",
        params={
            "metric": "llm.ttft_ms.p95",
            "from": (now - timedelta(minutes=10)).isoformat(),
            "to": now.isoformat(),
            "step": 300,
        },
        headers=console_headers(),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 46007
    assert body["data"]["reason"] == "percentile_requires_histogram"
    assert body["data"]["refusals"][0]["histogram_metric"] == "llm.ttft_ms"


def test_collector_writes_histogram_buckets_for_distribution_metrics(client) -> None:
    """分布型指标必须落 ``buckets`` 直方图（否则跨桶分位数无真源，P0-3）。"""
    import asyncio

    from app.console.ops.collector import OpsCollector
    from app.console.ops.metrics import get_registry
    from app.db import get_session_factory
    from app.models.console_telemetry import OpsMetricSample

    for value in (5.0, 120.0, 900.0):
        get_registry().observe("llm.ttft_ms", value, {"model": "deepseek-chat"})

    collector = OpsCollector(interval_s=60)
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(collector.tick())

    db = get_session_factory()()
    try:
        rows = list(
            db.execute(
                select(OpsMetricSample).where(OpsMetricSample.metric == "llm.ttft_ms")
            ).scalars()
        )
        other = list(
            db.execute(
                select(OpsMetricSample).where(OpsMetricSample.metric == "process.uptime_s")
            ).scalars()
        )
    finally:
        db.close()

    assert len(rows) == 1
    hist = rows[0].buckets
    assert hist and hist[-1][0] is None and hist[-1][1] == 3
    # 加和/水位型指标不得带直方图（两类不混进同一列）
    assert other and other[0].buckets == []


def test_telemetry_flag_disabled_returns_46014(client, monkeypatch) -> None:
    """``APP_OPS_TELEMETRY_ENABLED=false`` → ops 端点 46014（library 端点不受影响）。"""
    monkeypatch.setattr(get_settings(), "ops_telemetry_enabled", False)
    resp = client.get("/api/v1/console/ops/overview", headers=console_headers())
    assert resp.status_code == 403
    assert resp.json()["code"] == 46014


def test_collector_tick_writes_bucket_rows(client) -> None:
    """采集器一 tick：进程指标 + 自监控指标落库，桶起点对齐 60s。"""
    import asyncio

    from app.console.ops.collector import OpsCollector
    from app.db import get_session_factory
    from app.models.console_telemetry import OpsMetricSample

    collector = OpsCollector(interval_s=60)
    written = asyncio.get_event_loop_policy().new_event_loop().run_until_complete(collector.tick())
    assert written > 0

    db = get_session_factory()()
    try:
        rows = list(db.execute(select(OpsMetricSample)).scalars())
    finally:
        db.close()
    metrics = {r.metric for r in rows}
    assert "process.uptime_s" in metrics
    assert "trace.dropped" in metrics
    assert "redis.available" in metrics
    assert all(r.bucket_s == 60 and r.bucket_start.second == 0 for r in rows)


def test_scalar_row_shape() -> None:
    row = _scalar_row("x", 1.5)
    assert row["value_avg"] == row["value_max"] == row["value_min"] == 1.5
    assert row["buckets"] == []
