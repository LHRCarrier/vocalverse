// @vitest-environment happy-dom
/**
 * 运维域**契约测试**：把"控制台发什么参数、读什么字段"钉在
 * `services/python/app/console/api/routes/ops.py` 的真实签名上。
 *
 * 为什么值得单测：v1 的 DTO 与请求参数都是照设计文档臆造的（camelCase + 不同嵌套），
 * 而 envelope 的 `data` 非空 → 页面**不报错、只显示 `—`**，手工点页面很难发现。
 * 这些断言在修复前全部失败（例如请求里出现 `labelsKey`、`sessionId`，
 * 或把 `/ops/services` 的对象响应当数组用）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { opsApi } from '@/api'

interface Captured {
  url: string
  method: string
  body: unknown
}

const captured: Captured[] = []

/** 把 fetch 换成"回固定 envelope + 记录请求"的桩 */
function stub(payload: unknown): void {
  captured.length = 0
  vi.stubGlobal('fetch', (url: string, init: RequestInit = {}) => {
    captured.push({ url, method: init.method ?? 'GET', body: init.body })
    return Promise.resolve({
      status: 200,
      ok: true,
      headers: { get: () => null },
      json: async () => ({ code: 0, message: 'ok', data: payload }),
    } as unknown as Response)
  })
}

function query(url: string): URLSearchParams {
  const at = url.indexOf('?')
  return new URLSearchParams(at < 0 ? '' : url.slice(at + 1))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('opsApi 契约（权威：console/api/routes/ops.py）', () => {
  it('metrics：重复 metric + labels_key（不是 labelsKey）', async () => {
    stub({ from: 'f', to: 't', step: 60, series: {}, rows_read: 0, catalog: {} })
    await opsApi.metrics({
      metric: ['llm.call.count', 'llm.duration_ms.p95'],
      from: '2026-01-01T00:00:00Z',
      to: '2026-01-02T00:00:00Z',
      step: 60,
      labels_key: 'model=deepseek-chat',
    })
    expect(captured[0].url).toContain('/console/ops/metrics')
    const qs = query(captured[0].url)
    expect(qs.getAll('metric')).toEqual(['llm.call.count', 'llm.duration_ms.p95'])
    expect(qs.get('labels_key')).toBe('model=deepseek-chat')
    expect(qs.has('labelsKey')).toBe(false)
  })

  it('listTraces：session_id / min_duration_ms（不是 sessionId / minDurationMs）', async () => {
    stub({ items: [], total: 0, page: 1, page_size: 20 })
    await opsApi.listTraces({ session_id: 's-1', min_duration_ms: 800, kind: 'turn' })
    const qs = query(captured[0].url)
    expect(qs.get('session_id')).toBe('s-1')
    expect(qs.get('min_duration_ms')).toBe('800')
    expect(qs.has('sessionId')).toBe(false)
    expect(qs.has('minDurationMs')).toBe(false)
  })

  it('listEvents：rule_code 过滤 + 分页参数名 page_size', async () => {
    stub({ items: [], total: 0, page: 1, page_size: 20 })
    await opsApi.listEvents({ rule_code: 'http_p95_slow', page: 2, page_size: 20 })
    const qs = query(captured[0].url)
    expect(qs.get('rule_code')).toBe('http_p95_slow')
    expect(qs.get('page_size')).toBe('20')
  })

  it('ack：POST 且不带请求体（后端不收 note，acked_by 由服务端写快照）', async () => {
    stub({ id: 1 })
    await opsApi.ackEvent(1)
    expect(captured[0].url).toContain('/console/ops/alerts/events/1/ack')
    expect(captured[0].method).toBe('POST')
    expect(captured[0].body).toBeUndefined()
  })

  it('purge：请求体字段是 targets / dry_run（不是 target / olderThanHours）', async () => {
    stub({ dry_run: true, deleted: {}, policy: {} })
    await opsApi.purge({ targets: ['traces', 'contents'], dry_run: true })
    expect(captured[0].url).toContain('/console/ops/maintenance/purge')
    expect(captured[0].body).toBe(JSON.stringify({ targets: ['traces', 'contents'], dry_run: true }))
  })

  it('services：返回对象（带 items），不是数组', async () => {
    stub({
      status: 'ready',
      checked_at: 'c',
      items: [{ name: 'database', ok: true, required: true, detail: 'ok', latency_ms: 1 }],
      app_env: 'test',
      asr: 'a',
      tts: 't',
    })
    const probe = await opsApi.services()
    expect(Array.isArray(probe)).toBe(false)
    expect(probe.items[0].latency_ms).toBe(1)
  })

  it('overview：响应键原样保留 snake_case（不做 camelCase 映射）', async () => {
    stub({
      version: '0.1',
      app_env: 'prod',
      uptime_s: 12,
      dependencies: {
        status: 'ready',
        checked_at: 'c',
        items: [],
        app_env: 'prod',
        asr: 'a',
        tts: 't',
      },
      concurrency: {
        'http.inflight': 0,
        'asr.limit': 1,
        'ise.limit': 1,
        'reading_tts.limit': 1,
        'db.pool.capacity': null,
        note: 'n',
      },
      collector: { enabled: true, interval_s: 60, inflight_gauges: {} },
      self_monitoring: {
        trace_dropped_total: 1,
        trace_written_total: 5,
        trace_buffered: 0,
        trace_write_errors_total: 0,
        metric_collector_errors_total: 0,
        ops_alert_eval_errors_total: 0,
      },
      flags: { llm_trace_enabled: true, llm_trace_content_capture: false },
    })
    const data = await opsApi.overview()
    expect(data.uptime_s).toBe(12)
    expect(data.self_monitoring.trace_written_total).toBe(5)
    expect(data.concurrency['db.pool.capacity']).toBeNull()
  })

  it('library：书籍分页参数与 media 的隐藏请求体', async () => {
    stub({ items: [], total: 0, page: 1, page_size: 20 })
    await opsApi.listBooks({ page: 1, page_size: 20, q: 'alice', status: 'published' })
    expect(captured[0].url).toContain('/console/library/books')

    stub({ id: 'p1', public_id: 'p1', owner_id: 1, kind: 'image', mime_type: 'image/png', size_bytes: 9, status: 'hidden', url: '/api/v1/media/p1', created_at: null })
    const media = await opsApi.hideMedia('p1', true)
    expect(captured[0].url).toContain('/console/library/media/p1/hide')
    expect(captured[0].body).toBe(JSON.stringify({ hidden: true }))
    expect(media.status).toBe('hidden')
  })
})
