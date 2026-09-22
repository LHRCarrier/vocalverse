import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { TrpgState } from '@/api/trpg'
import TrpgChronicleView from '@/components/mobile/trpg/TrpgChronicleView.vue'
import type { TavernRow } from '@/composables/useTavernSession'

/** 纪事视图：本局摘要 / 编年史（最新在前）/ 任务与线索状态 / 尾声（结局系统卡）。 */
function state(overrides: Partial<TrpgState> = {}): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '' },
    messages: [],
    facts: [],
    tasks: [
      { id: 1, title: '寻找戒指', status: 'active', scene: null, last_mentioned_at: null },
      { id: 2, title: '打听怪谈', status: 'done', scene: null, last_mentioned_at: null },
    ],
    clues: [
      { id: 1, title: '暗门', content: '酒保提到过', scene: null, found: true, recovered: false, last_mentioned_at: null },
      { id: 2, title: '断刃', content: null, scene: null, found: false, recovered: false, last_mentioned_at: null },
    ],
    entities: [],
    events: [
      { id: 1, round: 1, summary: '抵达酒馆', created_at: null },
      { id: 2, round: 3, summary: '钟声响起', created_at: null },
    ],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '【摘要】钟声逼近。',
    verify: { dangling: [], gap: false, missing: [], patch_text: null, contradiction: false },
    ...overrides,
  }
}

const ENDING_ROW: TavernRow = {
  role: 'assistant',
  kind: 'system',
  content: '',
  payload: {
    trpg_sys: 'ending',
    quest: '寻找戒指',
    outcome: 'strong',
    title: '圆满结局 · 寻找戒指',
    text: '你做到了。',
    epilogue: '多年以后。',
  },
}

describe('TrpgChronicleView · 纪事（页内视图）', () => {
  it('渲染摘要 / 编年史（最新在前）/ 任务与线索状态 / 尾声卡', () => {
    const wrapper = mount(TrpgChronicleView, { props: { state: state(), rows: [ENDING_ROW] } })
    expect(wrapper.find('.t-chron__sum').text()).toContain('钟声逼近')

    const events = wrapper.findAll('.t-chron__event')
    expect(events).toHaveLength(2)
    expect(events[0]!.text()).toContain('第 3 回合')
    expect(events[0]!.text()).toContain('钟声响起')
    expect(events[1]!.text()).toContain('第 1 回合')

    expect(wrapper.text()).toContain('寻找戒指')
    expect(wrapper.text()).toContain('进行中')
    expect(wrapper.text()).toContain('已完成')
    expect(wrapper.text()).toContain('已找到')
    expect(wrapper.text()).toContain('未找到')

    expect(wrapper.find('.t-ending').text()).toContain('圆满结局')
  })

  it('非结局行不进尾声区（只认 trpg_sys="ending"）', () => {
    const rows: TavernRow[] = [
      { role: 'assistant', kind: 'system', content: '', payload: { trpg_sys: 'dice', text: '第 1 回合' } },
      { role: 'assistant', kind: 'text', content: 'DM 叙述' },
    ]
    const wrapper = mount(TrpgChronicleView, { props: { state: state({ events: [], tasks: [], clues: [] }), rows } })
    expect(wrapper.find('.t-ending').exists()).toBe(false)
    expect(wrapper.text()).toContain('本局还没有尾声')
  })

  it('空态：摘要/编年史/任务线索/尾声各自给引导文案', () => {
    const wrapper = mount(TrpgChronicleView, {
      props: {
        state: state({ narrative_summary: '', events: [], tasks: [], clues: [] }),
        rows: [],
      },
    })
    expect(wrapper.text()).toContain('还没有摘要')
    expect(wrapper.text()).toContain('还没有编年记录')
    expect(wrapper.text()).toContain('还没有任务或线索')
    expect(wrapper.text()).toContain('本局还没有尾声')
  })
})
