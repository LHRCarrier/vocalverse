/**
 * 跟唱面板顶栏组件测试（components/sing/SingSheetHead，2026-09-22 深色录唱页重做）。
 *
 * 参考图顶栏 = 返回 + 橙色评级条（A 2.63）+ 模式 chip；我们**不新造指标**：
 * 评级由现有实时分（近 5 秒在调率×出声率）经 `lib/sing-grade.ts` 映射，分数段与
 * `scoreColorOf` 的 85/60 阈值同源。本用例锁：
 * ① 等级字母与进度（scaleX，不是 width）随实时分变；② 无分数 → 占位「—」且条为空；
 * ③ 模式 chip 文案与暂停态配色；④ 录音进度线（3 分钟上限）；⑤ 关闭事件。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SingSheetHead from '@/components/sing/SingSheetHead.vue'

const props = {
  title: 'Twinkle Twinkle Little Star',
  score: null as number | null,
  modeText: '待开始',
  recording: false,
  paused: false,
  elapsedMs: null as number | null,
  maxMs: 180_000,
}

const mountHead = (over: Partial<typeof props> = {}) =>
  mount(SingSheetHead, { props: { ...props, ...over } })

describe('SingSheetHead · 评级条', () => {
  it('无实时分 → 字母占位「—」，进度条 scaleX(0)', () => {
    const w = mountHead()
    expect(w.find('.m-sing-grade__letter').text()).toBe('—')
    expect(w.find('.m-sing-grade__num').text()).toBe('—')
    const style = w.find('.m-sing-grade__fill').attributes('style') ?? ''
    expect(style).toContain('scaleX(0)')
  })

  it('实时分 → 等级字母 + 进度 + 数字；只动 transform（不动 width）', () => {
    const w = mountHead({ score: 88 })
    expect(w.find('.m-sing-grade__letter').text()).toBe('A') // 85~94 = A
    expect(w.find('.m-sing-grade__num').text()).toBe('88')
    const style = w.find('.m-sing-grade__fill').attributes('style') ?? ''
    expect(style).toContain('scaleX(0.88)')
    expect(style).not.toContain('width:')
  })

  it('评级条带练习参考口径的无障碍名（不宣称是最终分）', () => {
    const label = mountHead({ score: 72 }).find('.m-sing-grade').attributes('aria-label') ?? ''
    expect(label).toContain('实时分')
    expect(label).toContain('练习参考')
    expect(label).toContain('离线')
  })
})

describe('SingSheetHead · 模式 chip 与录音进度线', () => {
  it('模式文案随 props 变；暂停态加 is-paused', () => {
    expect(mountHead({ modeText: '跟唱中', recording: true }).find('.m-sing-top__mode').text()).toBe('跟唱中')
    const paused = mountHead({ modeText: '暂停中', recording: true, paused: true }).find('.m-sing-top__mode')
    expect(paused.text()).toBe('暂停中')
    expect(paused.classes()).toContain('is-paused')
  })

  it('未录音 → 无进度线；录音中 → scaleX = 已录/上限', () => {
    expect(mountHead().find('.m-sing-top__recbar').exists()).toBe(false)
    const w = mountHead({ recording: true, elapsedMs: 45_000 })
    const style = w.find('.m-sing-top__recbar').attributes('style') ?? ''
    expect(style).toContain('scaleX(0.25)')
    expect(style).not.toContain('width:')
  })

  it('关闭钮可点 → 抛 close；aria-label 保持「关闭」（既有测试与联调脚本据此定位）', async () => {
    const w = mountHead()
    await w.get('button[aria-label="关闭"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })
})
