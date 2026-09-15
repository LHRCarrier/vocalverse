/**
 * 运维域 DTO（Python 侧 `/api/v1/console/ops/**`，docs/50 §7 §8 §10.3）。
 *
 * ⚠️ 字段名与 Python 出参**逐字一致**（snake_case）——不做 camelCase 改写。
 * 权威来源（改本文件前先读它们）：
 * - `services/python/app/console/api/routes/ops.py`（每个端点的 data 构造）
 * - `app/console/ops/{probe,query,metrics,catalog,alerts}.py`、`app/console/trace/sink.py`
 *
 * 历史教训：v1 的 DTO 是照设计文档臆造的 camelCase（`probes` / `selfMonitor` /
 * `points[].avg` / `service` / `startedAt` …），实测与 Python 出参无一对应，
 * 因为 envelope 的 `data` 本身非空，页面不会报错、只会静默退化成 `—`。
 */

// ── 依赖探测（probe.py:26-101，与 /readyz 同一函数） ───────────────────────

/** `overview.dependencies` 与 `GET /ops/services` 的 data（probe.py:41-49） */
export interface DependencyProbe {
  /** 总体判定（probe.py:33-40）：必需项失败 → not_ready；仅可选项失败 → degraded */
  status: 'ready' | 'degraded' | 'not_ready'
  checked_at: string
  items: DependencyItem[]
  /** 兼容既有 /readyz 响应体的三个字段（probe.py:45-48） */
  app_env: string
  asr: string
  tts: string
}

/** 单条依赖（probe.py:60-66 / 86-92） */
export interface DependencyItem {
  name: string
  ok: boolean
  /** true = 失败即整体 not_ready；false = 可降级（redis 未配置时也算 ok=true） */
  required: boolean
  detail: string
  latency_ms: number
}

// ── 并发额度（ops.py:132-148） ────────────────────────────────────────────

/**
 * `GET /ops/concurrency` 与 `overview.concurrency`。
 * 键名就是后端字面量（含点号）；额度是**进程内常量**，只有 `http.inflight` 是在途 gauge。
 */
export interface ConcurrencyView {
  'http.inflight': number
  'asr.limit': number
  'ise.limit': number
  'reading_tts.limit': number
  /** 读连接池属性失败时为 null（ops.py:151-158） */
  'db.pool.capacity': number | null
  /** 后端自带的口径说明（原样展示，不要在前端另写一套） */
  note: string
}

// ── 指标目录与查询（catalog.py / query.py / ops.py:171-261） ───────────────

/** 跨桶聚合口径（catalog.py:18-21）：sum 可加 / avg 近似 / gauge 取峰 / distribution 直方图 */
export type MetricShape = 'sum' | 'avg' | 'gauge' | 'distribution'

/** 目录项（catalog.py:35-45；`GET /ops/metrics/catalog` 的元素） */
export interface MetricCatalogItem {
  name: string
  unit: string
  shape: MetricShape
  description: string
  /** 标签提示（如 route/model）；无标签为 null */
  labels: string | null
  /** 分位指标的直方图真源（基础指标名）；非分位指标为 null */
  percentile_of: string | null
  /** 能否对时间窗求分位数（只有 distribution 或其 pNN 为 true） */
  percentile_supported: boolean
}

/** 一个 step 的聚合点（query.py:246-253 / 300-307） */
export interface MetricPoint {
  t: string
  /** 分位指标该 step 内无直方图样本时为 **null**（不是 0：0 会被读成"延迟为 0"） */
  value: number | null
  /** 该点覆盖的观测数（samples），不同于样本桶数 */
  samples: number
  /** 该点的聚合口径文字（如 `max(value_max) over step`）——图表副标题直接用 */
  basis: string
}

/** `GET /ops/metrics` 的 data（ops.py:252-261） */
export interface MetricQueryResult {
  from: string
  to: string
  step: number
  /** metric 名 → 点序列；请求里每个 metric 都有键（无数据时为空数组） */
  series: Record<string, MetricPoint[]>
  /** 本次实际扫描的样本行数（成本闸门 MAX_ROWS_FETCH=20000 的显示口径） */
  rows_read: number
  /** metric 名 → 目录项（未知指标才会是 null，ops.py:259） */
  catalog: Record<string, MetricCatalogItem | null>
}

export interface MetricQuery {
  /** 可重复查询参数 `metric`（ops.py:182），单请求上限 8 个 */
  metric: string[]
  from: string
  to: string
  /** 秒；1..86400，且 (to-from)/step ≤ 5000 点 */
  step: number
  /** 查询参数名是 `labels_key`（ops.py:186），不是 labelsKey */
  labels_key?: string
}

// ── 预警（ops.py:264-521 / alerts.py） ───────────────────────────────────

