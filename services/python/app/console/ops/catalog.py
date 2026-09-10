"""指标目录（docs/50 §8.4 的逐项口径声明）。

**为什么要逐项声明 shape**（P0-3）：接口层必须能回答"这个指标跨桶能不能求分位数"。
- ``sum`` 加和型（计数/token）：跨桶求和正确；
- ``avg`` 均值型（占比）：跨桶只能"平均的再平均"（近似，需在界面标注）；
- ``gauge`` 水位型（uptime/rss/在途/池利用率）：跨桶取 max 或 last，求和无意义；
- ``distribution`` 分布型：**带直方图**，跨桶合并历史分桶后重新插值是唯一合法口径。

``percentile_of`` 指明该 ``.pNN`` 指标的历史真源（基础直方图指标名）：
查询/预警求窗口分位数时**合并基础指标的直方图**，而不是对每桶已算好的 pNN 再取平均。
"""

from __future__ import annotations

from dataclasses import dataclass

#: shape 取值
SHAPE_SUM = "sum"
SHAPE_AVG = "avg"
SHAPE_GAUGE = "gauge"
SHAPE_DISTRIBUTION = "distribution"


@dataclass(frozen=True)
class MetricSpec:
    """目录项：名称 / 单位 / 口径类型 / 说明 / （分位指标）历史真源。"""

    name: str
    unit: str
    shape: str
    description: str
    percentile_of: str | None = None
    labels_hint: str | None = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "shape": self.shape,
            "description": self.description,
            "labels": self.labels_hint,
            "percentile_of": self.percentile_of,
            # 能否对时间窗求分位数（跨桶）：只有 distribution（或指向 distribution 的 pNN）可以
            "percentile_supported": self.shape == SHAPE_DISTRIBUTION or bool(self.percentile_of),
        }


_HTTP_DUR = MetricSpec(
    "http.request.duration_ms",
    "ms",
    SHAPE_DISTRIBUTION,
    "HTTP 处理时长直方图（进程内固定分桶累计，跨桶可合并）",
    labels_hint="route",
)
_LLM_DUR = MetricSpec(
    "llm.duration_ms",
    "ms",
    SHAPE_DISTRIBUTION,
    "LLM 调用时长直方图（每次 LLM 尝试一个样本）",
    labels_hint="model",
)
_LLM_TTFT = MetricSpec(
    "llm.ttft_ms",
    "ms",
    SHAPE_DISTRIBUTION,
    "LLM 首 token 延迟直方图（仅流式调用有值）",
    labels_hint="model",
)
_ASR_WAIT = MetricSpec(
    "asr.queue.wait_ms",
    "ms",
    SHAPE_DISTRIBUTION,
    "ASR 信号量排队等待直方图（docs/50 §8.4 新增计时）",
)


def _p(base: MetricSpec, q: str) -> MetricSpec:
    return MetricSpec(
        f"{base.name}.{q}",
        base.unit,
        SHAPE_GAUGE,
        f"{base.description} · 桶内 {q.upper()}（跨桶查询时合并 {base.name} 直方图重算）",
        percentile_of=base.name,
        labels_hint=base.labels_hint,
    )


CATALOG: tuple[MetricSpec, ...] = (
    # ---- 进程 ----
    MetricSpec("process.uptime_s", "s", SHAPE_GAUGE, "进程运行时长（采集进程内起点计）"),
    MetricSpec("process.rss_mb", "MB", SHAPE_GAUGE, "进程常驻内存（/proc 或 Windows API 读取）"),
    # ---- HTTP ----
    MetricSpec(
        "http.request.count",
        "次/桶",
        SHAPE_SUM,
        "HTTP 请求数（按 labels.route 分组）",
        labels_hint="route",
    ),
    _p(_HTTP_DUR, "p50"),
    _p(_HTTP_DUR, "p95"),
    _p(_HTTP_DUR, "p99"),
    _HTTP_DUR,
    MetricSpec(
        "http.request.error.count",
        "次/桶",
        SHAPE_SUM,
        "HTTP 4xx+5xx 请求数（error_rate 的分子）",
        labels_hint="route",
    ),
    MetricSpec(
        "http.request.error_rate",
        "0-1",
        SHAPE_AVG,
        "HTTP 错误率（**桶内** 4xx+5xx 占比；跨桶只做平均的再平均，非精确率）",
    ),
    MetricSpec("http.inflight", "个", SHAPE_GAUGE, "在途请求数（纯 ASGI 中间件计数）"),
    # ---- 数据库 / 缓存 ----
    MetricSpec(
        "db.pool.utilization",
        "0-1",
        SHAPE_GAUGE,
        "连接池占用率 = checked_out / (pool_size + max_overflow)；直读池属性，不解析 status() 文本",
    ),
    MetricSpec("db.pool.checked_out", "个", SHAPE_GAUGE, "连接池已借出连接数"),
    MetricSpec("redis.available", "0/1", SHAPE_GAUGE, "Redis **真实 PING** 结果（1s 超时）"),
    # ---- LLM ----
    MetricSpec(
        "llm.call.count",
        "次/桶",
        SHAPE_SUM,
        "LLM 尝试次数（每次尝试一个 span，重试亦计入）",
        labels_hint="model",
    ),
    MetricSpec("llm.error.count", "次/桶", SHAPE_SUM, "LLM 失败尝试数（error_rate 的分子）"),
    MetricSpec(
        "llm.error_rate",
        "0-1",
        SHAPE_AVG,
        "LLM 失败率（**桶内** 失败/尝试；跨桶为平均值，非精确率）",
    ),
    _p(_LLM_TTFT, "p95"),
    _p(_LLM_DUR, "p95"),
    _LLM_TTFT,
    _LLM_DUR,
    MetricSpec(
        "llm.tokens.prompt", "token/桶", SHAPE_SUM, "prompt token 总量", labels_hint="model"
    ),
    MetricSpec(
        "llm.tokens.completion", "token/桶", SHAPE_SUM, "completion token 总量", labels_hint="model"
    ),
    # ---- ASR / TTS ----
    _p(_ASR_WAIT, "p95"),
    _ASR_WAIT,
    MetricSpec("tts.warm.state", "0/1", SHAPE_GAUGE, "TTS 预热任务状态（running→1，结束→0）"),
    # ---- 采集自监控（docs/50 §9.4）----
    MetricSpec("trace.dropped", "个/桶", SHAPE_SUM, "trace 采集丢弃数（队列满/写库失败/关闭超时）"),
    MetricSpec("trace.written", "个/桶", SHAPE_SUM, "trace 成功落库条数"),
    MetricSpec(
        "ops.alert.eval_errors",
        "次/桶",
        SHAPE_SUM,
        "预警评估自身失败次数（`ops_alert_eval_errors_total` 的桶内增量）",
    ),
)

CATALOG_BY_NAME: dict[str, MetricSpec] = {m.name: m for m in CATALOG}


def spec_of(metric: str) -> MetricSpec | None:
    return CATALOG_BY_NAME.get(metric)


def catalog_list() -> list[dict]:
    """``GET /ops/metrics/catalog`` 的响应体。"""
    return [m.as_dict() for m in CATALOG]


__all__ = [
    "CATALOG",
    "CATALOG_BY_NAME",
    "SHAPE_AVG",
    "SHAPE_DISTRIBUTION",
    "SHAPE_GAUGE",
    "SHAPE_SUM",
    "MetricSpec",
    "catalog_list",
    "spec_of",
]
