import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browseSessionId, EVENT_NAMES, TARGET_TYPES, track } from '@/api/events'

const mocks = vi.hoisted(() => ({ request: vi.fn() }))

vi.mock('@/api/client', () => ({ request: mocks.request }))

beforeEach(() => {
  mocks.request.mockReset()
  sessionStorage.clear()
})

function sentBody(): Record<string, unknown> {
  const call = mocks.request.mock.calls.at(-1)
  const init = call?.[1] as { body?: string }
  return JSON.parse(init.body ?? '{}') as Record<string, unknown>
}

describe('track（埋点 fe-06）', () => {
  it('默认 POST JSON 到 /api/v1/events', async () => {
    mocks.request.mockResolvedValue({ code: 0, message: 'ok', data: null })
    await track('scene_start', { page: '/m/tavern', sceneId: 1 })
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

  /**
   * docs/53 P1 埋点补齐（2026-09-21）：
   * ① 事件 20 类与后端 EventTypes 对齐（原缺读书域 5 类 + 推荐 2 类）；
   * ② target_type 与后端 TargetTypes 同源（修复答辩 defense 被静默丢）；
   * ③ 自动携带 browse_session_id（CTR/跳出率会话键）与 channel（渠道维度）。
   */
  it('事件全集 20 类，且包含本次补齐的读书域/推荐事件', () => {
    expect(EVENT_NAMES).toHaveLength(20)
    for (const name of ['word_lookup', 'vocab_add', 'annotation_add', 'tts_play', 'tts_prepare', 'recommend_impression', 'recommend_click']) {
      expect(EVENT_NAMES).toContain(name)
    }
    expect(TARGET_TYPES).toContain('defense')
  })

  it('自动带 browse_session_id（同一会话稳定）与 channel；透传维度字段', async () => {
    mocks.request.mockResolvedValue({ code: 0, message: 'ok', data: null })
    await track('recommend_click', {
      targetType: 'song',
      targetId: 9,
      songId: 9,
      sessionId: 3,
      recommendGroupId: 'grp-1',
      payload: { rank: 1 },
    })
    const body = sentBody()
    expect(body.event_type).toBe('recommend_click')
    expect(body.browse_session_id).toBe(browseSessionId())
    expect(body.browse_session_id).toBe(sentBody().browse_session_id)
    expect(body.channel).toBe('web') // happy-dom 无 Capacitor/standalone
    expect(body.recommend_group_id).toBe('grp-1')
    expect(body.song_id).toBe(9)
    expect(body.session_id).toBe(3)
    expect(body.target_type).toBe('song')
    expect(body.payload).toEqual({ rank: 1 })
  })
})
