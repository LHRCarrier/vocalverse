import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TrpgQuestBar from '@/components/mobile/trpg/TrpgQuestBar.vue'
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

describe('TrpgQuestBar · 进度钟条', () => {
  it('分段刻度：总格数 = segments，点亮数 = current；只渲染有钟任务', () => {
    const wrapper = mount(TrpgQuestBar, {
      props: {
        quests: [
          quest({ name: '寻找戒指', progress: '3/6', current: 3, segments: 6 }),
          quest({ name: '旧案', hasClock: false, status: 'done' }),
        ],
      },
    })
    const clocks = wrapper.findAll('.t-clock')
    expect(clocks).toHaveLength(1)
    expect(clocks[0]!.text()).toContain('寻找戒指')
    expect(clocks[0]!.text()).toContain('3/6')
    expect(clocks[0]!.findAll('.t-clock__pip')).toHaveLength(6)
    expect(clocks[0]!.findAll('.t-clock__pip.is-lit')).toHaveLength(3)
    expect(clocks[0]!.classes()).toContain('t-clock--positive')
  })

  it('语义标签：正向「推进」、威胁「威胁」（不只靠颜色）', () => {
    const wrapper = mount(TrpgQuestBar, {
      props: {
        quests: [
          quest({ name: '阴影逼近', kind: 'threat', progress: '2/4', current: 2, segments: 4 }),
          quest({ name: '寻找戒指', progress: '2/6', current: 2 }),
        ],
      },
    })
    const [threat, positive] = wrapper.findAll('.t-clock')
    expect(threat!.find('.t-clock__kind').text()).toContain('威胁')
    expect(positive!.find('.t-clock__kind').text()).toContain('推进')
  })

  it('stage 与 tick reason 有则渲染（docs/57 §3.2）', () => {
    const wrapper = mount(TrpgQuestBar, {
      props: {
        quests: [
          quest({
            name: '阴影逼近',
            kind: 'threat',
            progress: '3/4',
            current: 3,
            segments: 4,
            stage: '追查',
            reason: '防线被突破',
          }),
        ],
      },
    })
    const clock = wrapper.find('.t-clock')
    expect(clock.find('.t-clock__stage').text()).toContain('追查')
    expect(clock.find('.t-clock__reason').text()).toBe('防线被突破')
  })

  it('满格玩家向文案：正向「可收尾」、威胁「已爆发」；已结算置灰「已完结」', () => {
    const wrapper = mount(TrpgQuestBar, {
      props: {
        quests: [
          quest({ name: '阴影逼近', kind: 'threat', progress: '4/4', current: 4, segments: 4, full: true }),
          quest({ name: '寻找戒指', progress: '6/6', current: 6, segments: 6, full: true }),
          quest({ name: '旧案', progress: '6/6', current: 6, segments: 6, full: true, status: 'done' }),
        ],
      },
    })
    const clocks = wrapper.findAll('.t-clock')
    expect(clocks[0]!.classes()).toContain('t-clock--threat')
    expect(clocks[0]!.classes()).toContain('is-full')
    expect(clocks[0]!.text()).toContain('已爆发')
    expect(clocks[0]!.text()).not.toContain('满格·待结算')
    expect(clocks[1]!.text()).toContain('可收尾')

    const done = clocks[2]!
    expect(done.classes()).toContain('is-closed')
    expect(done.text()).toContain('已完结')
  })

  it('空列表不渲染容器（视觉基线不变）', () => {
    const wrapper = mount(TrpgQuestBar, { props: { quests: [] } })
    expect(wrapper.find('.t-clocks').exists()).toBe(false)
  })
})
