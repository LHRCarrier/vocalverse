import { opsHttp } from './client'
import type {
  AlertEvent,
  AlertRule,
  AlertRuleList,
  AlertRuleWrite,
  ConcurrencyView,
  DependencyProbe,
  LibraryBookRow,
  LibraryChapterRow,
  MediaAssetRow,
  MetricCatalogItem,
  MetricQuery,
  MetricQueryResult,
  OpsOverview,
  PageView,
  PublishStatus,
  PurgeRequest,
  PurgeResult,
  TraceContentResult,
  TraceDetail,
  TraceRow,
  TraceStats,
} from './types'

/**
 * Python 侧控制台端点（docs/50 §10.3）。
 * 路径同样在 `/api/v1/console/**` 下——**子路径与 Java 侧不重叠**
 * （Java = auth|admins|roles|permissions|audit-logs|moderation|content；Python = ops|library）。
 * `opsHttp` 的 base 是 `/api/v1`（复用既有网关路由，nginx 零改动）。
 *
 * ⚠️ 所有 query 参数名与返回类型都按 `services/python/app/console/api/routes/ops.py` /
 * `library.py` 的签名逐字对齐（snake_case），不做前端风格的改写：
 * 例如 `labels_key`（ops.py:186）、`session_id`、`min_duration_ms`、`rule_code`。
 */
const P = '/console'

export const opsApi = {
  // ── 总览 / 依赖 / 并发额度 ──────────────────────────────────────────────
  overview: () => opsHttp.get<OpsOverview>(`${P}/ops/overview`),

  /** 返回 `{status, checked_at, items[], app_env, asr, tts}` 对象，**不是数组**（ops.py:115-121） */
  services: () => opsHttp.get<DependencyProbe>(`${P}/ops/services`),

  concurrency: () => opsHttp.get<ConcurrencyView>(`${P}/ops/concurrency`),

  // ── 指标 ────────────────────────────────────────────────────────────────
  metricCatalog: () => opsHttp.get<MetricCatalogItem[]>(`${P}/ops/metrics/catalog`),

  metrics: (query: MetricQuery) =>
    opsHttp.get<MetricQueryResult>(`${P}/ops/metrics`, {
      query: {
        // 数组会被 client 展开成重复的 `metric=`（ops.py:182 的 list[str]）
        metric: query.metric,
        from: query.from,
        to: query.to,
        step: query.step,
        labels_key: query.labels_key,
      },
    }),

  // ── 预警 ────────────────────────────────────────────────────────────────
  listRules: () => opsHttp.get<AlertRuleList>(`${P}/ops/alerts/rules`),

  createRule: (body: AlertRuleWrite) => opsHttp.post<AlertRule>(`${P}/ops/alerts/rules`, body),

  /**
   * 改阈值/窗口/冷却/严重级/启停；`enabled=false` 即"停用"。
   * 这里**不提供 deleteRule**：后端 DELETE 一律 409/46010（ops.py:331-346），
   * 历史事件必须活过规则，删除这条路是刻意封死的——控制台只用 PATCH 停用。
   */
  updateRule: (id: number, body: Partial<AlertRuleWrite>) =>
    opsHttp.patch<AlertRule>(`${P}/ops/alerts/rules/${id}`, body),

  listEvents: (query: {
    page?: number
    page_size?: number
    status?: string
    severity?: string
    /** 查询参数是 `rule_code`（ops.py:353），不是 ruleCode */
    rule_code?: string
    from?: string
    to?: string
  }) => opsHttp.get<PageView<AlertEvent>>(`${P}/ops/alerts/events`, { query }),

  /** 认领：无请求体（ops.py:398-404），`acked_by` 存管理员用户名快照 */
  ackEvent: (id: number) => opsHttp.post<AlertEvent>(`${P}/ops/alerts/events/${id}/ack`),

  /** 处置完成（→ resolved）；note 落 `resolved_note`（ops.py:407-415） */
  resolveEvent: (id: number, note?: string) =>
    opsHttp.post<AlertEvent>(`${P}/ops/alerts/events/${id}/resolve`, { note }),

  // ── LLM trace ───────────────────────────────────────────────────────────
  /** 窗口汇总；**没有 kind 参数**（ops.py:528-533 只收 from/to） */
  traceStats: (query: { from?: string; to?: string }) =>
    opsHttp.get<TraceStats>(`${P}/ops/traces/stats`, { query }),

  listTraces: (query: {
    page?: number
    page_size?: number
    kind?: string
    status?: string
    model?: string
    /** `session_id`（ops.py:583） */
    session_id?: string
    from?: string
    to?: string
    /** `min_duration_ms`（ops.py:586） */
    min_duration_ms?: number
  }) => opsHttp.get<PageView<TraceRow>>(`${P}/ops/traces`, { query }),

  getTrace: (traceId: string, spanLimit?: number) =>
    opsHttp.get<TraceDetail>(`${P}/ops/traces/${traceId}`, {
      query: { span_limit: spanLimit },
    }),

  traceContents: (traceId: string) =>
    opsHttp.get<TraceContentResult>(`${P}/ops/traces/${traceId}/contents`),

  purge: (body: PurgeRequest) => opsHttp.post<PurgeResult>(`${P}/ops/maintenance/purge`, body),

  // ── 运营：书籍与媒体（Python 写方，`console/library/**`） ───────────────
  listBooks: (query: {
    page?: number
    page_size?: number
    q?: string
    status?: string
    level?: string
  }) => opsHttp.get<PageView<LibraryBookRow>>(`${P}/library/books`, { query }),

  publishBook: (id: number, status: PublishStatus) =>
    opsHttp.post<LibraryBookRow>(`${P}/library/books/${id}/publish`, { status }),

  /** 章节清单（不分页，返回 `{items}`；library.py:154-174） */
  listChapters: (bookId: number) =>
    opsHttp.get<{ items: LibraryChapterRow[] }>(`${P}/library/books/${bookId}/chapters`),

  /** 章节上/下架返回**章节**行，不是 null（library.py:180-200） */
  publishChapter: (id: number, status: PublishStatus) =>
    opsHttp.post<LibraryChapterRow>(`${P}/library/chapters/${id}/publish`, { status }),

  listMedia: (query: {
    page?: number
    page_size?: number
    kind?: string
    status?: string
    owner_id?: number
  }) => opsHttp.get<PageView<MediaAssetRow>>(`${P}/library/media`, { query }),

  /** 隐藏/恢复：`hidden=true` → hidden，`false` → ready；deleted 是用户意志，动不了 */
  hideMedia: (publicId: string, hidden: boolean) =>
    opsHttp.post<MediaAssetRow>(`${P}/library/media/${publicId}/hide`, { hidden }),
}
