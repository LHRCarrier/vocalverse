/**
 * 音准引导条组件测试（components/LivePitchChart，2026-09-22 深色录唱页重做）。
 *
 * 历史口径保留：空态挂载必须安全（`active=false` 不触 AudioContext/不启动 rAF 循环）——
 * 回归点：组件误在挂载期 start 检测器会导致 happy-dom/真机无 AudioContext 崩溃。
 *
 * 新口径（参考图）：
 * - 画布**常驻**（引导条是面板结构的一部分，不是可选显示）；`enabled`（「曲线」开关）**只管用户轨迹**；
 * - `score` 事件把实时分上报给顶栏评级条（组件内不再自绘读数）；
 * - `paused` → 走针冻结 + 整带降亮（`is-paused` 类）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import LivePitchChart from '@/components/LivePitchChart.vue'
import type { SongDetail } from '@/api/sing'

const detail: SongDetail = {
  id: 1,
  title: 'Twinkle',
  level: 1,
  pitch_ref_status: 'ready',
  expected_lines: 1,
  favorited: false,
  duration_s: 30,
  lines: [
    {
      seq: 1,
      start_ms: 0,
      end_ms: 1000,
      text: 'Twinkle twinkle',
      pitch_ref: { f0s: [440, 440, 440, 440], midi: [69, 69, 69, 69], notes: ['A4', 'A4', 'A4', 'A4'] },
    },
  ],
}

describe('LivePitchChart · 引导条挂载', () => {
  it('空态挂载安全（active=false 不启动检测），画布常驻、读数占位', () => {
    const w = mount(LivePitchChart, { props: { detail, stream: null, active: false } })
    expect(w.find('.sing-lane__canvas').exists()).toBe(true)
    expect(w.find('.sing-lane__read').text()).toBe('—')
    expect(w.classes()).not.toContain('is-off')
  })

  it('「曲线」开关关闭 → is-off（用户轨迹不画），但画布与检测口径不变', () => {
    const off = mount(LivePitchChart, { props: { detail, stream: null, active: false, enabled: false } })
    expect(off.classes()).toContain('is-off')
    expect(off.find('.sing-lane__canvas').exists()).toBe(true)
    expect(off.find('.sing-lane__note').text()).toContain('已关')
  })

  it('暂停 → is-paused 且标注「已暂停」（走针冻结由渲染层按 props 处理）', () => {
    const w = mount(LivePitchChart, { props: { detail, stream: null, active: true, paused: true } })
    expect(w.classes()).toContain('is-paused')
    expect(w.find('.sing-lane__note').text()).toBe('已暂停')
  })

  it('动效档 off（data-motion=off）空态挂载安全', () => {
    document.documentElement.dataset.motion = 'off'
    try {
      const w = mount(LivePitchChart, { props: { detail, stream: null, active: false } })
      expect(w.find('.sing-lane__read').text()).toBe('—')
    } finally {
      document.documentElement.dataset.motion = 'high'
    }
  })
})
