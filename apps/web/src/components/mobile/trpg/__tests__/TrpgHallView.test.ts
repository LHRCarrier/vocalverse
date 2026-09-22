import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { TrpgState } from '@/api/trpg'
import TrpgHallView from '@/components/mobile/trpg/TrpgHallView.vue'

/** 大堂视图：继续冒险 / 我的冒险 / 场景卡开新局 / 已完结（含当前局结局提示）。 */
function state(overrides: Partial<TrpgState> = {}): TrpgState {
  return {
    campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '你推开了酒馆的门。' },
    messages: [],
    facts: [],
    tasks: [],
    clues: [],
    entities: [],
    events: [],
    scene: '酒馆',
    snapshot: '',
    narrative_summary: '你推开了酒馆的门。',
    verify: { dangling: [], gap: false, missing: [], patch_text: null, contradiction: false },
    ...overrides,
  }
}

const CAMPAIGNS = [
  { id: 1, name: '迷雾酒馆', last_active_at: '2026-09-22T10:00:00Z' },
  { id: 2, name: '雨夜驿站', finished: true, finished_at: '2026-09-21T08:00:00Z' },
]

describe('TrpgHallView · 大堂（页内视图）', () => {
  it('继续冒险：当前剧本卡（名/场景/摘要/进行中）+ 我的冒险列表 + 开新局入口', () => {
    const wrapper = mount(TrpgHallView, {
      props: { campaigns: CAMPAIGNS, currentId: 1, state: state() },
    })
    const hero = wrapper.find('.t-hall__hero')
    expect(hero.text()).toContain('迷雾酒馆')
    expect(hero.text()).toContain('酒馆')
    expect(hero.text()).toContain('你推开了酒馆的门')
    expect(hero.find('.t-hall__badge.is-live').text()).toBe('进行中')
    expect(hero.find('button').text()).toBe('继续冒险')

    expect(wrapper.findAll('.t-hall__item')).toHaveLength(2)
    expect(wrapper.find('.t-hall__item.is-on').text()).toContain('迷雾酒馆')
    expect(wrapper.find('.t-hall__item.is-on').text()).toContain('当前')
    expect(wrapper.find('button[aria-label="重开本剧本"]').exists()).toBe(true)

    expect(wrapper.text()).toContain('用场景卡开新局')
    expect(wrapper.find('.t-hall__done').text()).toContain('雨夜驿站')
  })

  it('交互：继续 / 切换剧本 / 重开 / 打开场景卡 都上抛事件', async () => {
    const wrapper = mount(TrpgHallView, {
      props: { campaigns: CAMPAIGNS, currentId: 1, state: state() },
    })
    await wrapper.find('.t-hall__hero button').trigger('click')
    await wrapper.find('button[aria-label="切换剧本 雨夜驿站"]').trigger('click')
    await wrapper.find('button[aria-label="重开本剧本"]').trigger('click')
    await wrapper.findAll('button').find((b) => b.text() === '打开场景卡')!.trigger('click')

    expect(wrapper.emitted('continue')).toHaveLength(1)
    expect(wrapper.emitted('switchCampaign')).toEqual([[2]])
    expect(wrapper.emitted('restart')).toHaveLength(1)
    expect(wrapper.emitted('openCards')).toHaveLength(1)
  })

  it('已完结：finished 列表项 + 当前局结局提示（结局系统卡 payload）', () => {
    const wrapper = mount(TrpgHallView, {
      props: {
        campaigns: [
          // 当前剧本列表项未带 finished（结算后列表未及刷新的窗口期）→ 以 state.finished 补
          { id: 1, name: '迷雾酒馆' },
          { id: 2, name: '雨夜驿站', finished: true, finished_at: '2026-09-21T08:00:00Z' },
        ],
        currentId: 1,
        state: state({
          campaign: { id: 1, name: '迷雾酒馆', narrative_summary: '', finished: true },
          messages: [
            {
              id: 9,
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
              meta: null,
              audio_url: null,
              created_at: null,
            },
          ],
        }),
        finished: true,
      },
    })
    // 我的冒险行也标已完结（列表未同步时的 state 兜底）
    expect(wrapper.find('.t-hall__item.is-on .t-hall__badge.is-done').exists()).toBe(true)

    const done = wrapper.findAll('.t-hall__done')
    expect(done).toHaveLength(2)
    expect(done[0]!.text()).toContain('迷雾酒馆')
    // 结局提示只对当前已加载剧本可得（列表契约不带结局文案）
    expect(done[0]!.find('.t-hall__done-hint').text()).toContain('圆满结局 · 寻找戒指')
    expect(done[1]!.text()).toContain('雨夜驿站')
    expect(done[1]!.find('.t-hall__done-hint').exists()).toBe(false)
    expect(wrapper.find('.t-hall__hero .t-hall__badge.is-done').text()).toBe('已完结')
    expect(wrapper.find('.t-hall__hero button').text()).toBe('回顾本局')
  })

  it('空态：无剧本时给场景卡引导；无完结时给收尾提示', () => {
    const wrapper = mount(TrpgHallView)
    expect(wrapper.find('.t-hall__hero').exists()).toBe(false)
    expect(wrapper.text()).toContain('还没有开局')
    expect(wrapper.text()).toContain('还没有冒险记录')
    expect(wrapper.text()).toContain('还没有完结的篇章')
  })
})
