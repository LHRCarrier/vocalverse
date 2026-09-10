"""进程内指标登记表（docs/50 §8.4）。

**为什么分"加和型"与"分布型"**（P0-3 的硬要求）：

- 计数量（``http.request.count`` / ``llm.tokens.*`` / ``trace.written``）是**可加**的，
  跨桶直接求和/求均值都对；
- 时长/等待/TTFT 是**分布**型的：跨桶求"p95 的平均"在数学上没有任何意义
  （不同桶的样本量不同、分位点位置不同）。故本模块按**固定分桶直方图**累计
  （Prometheus 口径的累计计数），把跨桶分位数计算交给"合并直方图后重新插值"——
  这才是唯一站得住的口径（docs/50 §8.4 的界面副标题也必须照此声明）。

直方图落 ``ops_metric_samples.buckets``，格式 ``[[upper_bound, 累计计数], ...]``，
最后一对的 ``upper_bound`` 为 ``null`` 表示 ``+Inf`` 溢出桶（JSON 不允许 Infinity 字面量）。
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any

#: 请求/LLM 时长分桶（ms）——覆盖 5ms~60s，桶界按 2~2.5 倍递增
DURATION_BUCKETS_MS: tuple[float, ...] = (
    5,
    10,
    25,
    50,
    100,
    250,
    500,
    1000,
    2000,
    5000,
    10000,
    30000,
    60000,
)
#: 队列/信号量等待分桶（ms）
WAIT_BUCKETS_MS: tuple[float, ...] = (1, 5, 10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 30000)
#: token 分桶
TOKEN_BUCKETS: tuple[float, ...] = (50, 100, 250, 500, 1000, 2000, 4000, 8000, 16000, 32000, 64000)

#: 指标名 → 分桶界（未登记的名称默认用 DURATION_BUCKETS_MS）
BUCKETS_BY_METRIC: dict[str, tuple[float, ...]] = {
    "http.request.duration_ms": DURATION_BUCKETS_MS,
    "http.request.duration_ms.p50": DURATION_BUCKETS_MS,
    "http.request.duration_ms.p95": DURATION_BUCKETS_MS,
    "http.request.duration_ms.p99": DURATION_BUCKETS_MS,
    "llm.duration_ms": DURATION_BUCKETS_MS,
    "llm.duration_ms.p95": DURATION_BUCKETS_MS,
    "llm.ttft_ms": DURATION_BUCKETS_MS,
    "llm.ttft_ms.p95": DURATION_BUCKETS_MS,
    "asr.queue.wait_ms": WAIT_BUCKETS_MS,
    "asr.queue.wait_ms.p95": WAIT_BUCKETS_MS,
    "llm.tokens.prompt": TOKEN_BUCKETS,
    "llm.tokens.completion": TOKEN_BUCKETS,
}


@dataclass
class Series:
    """一条 (metric, labels) 序列的桶内累计（直方图记 cumulative，标量记 count/total）。"""

    boundaries: tuple[float, ...]
    counts: list[int] = field(default_factory=list)
    count: int = 0
    total: float = 0.0
    min: float | None = None
    max: float | None = None

    def __post_init__(self) -> None:
        if not self.counts:
            self.counts = [0] * (len(self.boundaries) + 1)  # 末槽 = +Inf 溢出桶

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.min = value if self.min is None else min(self.min, value)
        self.max = value if self.max is None else max(self.max, value)
        for i, bound in enumerate(self.boundaries):
            if value <= bound:
                self.counts[i] += 1
                return
        self.counts[-1] += 1

    def add(self, value: float) -> None:
        """加和型累加（value 恒为增量）。"""
        self.count += 1
        self.total += value
        self.min = value if self.min is None else min(self.min, value)
        self.max = value if self.max is None else max(self.max, value)

    def buckets_json(self) -> list[list[Any]]:
        """累计直方图 → ``[[upper_bound, cumulative], ...]``；末桶 bound=None 表示 +Inf。"""
        out: list[list[Any]] = []
        cum = 0
        for i, bound in enumerate(self.boundaries):
            cum += self.counts[i]
            out.append([bound, cum])
        cum += self.counts[-1]
        out.append([None, cum])
        return out

    def snapshot(self) -> Series:
        copy = Series(
            boundaries=self.boundaries,
            counts=list(self.counts),
            count=self.count,
            total=self.total,
            min=self.min,
            max=self.max,
        )
        return copy

    def reset(self) -> None:
        self.counts = [0] * (len(self.boundaries) + 1)
        self.count = 0
        self.total = 0.0
        self.min = None
        self.max = None


class MetricsRegistry:
    """线程安全登记表（观测点可能来自 worker 线程，如 ASR 信号量等待）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._series: dict[tuple[str, str], Series] = {}
        self._gauges: dict[tuple[str, str], float] = {}
        self._labels: dict[tuple[str, str], dict[str, Any]] = {}

    # -- 写入 ---------------------------------------------------------------
    def observe(self, metric: str, value: float, labels: dict[str, Any] | None = None):
        self._with_series(metric, labels).observe(float(value))

    def add(self, metric: str, value: float, labels: dict[str, Any] | None = None):
        self._with_series(metric, labels).add(float(value))

    def incr(self, metric: str, value: float = 1.0, labels: dict[str, Any] | None = None):
        self.add(metric, value, labels)

    def set_gauge(self, metric: str, value: float, labels: dict[str, Any] | None = None):
        with self._lock:
            key = (metric, labels_key(labels))
            self._gauges[key] = float(value)
            self._labels[key] = dict(labels or {})

    def add_gauge(self, metric: str, delta: float, labels: dict[str, Any] | None = None):
        with self._lock:
            key = (metric, labels_key(labels))
            self._gauges[key] = self._gauges.get(key, 0.0) + float(delta)
            self._labels[key] = dict(labels or {})

    def _with_series(self, metric: str, labels: dict[str, Any] | None) -> Series:
        key = (metric, labels_key(labels))
        with self._lock:
            series = self._series.get(key)
            if series is None:
                series = Series(boundaries=BUCKETS_BY_METRIC.get(metric, DURATION_BUCKETS_MS))
                self._series[key] = series
                self._labels[key] = dict(labels or {})
            return series

    # -- 读取（collector 每桶 drain 一次） ------------------------------------
    def drain(self) -> list[dict[str, Any]]:
        """取出并清空所有计数器/直方图（按 60s 桶口径）。"""
        with self._lock:
            out = []
            for (metric, lkey), series in self._series.items():
                snap = series.snapshot()
                series.reset()
                if snap.count == 0:
                    continue
                out.append(
                    {
                        "metric": metric,
                        "labels_key": lkey,
                        "labels": dict(self._labels.get((metric, lkey), {})),
                        "series": snap,
                    }
                )
        return out

    def gauges(self) -> dict[str, float]:
        """当前标量（在途请求数等）；``metric|labels_key`` → 值。"""
        with self._lock:
            return {f"{m}|{lk}": v for (m, lk), v in self._gauges.items()}

    def reset(self) -> None:
        with self._lock:
            self._series.clear()
            self._gauges.clear()
            self._labels.clear()