export type AlertComparator = 'gt' | 'gte' | 'lt' | 'lte'
export type AlertSeverity = 'info' | 'warn' | 'critical'
export type AlertEventStatus = 'firing' | 'acknowledged' | 'resolved'

/** 规则行（ops.py:443-460 `_rule_view`） */
export interface AlertRule {
  id: number
  code: string
  name: string
  service: 'python' | 'java'
  metric: string
  comparator: AlertComparator
  threshold: number
  /** 评估窗口（秒），不小于 60（桶宽） */
  window_s: number
  /** 窗口内最少**样本桶数**，不足不判定（防冷启动误报） */
  min_samples: number
  severity: AlertSeverity
  enabled: boolean
  cooldown_s: number
  /** jsonb 列（模型 server_default 为 `[]`），后端原样回传、不做形状校验 */
  notify_channels: string[]
  description: string | null
  updated_at: string | null
}

/** `GET /ops/alerts/rules` 返回 `{items}` 而不是裸数组（ops.py:278） */
export interface AlertRuleList {
  items: AlertRule[]
}

/** 规则写入口；前 6 个字段是 POST 的必填项（ops.py:503-505） */
export interface AlertRuleWrite {
  code: string
  name: string
  metric: string
  comparator: AlertComparator
  threshold: number
  severity: AlertSeverity
  service?: 'python' | 'java'
  /** 小于 60 会被 46007 拒绝（ops.py:519-520） */
  window_s?: number
  min_samples?: number
  enabled?: boolean
  cooldown_s?: number
  notify_channels?: string[]
  description?: string
}

/** 事件行（ops.py:463-481 `_event_view`） */
export interface AlertEvent {
  id: number
  rule_id: number
  /** 规则 code 快照（规则被停用后事件仍可读） */
  rule_code: string
  severity: AlertSeverity
  status: AlertEventStatus
  value: number
  threshold: number
  window_s: number
  message: string
  /** 触发时的口径快照 `{metric, basis, samples, window_start}`（alerts.py:231-236） */
  detail: Record<string, unknown> | null
  dedup_key: string
  fired_at: string | null
  acked_at: string | null
  /** 管理员**用户名快照**（跨服务不加 FK），不是 admin id */
  acked_by: string | null
  resolved_at: string | null
  resolved_note: string | null
}

// ── LLM trace（ops.py:524-771） ──────────────────────────────────────────

export type TraceStatus = 'ok' | 'error' | 'aborted' | 'incomplete'

/** trace 行（ops.py:725-747 `_trace_view`） */
export interface TraceRow {
  trace_id: string
  request_id: string | null
  /** turn|free_chat|defense|summary|conclude|reading_tts|score|meta（值集由采集侧约束） */
  kind: string
  status: TraceStatus
  session_id: string | null
  user_id: number | null
  model: string | null
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  ttft_ms: number | null
  span_count: number
  llm_call_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  error_code: string | null
  error_message: string | null
  content_captured: boolean
  /** 采样率/prompt 模板 id/git sha 等（jsonb） */
  attrs: Record<string, unknown>
}

/** span 行（ops.py:750-771 `_span_view`） */
export interface TraceSpan {
  span_id: string
  parent_span_id: string | null
  /** ENTRY|AGENT|STEP|LLM|TOOL|ASR|TTS|SCORE|RETRIEVE */
  name: string
  span_kind: 'internal' | 'client' | 'server'
  seq: number
  started_at: string | null
  ended_at: string | null
  duration_ms: number | null
  ttft_ms: number | null
  status: TraceStatus
  retry_index: number
  model: string | null
  prompt_tokens: number | null
  completion_tokens: number | null
  finish_reason: string | null
  tool_name: string | null
  error_code: string | null
  error_message: string | null
  attrs: Record<string, unknown>
}

/**
 * `GET /ops/traces/{trace_id}`（ops.py:660-665）。
 * 注意**没有** originAt：瀑布图原点只能用 `trace.started_at`（trace 起点=根 span 起点）。
 */
export interface TraceDetail {
  trace: TraceRow
  spans: TraceSpan[]
  /** span 数超过 span_limit（默认/上限 500）时为 true（ops.py:658） */
  truncated: boolean
  span_limit: number
}

/**
 * `GET /ops/traces/stats`（ops.py:562-573 的窗口汇总 + :772-789 的聚合块）。
 *
 * ⚠️ 修订记录（2026-09-10）：本接口**原先只有窗口汇总**，控制台的两张图（调用量/错误率趋势、
 * 按模型调用量）因此**没有数据源、被迫删掉**。处置不是接受这个损失，而是**回派后端扩接口**
 * ——现在 `trend` / `by_model` / `by_status` 已提供（见 `docs/50 §10.1.1` 第 3 条：
 * 「删掉一个功能」与「加一个后端聚合」是两种完全不同的处置）。
 */
