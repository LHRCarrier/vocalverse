import { describe, expect, it } from 'vitest'

import { ApiError, readyz } from './client'

describe('request envelope', () => {
  it('throws ApiError when code != 0', async () => {
    const originalFetch = globalThis.fetch
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ code: 50001, message: 'upstream timeout', data: null }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })) as typeof fetch

    try {
      await expect(readyz()).rejects.toThrow(ApiError)
    } finally {
      globalThis.fetch = originalFetch
    }
  })

  it('throws ApiError with friendly message when body is empty (backend unreachable)', async () => {
    // 修复前：resp.json() 抛 SyntaxError「Unexpected end of JSON input」（登录页曾直接展示）；
    // 修复后：ApiError 且带「服务不可达」提示 + 目标路径，便于定位是哪个后端没起。
    const originalFetch = globalThis.fetch
    globalThis.fetch = (async () => new Response('', { status: 500 })) as typeof fetch

    try {
      await expect(readyz()).rejects.toThrow(ApiError)
      await expect(readyz()).rejects.toThrow(/服务不可达/)
    } finally {
      globalThis.fetch = originalFetch
    }
  })

  it('parses success envelope', async () => {
    const originalFetch = globalThis.fetch
    globalThis.fetch = (async () =>
      new Response(
        JSON.stringify({
          code: 0,
          message: 'ok',
          data: { status: 'ready', app_env: 'test', asr: 'small', tts: 'edge' },
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      )) as typeof fetch

    try {
      const r = await readyz()
      expect(r.data.status).toBe('ready')
    } finally {
      globalThis.fetch = originalFetch
    }
  })
})
