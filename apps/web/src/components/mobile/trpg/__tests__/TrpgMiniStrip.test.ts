import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TrpgMiniStrip from '@/components/mobile/trpg/TrpgMiniStrip.vue'
import type { TavernQuest } from '@/composables/useTavernQuest'

function quest(partial: Partial<TavernQuest> & { name: string }): TavernQuest {
  return {
    progress: '0/6',
    current: 0,
    segments: 6,
    kind: 'positive',
    stage: null,
    status: 'active',
    full: false,
    reason: null,
    hasClock: true,
    ...partial,
  }
}

describe('TrpgMiniStrip · 常驻迷你状态条（docs/57 §3.2）', () => {
  it('威胁钟优先为「主任务」：名字 + 威胁标签 + 进度 + 分段格；进展用「推进」', () => {
    const wrapper = mount(TrpgMiniStrip, {
      props: {
        quests: [
          quest({ name: '寻找戒指', progress: '3/6', current: 3, segments: 6 }),
          quest({ name: '阴影逼近', kind: 'threat', progress: '2/4', current: 2, segments: 4 }),
        ],
      },
    })
    const text = wrapper.find('.t-mini__quest').text()
    expect(text).toContain('阴影逼近')
    expect(text).toContain('威胁')
    expect(text).toContain('2/4')
    expect(wrapper.find('.t-mini__quest').findAll('.t-mini__pip')).toHaveLength(4)
    expect(wrapper.find('.t-mini__quest').findAll('.t-mini__pip.is-lit')).toHaveLength(2)

    const positive = mount(TrpgMiniStrip, {
      props: { quests: [quest({ name: '寻找戒指', progress: '3/6', current: 3 })] },
    })
    expect(positive.find('.t-mini__quest').text()).toContain('推进')
    expect(positive.find('.t-mini__quest').text()).toContain('寻找戒指')
  })

  it('满格玩家向文案：正向「可收尾」、威胁「已爆发」；已结算任务不进条', () => {
    const positive = mount(TrpgMiniStrip, {
      props: {
        quests: [
          quest({ name: '寻找戒指', progress: '6/6', current: 6, full: true }),
          quest({ name: '旧案', status: 'done', hasClock: false }),
        ],
      },
    })
    expect(positive.find('.t-mini__quest').text()).toContain('可收尾')
    expect(positive.find('.t-mini__quest').text()).not.toContain('旧案')

    const threat = mount(TrpgMiniStrip, {
      props: {
        quests: [quest({ name: '阴影逼近', kind: 'threat', progress: '4/4', current: 4, full: true })],
      },
    })
    expect(threat.find('.t-mini__quest').text()).toContain('已爆发')
  })

  it('无任务：显示占位而不是空白；点条/箭头展开，点线索开主持台任务页', async () => {
    const wrapper = mount(TrpgMiniStrip, {
      props: { quests: [], presentCount: 2, arrivingCount: 1, clueCount: 3, expanded: false },
    })
    expect(wrapper.find('.t-mini__quest').text()).toContain('尚无目标')
    expect(wrapper.text()).toContain('在场 2 · 赶来 1')
    expect(wrapper.text()).toContain('3')
    expect(wrapper.find('.t-mini__caret').attributes('aria-expanded')).toBe('false')

    await wrapper.find('.t-mini__quest').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
    await wrapper.find('.t-mini__caret').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(2)
    await wrapper.find('.t-mini__cast').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(3)

    await wrapper.find('.t-mini__clue').trigger('click')
    expect(wrapper.emitted('open-console')).toEqual([['quests']])
  })

  it('展开态箭头标记 aria-expanded=true', () => {
    const wrapper = mount(TrpgMiniStrip, { props: { expanded: true } })
    expect(wrapper.find('.t-mini__caret').attributes('aria-expanded')).toBe('true')
  })
})
