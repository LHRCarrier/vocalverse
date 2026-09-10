/**
 * LivePitchChart 组件冒烟（docs/06 §9.4 注记 · 实时音准线）：
 * 空态挂载必须安全（active=false 不触 AudioContext/不启动 rAF 循环）——
 * 回归点：组件误在挂载期 start 检测器会导致 happy-dom/真机无 AudioContext 崩溃。
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
  lines: [
    {
      seq: 1,
      start_ms: 0,
      end_ms: 1000,
      text: 'Twinkle twinkle',
      pitch_ref: { f0s: [440, 440, 440, 440] },
    },
  ],
}

describe('LivePitchChart', () => {
  it('空态挂载：开关默认开、读数占位、不启动检测（无 AudioContext 报错）', () => {
    localStorage.removeItem('vv_sing_live_pitch')
    const w = mount(LivePitchChart, { props: { detail, stream: null, active: false } })
    expect((w.find('input').element as HTMLInputElement).checked).toBe(true)
    expect(w.find('.live-pitch__read').text()).toBe('—')
    expect(w.text()).toContain('实时参考线')
    expect(w.text()).toContain('离线分析为准')
  })

  it('开关可关闭并持久化；关闭后再次挂载保持关闭', async () => {
    const w = mount(LivePitchChart, { props: { detail, stream: null, active: false } })
    await w.find('input').setValue(false)
    expect(localStorage.getItem('vv_sing_live_pitch')).toBe('off')
    const w2 = mount(LivePitchChart, { props: { detail, stream: null, active: false } })
    expect((w2.find('input').element as HTMLInputElement).checked).toBe(false)
    expect(w2.classes()).toContain('live-pitch--off')
  })
})
