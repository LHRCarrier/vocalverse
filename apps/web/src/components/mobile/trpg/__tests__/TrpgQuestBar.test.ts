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

  it('正向/威胁两色 + 满格强调 + 已结算置灰', () => {
    const wrapper = mount(TrpgQuestBar, {
      props: {
        quests: [
          quest({ name: '阴影逼近', kind: 'threat', progress: '4/4', current: 4, segments: 4, full: true }),
          quest({ name: '寻找戒指', progress: '6/6', current: 6, segments: 6, full: true, status: 'done' }),
        ],
      },
    })
    const threat = wrapper.findAll('.t-clock')[0]!
    expect(threat.classes()).toContain('t-clock--threat')
    expect(threat.classes()).toContain('is-full')
    expect(threat.text()).toContain('满格·待结算')

    const done = wrapper.findAll('.t-clock')[1]!
    expect(done.classes()).toContain('is-closed')
    expect(done.text()).toContain('已结算')
  })

  it('空列表不渲染容器（视觉基线不变）', () => {
    const wrapper = mount(TrpgQuestBar, { props: { quests: [] } })
    expect(wrapper.find('.t-clocks').exists()).toBe(false)
  })
})
