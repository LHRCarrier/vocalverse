import { beforeEach, describe, expect, it, vi } from 'vitest'

import { track } from '@/api/events'

const mocks = vi.hoisted(() => ({ request: vi.fn() }))

vi.mock('@/api/client', () => ({ request: mocks.request }))

beforeEach(() => {
  mocks.request.mockReset()
})

describe('track（埋点 fe-06）', () => {
  it('默认 POST JSON 到 /api/v1/events', async () => {
    mocks.request.mockResolvedValue({ code: 0, message: 'ok', data: null })
    await track('scene_start', { page: '/m/chat', sceneId: 1 })
    expect(mocks.request).toHaveBeenCalledWith(
      '/api/v1/events',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('beacon: true 用 keepalive fetch（页面卸载/切换边界事件可携带 Authorization）', async () => {
    mocks.request.mockResolvedValue({ code: 0, message: 'ok', data: null })
    await track('practice_complete', { page: '/placement', beacon: true })
    expect(mocks.request).toHaveBeenCalledWith(
      '/api/v1/events',
      expect.objectContaining({ keepalive: true }),
    )
  })

  it('普通事件不带 keepalive', async () => {
    mocks.request.mockResolvedValue({ code: 0, message: 'ok', data: null })
    await track('recording_start', { page: '/placement' })
    expect(mocks.request).toHaveBeenCalledWith(
      '/api/v1/events',
      expect.not.objectContaining({ keepalive: true }),
    )
  })

  it('上报失败静默（不抛错，埋点非关键路径）', async () => {
    mocks.request.mockRejectedValue(new Error('net down'))
    await expect(track('fun_action', {})).resolves.toBeUndefined()
  })
})
