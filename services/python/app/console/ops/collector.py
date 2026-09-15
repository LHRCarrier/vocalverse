"""指标采集器（docs/50 §8.4：单后台任务，每 60s 产出一桶 ``ops_metric_samples``）。

要点：

- **一个任务**：lifespan 启停；单任务天然串行，不与业务抢事件循环（docs/50 §8.1 <1% 开销）；
- **加和 vs 分布**（P0-3）：计数量进 ``value_avg``（= 桶内总和），
  时长类同时写"桶内 pNN 行"与"基础直方图行"；``buckets`` 只对分布型指标填，
  加和型一律留 ``[]`` —— 跨桶分位数只能靠合并直方图重算；
- **连接池**：直读池对象属性（``checkedout()`` / ``size()`` / ``_max_overflow``），
  **不解析** ``engine.pool.status()`` 的人读字符串（SQLAlchemy 2.0 里它是
  "Pool size: 20\\nConnections in pool: …" 这种给人看的文本，格式无契约、改版即碎）。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from app.console.ops.metrics import histogram_percentile, labels_key

logger = logging.getLogger("vocalverse.console.ops.collector")

#: 采集桶宽（docs/50 §13.2：``APP_OPS_TELEMETRY_INTERVAL_S``，默认 60）
DEFAULT_INTERVAL_S = 60
SERVICE = "python"

#: 进程起点（模块导入时刻；与真实进程启动时刻误差 = import 耗时，POC 可接受）
_PROCESS_START = time.monotonic()


class OpsCollector:
    """指标采集后台任务（幂等 start/stop；``tick()`` 可直接被测试调用）。"""

    def __init__(self, interval_s: int | None = None) -> None:
        self._interval = int(interval_s or _interval_from_settings())
        self._task: asyncio.Task | None = None
        self._last_sink: dict[str, int] = {"dropped": 0, "written": 0}
        self._last_alert_errors = 0
        self.errors_total = 0
        self.last_tick_at: datetime | None = None

    # ------------------------------------------------------------------
    async def start(self) -> None:
        if self._task is not None:
            return
        # 内置 6 条预警规则：迁移只做 DDL，seed 归 Python 写方（docs/10 §7.1-2）
        try:
            await asyncio.to_thread(_seed_rules)
        except Exception:  # noqa: BLE001 - 播种失败不阻塞采集启动
            logger.warning("预警规则播种跳过", exc_info=True)
        self._task = asyncio.create_task(self._loop(), name="ops-collector")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self._task  # 关闭路径吞异常（cancel 后 await 必抛 CancelledError）
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._interval)
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - 采集失败不得终止循环（自监控计数）
                self.errors_total += 1
                logger.warning("ops collector tick failed", exc_info=True)

    # ------------------------------------------------------------------
    async def tick(self, bucket_start: datetime | None = None) -> int:
        """产出并写入一桶；返回写入的样本行数（异常不外抛，计入 errors_total）。"""
        now = datetime.now(UTC)
        start = bucket_start or _floor_bucket(now, self._interval)
        try:
            rows = await self._build_rows(start)
            written = await asyncio.to_thread(_write_rows, rows)
            # 同一 tick 内评估预警：指标刚落库，窗口查询读到的是最新一桶
            await asyncio.to_thread(_evaluate_alerts)
            self.last_tick_at = now
            logger.debug("ops collector 桶 %s 写入 %d 行", start.isoformat(), written)
            return written
        except Exception:  # noqa: BLE001
            self.errors_total += 1
            logger.warning("ops collector 写出失败", exc_info=True)
            return 0

    async def _build_rows(self, bucket_start: datetime) -> list[dict[str, Any]]:
        from app.console.ops.metrics import get_registry

        rows: list[dict[str, Any]] = []
        drained = get_registry().drain()

        # 1) 进程
        rows.append(_scalar_row("process.uptime_s", time.monotonic() - _PROCESS_START))
        rss = _rss_mb()
        if rss is not None:
            rows.append(_scalar_row("process.rss_mb", rss))

        # 2) 进程内计数/直方图（HTTP / LLM / ASR 等待）
        for item in drained:
            rows.extend(_rows_for_series(item))

        # 3) 派生比率（桶内）
        rows.extend(_derived_rates(drained))

        # 4) 连接池 / Redis / TTS 预热
        rows.extend(_pool_rows())
        rows.append(_scalar_row("redis.available", 1.0 if await _redis_ok() else 0.0))
        rows.append(_scalar_row("tts.warm.state", _tts_warm_state()))

        # 5) 采集自监控（docs/50 §9.4：采集自己的健康也要可见）
        rows.extend(self._self_monitor_rows())

        for row in rows:
            row.update(
                {"service": SERVICE, "bucket_start": bucket_start, "bucket_s": self._interval}
            )
        return rows

    def _self_monitor_rows(self) -> list[dict[str, Any]]:
        from app.console.trace.sink import get_sink

        stats = get_sink().stats()
        out = []
        for metric, key in (("trace.dropped", "dropped"), ("trace.written", "written")):
            delta = max(int(stats[key]) - int(self._last_sink.get(key, 0)), 0)
            self._last_sink[key] = int(stats[key])
            out.append(_scalar_row(metric, float(delta)))
        try:
            from app.console.ops.alerts import eval_errors_total

            delta = max(int(eval_errors_total()) - self._last_alert_errors, 0)
            self._last_alert_errors = int(eval_errors_total())
            out.append(_scalar_row("ops.alert.eval_errors", float(delta)))
        except Exception:  # noqa: BLE001
            pass
        return out


# ---------------------------------------------------------------------------
# 行构造
# ---------------------------------------------------------------------------
def _scalar_row(metric: str, value: float) -> dict[str, Any]:
    return {
        "metric": metric,
        "labels_key": "",
        "labels": {},
        "value_avg": float(value),
        "value_max": float(value),
        "value_min": float(value),
        "sample_count": 1,
        "buckets": [],
    }


def _rows_for_series(item: dict[str, Any]) -> list[dict[str, Any]]:
    """一条序列 → 样本行（分布型额外展开 ``.pNN`` 行且带 buckets）。"""
    from app.console.ops.catalog import (
        SHAPE_DISTRIBUTION,
        SHAPE_SUM,
        spec_of,
    )

    metric: str = item["metric"]
    series = item["series"]
    spec = spec_of(metric)
    shape = spec.shape if spec else SHAPE_SUM
    base = {
        "metric": metric,
        "labels_key": item["labels_key"],
        "labels": item["labels"],
        "sample_count": series.count,
        "buckets": [],
    }
    if shape == SHAPE_DISTRIBUTION:
        avg = series.total / series.count if series.count else 0.0
        rows = [
            {
                **base,
                "value_avg": avg,
                "value_max": float(series.max if series.max is not None else 0.0),
                "value_min": float(series.min if series.min is not None else 0.0),
                "buckets": series.buckets_json(),
            }
        ]
        hist = series.buckets_json()
        for q, name in (("p50", "p50"), ("p95", "p95"), ("p99", "p99")):
            value = histogram_percentile(hist, {"p50": 0.5, "p95": 0.95, "p99": 0.99}[q])
            if value is None:
                continue
            rows.append(
                {
                    **base,
                    "metric": f"{metric}.{name}",
                    "value_avg": float(value),
                    "value_max": float(value),
                    "value_min": float(value),
                }
            )
        return rows
    # 加和/均值/水位：count 语义直接看 value_avg
    return [
        {
            **base,
            "value_avg": float(series.total),
            "value_max": float(series.max if series.max is not None else series.total),
            "value_min": float(series.min if series.min is not None else series.total),
        }
    ]


def _derived_rates(drained: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """桶内比率（错误率/LLM 失败率）：明确标注为"桶内"口径，跨桶不做精确聚合。"""
    totals: dict[str, float] = {}
    for item in drained:
        totals[item["metric"]] = totals.get(item["metric"], 0.0) + float(item["series"].total)
    out = []
    for num, den, name in (
        ("http.request.error.count", "http.request.count", "http.request.error_rate"),
        ("llm.error.count", "llm.call.count", "llm.error_rate"),
    ):
        d = totals.get(den, 0.0)
        if d <= 0:
            continue
        out.append(_scalar_row(name, totals.get(num, 0.0) / d))
    return out


def _pool_rows() -> list[dict[str, Any]]:
    """连接池占用：**直读属性**，不解析 ``pool.status()`` 字符串。"""
    try:
        from app.db import get_engine

        pool = get_engine().pool
        checked_out = _pool_checked_out(pool)
        capacity = _pool_capacity(pool)
        if checked_out is None:
            return []
        out = [_scalar_row("db.pool.checked_out", float(checked_out))]
        if capacity:
            out.append(_scalar_row("db.pool.utilization", float(checked_out) / float(capacity)))
        return out
    except Exception:  # noqa: BLE001
        return []


def _pool_checked_out(pool) -> int | None:
    for attr in ("checkedout", "checked_out"):
        fn = getattr(pool, attr, None)
        if callable(fn):
            try:
                return int(fn())
            except Exception:  # noqa: BLE001
                continue
    return None


def _pool_capacity(pool) -> int | None:
    """``pool_size + max_overflow``（QueuePool）；其它池型退回 ``size()``。"""
    size = None
    fn = getattr(pool, "size", None)
    if callable(fn):
        try:
            size = int(fn())
        except Exception:  # noqa: BLE001
            size = None
    overflow = int(getattr(pool, "_max_overflow", 0) or 0)
    if size is None:
        return overflow or None
    return size + overflow


def _rss_mb() -> float | None:
    """常驻内存（MB）：Linux 读 ``/proc/self/statm``，Windows 走 psapi（无三方依赖）。"""
    try:
        import sys

        if sys.platform.startswith("win"):
            return _rss_mb_windows()
        with open("/proc/self/statm", encoding="ascii") as fh:
            pages = int(fh.read().split()[1])
        return pages * 4096 / (1024 * 1024)
    except Exception:  # noqa: BLE001
        return None


def _rss_mb_windows() -> float | None:
    import ctypes
    from ctypes import wintypes

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
        ctypes.windll.kernel32.GetCurrentProcess(),  # type: ignore[attr-defined]
        ctypes.byref(counters),
        counters.cb,
    )
    if not ok:
        return None
    return counters.WorkingSetSize / (1024 * 1024)


async def _redis_ok() -> bool:
    from app.core.redis_client import redis_ping

    try:
        return await redis_ping()
    except Exception:  # noqa: BLE001
        return False


def _tts_warm_state() -> float:
    """``app.state.tts_warm_task`` 是否仍在跑（0/1）。"""
    try:
        from app.main import app

        task = getattr(app.state, "tts_warm_task", None)
        return 1.0 if (task is not None and not task.done() and not task.cancelled()) else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


# ---------------------------------------------------------------------------
# 写库（一批一事务；同桶重采 = upsert 覆盖，靠唯一键幂等）
# ---------------------------------------------------------------------------
def _write_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    from app.db import get_session_factory
    from app.models.console_telemetry import OpsMetricSample

    supports_buckets = hasattr(OpsMetricSample, "buckets")
    db = get_session_factory()()
    try:
        for row in rows:
            payload = {k: v for k, v in row.items() if k != "buckets"}
            if supports_buckets:
                payload["buckets"] = row.get("buckets") or []
            existing = db.execute(
                select(OpsMetricSample.id).where(
                    OpsMetricSample.service == row["service"],
                    OpsMetricSample.metric == row["metric"],
                    OpsMetricSample.labels_key == row["labels_key"],
                    OpsMetricSample.bucket_start == row["bucket_start"],
                    OpsMetricSample.bucket_s == row["bucket_s"],
                )
            ).first()
            if existing is None:
                db.add(OpsMetricSample(**payload))
            else:
                db.execute(
                    OpsMetricSample.__table__.update()
                    .where(OpsMetricSample.id == existing[0])
                    .values(**{k: v for k, v in payload.items() if k not in ("service", "metric")})
                )
        db.commit()
        return len(rows)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _seed_rules() -> int:
    """幂等播种内置预警规则（collector 启动时一次）。"""
    from app.console.ops.alerts import ensure_seed_rules
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        return ensure_seed_rules(db)
    finally:
        db.close()


def _evaluate_alerts() -> list[dict]:
    """评估预警（每个采集 tick 一次；失败在 alerts 内部计数，不外抛）。"""
    from app.console.ops.alerts import evaluate
    from app.db import get_session_factory

    db = get_session_factory()()
    try:
        return evaluate(db)
    finally:
        db.close()


def _floor_bucket(now: datetime, interval: int) -> datetime:
    """桶起点对齐到 interval 秒边界（UTC）。"""
    epoch = int(now.timestamp())
    floored = epoch - (epoch % max(interval, 1))
    return datetime.fromtimestamp(floored, UTC)


def _interval_from_settings() -> int:
    try:
        from app.core.config import get_settings

        return int(get_settings().ops_telemetry_interval_s) or DEFAULT_INTERVAL_S
    except Exception:  # noqa: BLE001
        return DEFAULT_INTERVAL_S


def telemetry_enabled() -> bool:
    try:
        from app.core.config import get_settings

        return bool(get_settings().ops_telemetry_enabled)
    except Exception:  # noqa: BLE001
        return False


#: 提示：bucket 窗口查询用（end 开区间）
def bucket_window(now: datetime, window_s: int) -> tuple[datetime, datetime]:
    return now - timedelta(seconds=window_s), now


__all__ = [
    "DEFAULT_INTERVAL_S",
    "OpsCollector",
    "bucket_window",
    "telemetry_enabled",
    "labels_key",
]