_REGISTRY = MetricsRegistry()


def get_registry() -> MetricsRegistry:
    return _REGISTRY


def reset_registry_for_tests() -> MetricsRegistry:
    _REGISTRY.reset()
    return _REGISTRY


def labels_key(labels: dict[str, Any] | None) -> str:
    """标签规范化键（排序拼接）——参与 ``ops_metric_samples`` 唯一键，避免 jsonb 直接比较。"""
    if not labels:
        return ""
    items = sorted((str(k), _scalar(v)) for k, v in labels.items())
    return ",".join(f"{k}={v}" for k, v in items)[:160]


def _scalar(v: Any) -> str:
    if v is None:
        return ""
    return str(v)[:32]


# ---------------------------------------------------------------------------
# trace → llm.* 指标（recorder 收尾时调用，docs/50 §8.4「来自 trace 聚合」）
# ---------------------------------------------------------------------------
def record_trace(rec) -> None:
    """把一条已收尾的 trace 折算成 llm.* 指标。

    走**进程内**而不是回查 ``llm_traces``：collector 每 60s 只做一次快照，
    实时性更好，也避免"指标采集再打一次业务库"（docs/50 §8.1 采集开销 <1% 的口径）。
    """
    spans = [s for s in rec.spans if s.name == "LLM"]
    if not spans:
        return
    reg = _REGISTRY
    for s in spans:
        model = s.model or rec.model or "unknown"
        reg.incr("llm.call.count", 1, {"model": model})
        if s.status != "ok":
            reg.incr("llm.error.count", 1, {"model": model})
        if s.duration_ms is not None:
            reg.observe("llm.duration_ms", float(s.duration_ms), {"model": model})
        if s.ttft_ms is not None:
            reg.observe("llm.ttft_ms", float(s.ttft_ms), {"model": model})
        if s.prompt_tokens is not None:
            reg.add("llm.tokens.prompt", float(s.prompt_tokens), {"model": model})
        if s.completion_tokens is not None:
            reg.add("llm.tokens.completion", float(s.completion_tokens), {"model": model})


# ---------------------------------------------------------------------------
# 直方图合并 + 分位数（跨桶唯一合法口径）
# ---------------------------------------------------------------------------
def merge_histograms(histograms: list[list[list[Any]]]) -> list[list[Any]]:
    """合并多桶累计直方图（同界逐项相加；界不一致时按并集重排）。"""
    merged: dict[Any, float] = {}
    for h in histograms:
        if not h:
            continue
        prev = 0.0
        for bound, cum in h:
            delta = float(cum) - prev
            prev = float(cum)
            merged[bound] = merged.get(bound, 0.0) + delta
    out: list[list[Any]] = []
    cum = 0.0
    for bound in sorted(merged, key=lambda b: (b is None, b if b is not None else 0)):
        cum += merged[bound]
        out.append([bound, cum])
    return out


def histogram_percentile(hist: list[list[Any]], q: float) -> float | None:
    """在**合并后**的累计直方图上插值求分位数（桶内线性插值）。

    返回 ``None`` 表示无样本；落进 ``+Inf`` 溢出桶时返回该桶下界（无法插值，
    调用方应如实在口径说明里标注为"下界估计"）。
    """
    if not hist:
        return None
    total = float(hist[-1][1])
    if total <= 0:
        return None
    target = q * total
    prev_bound = 0.0
    prev_cum = 0.0
    for bound, cum in hist:
        cum = float(cum)
        if cum >= target:
            if bound is None:
                return prev_bound
            span = cum - prev_cum
            if span <= 0:
                return float(bound)
            frac = (target - prev_cum) / span
            return prev_bound + (float(bound) - prev_bound) * frac
        prev_bound = float(bound) if bound is not None else prev_bound
        prev_cum = cum
    return prev_bound


__all__ = [
    "BUCKETS_BY_METRIC",
    "DURATION_BUCKETS_MS",
    "TOKEN_BUCKETS",
    "WAIT_BUCKETS_MS",
    "MetricsRegistry",
    "Series",
    "get_registry",
    "histogram_percentile",
    "labels_key",
    "merge_histograms",
    "record_trace",
    "reset_registry_for_tests",
]
