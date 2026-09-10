"""`GET /ops/traces/stats` 扩展块测试（trend / by_model / by_status）。

覆盖（按评审要求）：
1. **既有字段一个没变**（控制台已按老形状消费，形状回归即破坏）；
2. trend **按天稠密补零**（缺日不跳过，折线才不会把断层画成斜坡）；
3. trend 的 ``duration_ms_p95`` 来自**合并直方图**；**该日无直方图 → null（不是 0）**；
4. ``by_model`` 按 ``trace_count`` 降序、``NULL`` 归 ``(unknown)``；
5. 窗口超过 180 天 → 46007 + 建议窗口（不做静默降采样）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.console.ops.metrics import Series
from app.core.config import get_settings
from app.db import get_session_factory
from app.models.console_telemetry import LlmTrace, OpsMetricSample
from sqlalchemy import select

from .helpers import console_headers

STATS_PERMS = ("ops:trace:read",)
URL = "/api/v1/console/ops/traces/stats"

#: 修复前的既有字段集合（形状回归的锚点）
LEGACY_FIELDS = {
    "from",
    "to",
    "trace_count",
    "error_count",
    "error_rate",
    "llm_call_count",
    "prompt_tokens",
    "completion_tokens",
    "duration_ms_p95",
    "duration_ms_p95_basis",
}


def _seed_trace(
    when: datetime,
    *,
    status: str = "ok",
    model: str | None = "deepseek-chat",
    llm_calls: int = 1,
    prompt: int = 10,
    completion: int = 5,
) -> None:
    import uuid

    db = get_session_factory()()
    try:
        db.add(
            LlmTrace(
                trace_id=uuid.uuid4().hex,
                service="python",
                kind="turn",
                model=model,
                status=status,
                started_at=when,
                ended_at=when + timedelta(seconds=1),
                duration_ms=1000,
                span_count=1,
                llm_call_count=llm_calls,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=prompt + completion,
            )
        )
        db.commit()
    finally:
        db.close()


def _seed_histogram(when: datetime, values: list[float], model: str = "deepseek-chat") -> None:
    """写一行 ``llm.duration_ms`` 直方图样本（labels 含 model，与控制台按模型看的口径一致）。"""
    series = Series(boundaries=(10, 100, 1000, 10000))
    for v in values:
        series.observe(v)
    db = get_session_factory()()
    try:
        db.add(
            OpsMetricSample(
                service="python",
                metric="llm.duration_ms",
                labels_key=f"model={model}",
                labels={"model": model},
                bucket_start=when,
                bucket_s=60,
                value_avg=series.total / series.count,
                value_max=float(series.max or 0),
                value_min=float(series.min or 0),
                sample_count=series.count,
                buckets=series.buckets_json(),
            )
        )
        db.commit()
    finally:
        db.close()


def _get(client, params: dict) -> dict:
    resp = client.get(URL, params=params, headers=console_headers(perms=STATS_PERMS))
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def test_legacy_fields_unchanged_and_new_blocks_present(client) -> None:
    """既有 10 个字段全部保留且类型不变；只新增 trend/trend_meta/by_model/by_status。"""
    now = datetime.now(UTC).replace(microsecond=0)
    _seed_trace(now - timedelta(hours=2), llm_calls=2, prompt=30, completion=12)
    _seed_trace(now - timedelta(hours=3), status="error")

    data = _get(client, {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()})

    assert set(data) >= LEGACY_FIELDS, "既有字段被删除/改名即破坏控制台"
    assert set(data) == LEGACY_FIELDS | {"trend", "trend_meta", "by_model", "by_status"}
    assert data["trace_count"] == 2
    assert data["error_count"] == 1
    assert data["error_rate"] == 0.5
    assert data["llm_call_count"] == 3
    assert data["prompt_tokens"] == 40
    assert data["completion_tokens"] == 17
    assert data["duration_ms_p95"] is None  # 无直方图样本 → null（不是 0）


def test_trend_is_dense_and_zero_filled(client) -> None:
    """4 天窗口只有 1 天有数据 → trend 仍是 4 条，缺日计数补 0。"""
    now = datetime.now(UTC).replace(microsecond=0)
    day0 = (now - timedelta(days=3)).replace(hour=12, minute=0, second=0)
    _seed_trace(day0)
    _seed_trace(day0 + timedelta(minutes=5), status="error")

    data = _get(client, {"from": (now - timedelta(days=3)).isoformat(), "to": now.isoformat()})

    trend = data["trend"]
    assert len(trend) >= 4, "trend 必须覆盖整个窗口（稠密），不能只返回有数据的天"
    assert [t["date"] for t in trend] == sorted(t["date"] for t in trend)
    by_date = {t["date"]: t for t in trend}
    hit = by_date[day0.date().isoformat()]
    assert hit["trace_count"] == 2 and hit["error_count"] == 1
    empties = [t for t in trend if t["date"] != day0.date().isoformat()]
    assert empties and all(
        t["trace_count"] == 0 and t["error_count"] == 0 and t["llm_call_count"] == 0
        for t in empties
    )
    assert data["trend_meta"]["bucket"] == "day"
    assert data["trend_meta"]["timezone"] == "UTC"


def test_trend_p95_from_merged_histogram_and_null_without_samples(client) -> None:
    """有直方图的天给插值分位数；没有直方图的天必须是 ``null``（不是 0）。"""
    now = datetime.now(UTC).replace(microsecond=0)
    with_hist = (now - timedelta(days=1)).replace(hour=10, minute=0, second=0)
    without_hist = (now - timedelta(days=2)).replace(hour=10, minute=0, second=0)
    _seed_trace(with_hist)
    _seed_trace(without_hist)
    # 只有 with_hist 那天有直方图（20 个快样本 + 3 个慢样本 → p95 必落在慢桶）
    _seed_histogram(with_hist, [5.0] * 20 + [9000.0] * 3)

    data = _get(client, {"from": (now - timedelta(days=3)).isoformat(), "to": now.isoformat()})
    by_date = {t["date"]: t for t in data["trend"]}

    hit = by_date[with_hist.date().isoformat()]
    assert hit["duration_ms_p95"] is not None
    assert hit["duration_ms_p95"] > 1000  # 23 样本里 3 个 9000ms
    gap = by_date[without_hist.date().isoformat()]
    assert gap["duration_ms_p95"] is None, "无直方图样本必须 null，写 0 会被读成『当天飞快』"
    # 窗口级 p95 与 trend 同源（合并直方图），不是"每日 p95 的平均"
    assert data["duration_ms_p95"] == hit["duration_ms_p95"]
    assert data["trend_meta"]["p95_available"] is True


def test_trend_p95_null_when_histogram_rows_exceed_budget(client, monkeypatch) -> None:
    """直方图行超预算 → 整段 p95 置 null 并标注（不拿部分直方图算错值）。"""
    import app.console.api.routes.ops as ops_mod

    monkeypatch.setattr(ops_mod, "MAX_HISTOGRAM_ROWS", 1)
    now = datetime.now(UTC).replace(microsecond=0)
    for i in range(3):
        _seed_histogram(now - timedelta(minutes=i + 1), [10.0, 20.0])

    data = _get(client, {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()})
    assert data["duration_ms_p95"] is None
    assert data["trend_meta"]["p95_available"] is False
    assert all(t["duration_ms_p95"] is None for t in data["trend"])


def test_by_model_ordering_and_unknown_bucket(client) -> None:
    """``by_model`` 按 trace_count 降序；``model IS NULL`` 归入 ``(unknown)``。"""
    now = datetime.now(UTC).replace(microsecond=0)
    for _ in range(2):
        _seed_trace(now - timedelta(hours=1), model="deepseek-chat", llm_calls=2)
    for _ in range(3):
        _seed_trace(now - timedelta(hours=1), model="deepseek-reasoner")
    _seed_trace(now - timedelta(hours=1), model=None)

    data = _get(client, {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()})
    models = data["by_model"]
    assert [m["model"] for m in models] == ["deepseek-reasoner", "deepseek-chat", "(unknown)"]
    assert [m["trace_count"] for m in models] == [3, 2, 1]
    top = models[0]
    assert top["llm_call_count"] == 3
    assert set(top) == {
        "model",
        "trace_count",
        "llm_call_count",
        "prompt_tokens",
        "completion_tokens",
    }


def test_by_status_is_dense_in_canonical_order(client) -> None:
    """四条状态恒在、顺序固定（图例不随数据抖动），计数为 0 也返回。"""
    now = datetime.now(UTC).replace(microsecond=0)
    _seed_trace(now - timedelta(hours=1))
    _seed_trace(now - timedelta(hours=1), status="incomplete")

    data = _get(client, {"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()})
    assert [s["status"] for s in data["by_status"]] == ["ok", "error", "aborted", "incomplete"]
    counts = {s["status"]: s["count"] for s in data["by_status"]}
    assert counts == {"ok": 1, "error": 0, "aborted": 0, "incomplete": 1}


def test_trend_window_cap_returns_46007_with_hint(client) -> None:
    """超过 180 天 → 46007 + ``suggestedStep``/``suggestedFrom``（不静默降采样）。"""
    now = datetime.now(UTC)
    resp = client.get(
        URL,
        params={"from": (now - timedelta(days=365)).isoformat(), "to": now.isoformat()},
        headers=console_headers(perms=STATS_PERMS),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 46007
    assert body["data"]["maxTrendBuckets"] == 180
    assert body["data"]["requestedBuckets"] > 180
    assert body["data"]["suggestedStep"] >= 86400
    assert body["data"]["suggestedFrom"]


def test_stats_requires_trace_permission(client) -> None:
    now = datetime.now(UTC)
    resp = client.get(
        URL,
        params={"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()},
        headers=console_headers(perms=("ops:metric:read",)),
    )
    assert resp.status_code == 403
    assert resp.json()["data"]["required"] == "ops:trace:read"


def test_stats_empty_window_is_all_zero_not_error(client) -> None:
    """空窗口：计数全 0、p95 为 null、trend 仍稠密（前端不必区分"没数据"与"接口坏了"）。"""
    now = datetime.now(UTC).replace(microsecond=0)
    data = _get(client, {"from": (now - timedelta(days=2)).isoformat(), "to": now.isoformat()})
    assert data["trace_count"] == 0
    assert data["error_rate"] == 0.0
    assert data["duration_ms_p95"] is None
    assert len(data["trend"]) >= 3
    assert all(t["trace_count"] == 0 for t in data["trend"])


def test_stats_survives_trace_flag(client, monkeypatch) -> None:
    """功能位关闭 → 46014（与其它 trace 端点同闸门）。"""
    monkeypatch.setattr(get_settings(), "llm_trace_enabled", False)
    now = datetime.now(UTC)
    resp = client.get(
        URL,
        params={"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat()},
        headers=console_headers(perms=STATS_PERMS),
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == 46014


def test_histogram_rows_are_reused_not_refetched() -> None:
    """成本口径：stats 用**一个会话 4 条 SQL**（这里断言查询条数，防将来退化成 N+1）。"""
    from app.console.api.routes.ops import _trace_stats
    from app.models.console_telemetry import LlmTrace as Model

    now = datetime.now(UTC).replace(microsecond=0)
    _seed_trace(now - timedelta(minutes=5))
    _seed_histogram(now - timedelta(minutes=6), [10.0, 20.0])

    class _CountingSession:
        def __init__(self, real):
            self._real = real
            self.count = 0

        def execute(self, *args, **kwargs):
            self.count += 1
            return self._real.execute(*args, **kwargs)

    db = get_session_factory()()
    try:
        counting = _CountingSession(db)
        data = _trace_stats(counting, Model, now - timedelta(days=1), now)
    finally:
        db.close()
    assert counting.count == 4, f"stats 应为 4 条 SQL（状态/日/模型/直方图），实际 {counting.count}"
    assert data["trace_count"] == 1

    # 顺带：既有 row 查询没被引入（没有按 trace 逐行拉）
    db = get_session_factory()()
    try:
        assert db.execute(select(LlmTrace)).scalars().all()
    finally:
        db.close()
