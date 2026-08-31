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
