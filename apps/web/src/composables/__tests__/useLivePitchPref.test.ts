/**
 * 实时音准线显示开关（useLivePitchPref）测试。
 * 2026-09-22：开关从 LivePitchChart 内部提到面板底部按钮行，偏好改由本 composable 持有。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { useLivePitchPref } from '@/composables/useLivePitchPref'

beforeEach(() => {
  localStorage.removeItem('vv_sing_live_pitch')
})

describe('useLivePitchPref', () => {
  it('默认开（无存储值）', () => {
    expect(useLivePitchPref().on.value).toBe(true)
  })

  it('toggle 翻转并持久化（on / off）', () => {
    const { on, toggle } = useLivePitchPref()
    toggle()
    expect(on.value).toBe(false)
    expect(localStorage.getItem('vv_sing_live_pitch')).toBe('off')
    toggle()
    expect(on.value).toBe(true)
    expect(localStorage.getItem('vv_sing_live_pitch')).toBe('on')
  })

  it('可显式指定目标值（幂等，便于程序化开关）', () => {
    const { on, toggle } = useLivePitchPref()
    toggle(false)
    expect(on.value).toBe(false)
    toggle(false)
    expect(on.value).toBe(false)
    expect(localStorage.getItem('vv_sing_live_pitch')).toBe('off')
  })

  it('存储为 off 时再次使用保持关闭（跨挂载记忆）', () => {
    localStorage.setItem('vv_sing_live_pitch', 'off')
    expect(useLivePitchPref().on.value).toBe(false)
  })
})