export interface TraceStats {
  from: string
  to: string
  trace_count: number
  error_count: number
  /** 失败 trace / 总 trace（总数为 0 时 0.0） */
  error_rate: number
  llm_call_count: number
  prompt_tokens: number
  completion_tokens: number
  /** 窗口内无直方图样本时为 null（window_value 返回 None，绝不回退成假数字） */
  duration_ms_p95: number | null
  /** p95 的口径说明（如 `histogram_merge(llm.duration_ms)`） */
  duration_ms_p95_basis: string | null
  /**
   * 按 **UTC 日**分桶的趋势，**覆盖整个窗口且缺失日补 0**（图要连续才读得出趋势）。
   * 每日 `duration_ms_p95` 由该日直方图**合并后插值**；**无样本日为 `null`**——
   * 画图时必须留缺口，不能画 0（0 会被读成"当天飞快"，是假信号）。
   */
  trend: TraceTrendPoint[]
  /**
   * 趋势的口径与降级说明（`ops.py:773-785`）。
   * `p95_available=false` 表示直方图行数超预算 → 该次响应 p95 **全部为 null**（宁缺勿错）；
   * 界面必须据此说明"为什么没有时长曲线"，而不是显示一张空图。
   */
  trend_meta: TraceTrendMeta
  /** 按主模型聚合，`trace_count` 降序；`model` 为 `(unknown)` 表示 trace 未带主模型 */
  by_model: TraceByModel[]
  /** `ok|error|aborted|incomplete` **四条恒在**（计数为 0 也返回，便于画固定图例） */
  by_status: { status: TraceStatus; count: number }[]
}

export interface TraceTrendPoint {
  date: string
  trace_count: number
  error_count: number
  llm_call_count: number
  /** `null` = 该日无直方图样本（图上留缺口，不画 0） */
  duration_ms_p95: number | null
}

export interface TraceTrendMeta {
  bucket: string
  timezone: string
  buckets: number
  p95_metric: string
  /** false → p95 全为 null（超预算的诚实降级，不等于"没有慢调用"） */
  p95_available: boolean
  rows_budget: number
  note: string
}

export interface TraceByModel {
  model: string
  trace_count: number
  llm_call_count: number
  prompt_tokens: number
  completion_tokens: number
}

/** 内容行（ops.py:706-718） */
export interface TraceContentRow {
  span_id: string
  direction: 'input' | 'output'
  seq: number
  role: string | null
  content: string
  content_chars: number
  truncated: boolean
  redacted: boolean
}

/** `GET /ops/traces/{trace_id}/contents`（ops.py:702-720；每次读取都写审计） */
export interface TraceContentResult {
  captured: boolean
  /** 当前服务端内容捕获开关（区分"没采"与"采了但为空"） */
  content_capture_enabled: boolean
  /** 未捕获原因（来自 trace.attrs.content_capture_reason），无则 null */
  deny_reason: string | null
  items: TraceContentRow[]
  total: number
}

// ── 维护：保留期清理（ops.py:774-827） ───────────────────────────────────

export interface PurgeRequest {
  /** 缺省 = 三者全清（ops.py:786） */
  targets?: ('traces' | 'contents' | 'metrics')[]
  dry_run?: boolean
}

/** `POST /ops/maintenance/purge` 的 data（ops.py:811-819） */
export interface PurgeResult {
  dry_run: boolean
  /** 只含请求过的 target 对应的键；traces 会同时给出 spans（ops.py:800-802） */
  deleted: {
    traces?: number
    spans?: number
    contents?: number
    metrics?: number
  }
  policy: {
    llm_trace_retention_days: number
    llm_span_content_retention_hours: number
    ops_metric_retention_days: number
  }
}

// ── 总览（ops.py:71-112） ────────────────────────────────────────────────

export interface OpsOverview {
  /** `app.__version__` */
  version: string
  app_env: string
  /** 进程内起点计的秒数（ops.py:91），不是进程启动的墙钟时间 */
  uptime_s: number
  dependencies: DependencyProbe
  concurrency: ConcurrencyView
  collector: {
    enabled: boolean
    interval_s: number
    /** `metric|labels_key` → 当前值（metrics.py:184-187） */
    inflight_gauges: Record<string, number>
  }
  /** 采集自监控（docs/50 §9.4）：看板自己也要被观测 */
  self_monitoring: {
    trace_dropped_total: number
    trace_written_total: number
    trace_buffered: number
    trace_write_errors_total: number
    metric_collector_errors_total: number
    ops_alert_eval_errors_total: number
  }
  flags: {
    llm_trace_enabled: boolean
    llm_trace_content_capture: boolean
  }
}
