import { describe, expect, it, vi } from 'vitest'

import {
  createStreamFollow,
  distanceFromBottom,
  isNearBottom,
  NEAR_BOTTOM_PX,
  type ScrollViewport,
} from '@/composables/useTavernScroll'

function viewport(scrollTop: number, scrollHeight = 2000, innerHeight = 844): ScrollViewport {
  return { scrollTop, scrollHeight, innerHeight }
}

describe('useTavernScroll · 流式跟随滚动（docs/57 §3.2）', () => {
  it('distanceFromBottom / isNearBottom：底部距离与阈值判定', () => {
    expect(distanceFromBottom(viewport(1156))).toBe(0)
    expect(distanceFromBottom(viewport(1000))).toBe(156)
    expect(distanceFromBottom(viewport(1300))).toBe(0) // 越界钳 0
    expect(isNearBottom(viewport(1100), 96)).toBe(true)
    expect(isNearBottom(viewport(1000), 96)).toBe(false)
    expect(NEAR_BOTTOM_PX).toBeGreaterThan(0)
  })

  it('贴底时内容增长 → 按节流窗口滚动；窗口内重复增长只滚一次', () => {
    const scroll = vi.fn()
    const follow = createStreamFollow({
      getViewport: () => viewport(1156),
      scrollToBottom: scroll,
      throttleMs: 120,
      now: () => 0,
    })
    expect(follow.engaged).toBe(true)

    expect(follow.onContentGrow(0)).toBe(true)
    expect(follow.onContentGrow(50)).toBe(false) // 节流窗口内
    expect(follow.onContentGrow(120)).toBe(true)
    expect(scroll).toHaveBeenCalledTimes(2)
    expect(scroll).toHaveBeenCalledWith(false)
  })

  it('用户上滑离底 → 暂停跟随；reengage（新用户动作）后恢复', () => {
    let top = 1156
    const scroll = vi.fn()
    const follow = createStreamFollow({
      getViewport: () => viewport(top),
      scrollToBottom: scroll,
      throttleMs: 0,
      now: () => 0,
    })

    top = 900 // 距底 256px → 上滑
    expect(follow.onUserScroll()).toBe(false)
    expect(follow.engaged).toBe(false)
    expect(follow.onContentGrow(1000)).toBe(false)
    expect(scroll).not.toHaveBeenCalled()

    follow.reengage()
    expect(follow.engaged).toBe(true)
    expect(follow.onContentGrow(2000)).toBe(true)
    expect(scroll).toHaveBeenCalledTimes(1)
  })

  it('滚回底部附近自动恢复跟随（无需用户动作）', () => {
    let top = 500
    const scroll = vi.fn()
    const follow = createStreamFollow({
      getViewport: () => viewport(top),
      scrollToBottom: scroll,
      throttleMs: 0,
      now: () => 0,
    })
    follow.onUserScroll()
    expect(follow.engaged).toBe(false)

    top = 1150 // 距底 6px
    expect(follow.onUserScroll()).toBe(true)
    expect(follow.onContentGrow(100)).toBe(true)
    expect(scroll).toHaveBeenCalledTimes(1)
  })

  it('turn_end 兜底：即使已暂停也保证滚一次并重新吸附', () => {
    const scroll = vi.fn()
    const follow = createStreamFollow({
      getViewport: () => viewport(200),
      scrollToBottom: scroll,
      throttleMs: 120,
      now: () => 0,
    })
    follow.onUserScroll()
    expect(follow.engaged).toBe(false)

    follow.onTurnEnd()
    expect(scroll).toHaveBeenCalledTimes(1)
    expect(follow.engaged).toBe(true)
  })
})
