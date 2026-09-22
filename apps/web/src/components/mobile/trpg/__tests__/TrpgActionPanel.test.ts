import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TrpgActionPanel from '@/components/mobile/trpg/TrpgActionPanel.vue'
import type {
  TavernEncounter,
  TavernItem,
  TavernParticipant,
} from '@/composables/useTavernEncounter'

function target(partial: Partial<TavernParticipant> & { name: string }): TavernParticipant {
  return { key: `npc.${partial.name}`, kind: 'npc', hp: null, current: false, ...partial }
}

const ITEMS: TavernItem[] = [
  { name: '短剑', qty: 1, owner: 'pc.主角', effect: null, consumable: false },
  { name: '治疗药水', qty: 2, owner: 'pc.主角', effect: '回复5', consumable: true },
]

const ENCOUNTER: TavernEncounter = {
  id: 'main',
  status: 'active',
  order: ['pc.主角', 'npc.地精'],
  turn: 1,
  round: 2,
  currentKey: 'npc.地精',
  currentName: '地精',
}

describe('TrpgActionPanel · 常驻快速行动条（docs/57 §3.2）', () => {
  it('无实体/无道具：面板仍渲染（行动行常驻）', () => {
    const wrapper = mount(TrpgActionPanel)
    expect(wrapper.find('.t-act-panel').exists()).toBe(true)
    expect(wrapper.find('.t-act-panel__row').exists()).toBe(true)
    expect(wrapper.find('.t-act-confirm').exists()).toBe(false)
  })

  it('攻击：点目标出确认（目标名 + 武器下拉仅非消耗品），确认发「我用{武器}攻击{目标}」+ 回执', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: { attackTargets: [target({ name: '地精', hp: '7' })], items: ITEMS },
    })
    const chip = wrapper.find('.t-act-chip--attack')
    expect(chip.text()).toContain('攻击 地精')
    expect(chip.text()).toContain('HP 7')

    await chip.trigger('click')
    expect(wrapper.find('.t-act-confirm').text()).toContain('攻击 地精')
    const options = wrapper.findAll('select[aria-label="选择武器"] option').map((o) => o.text())
    expect(options).toEqual(['徒手', '短剑']) // 治疗药水（消耗品）不是武器
    await wrapper.find('select[aria-label="选择武器"]').setValue('短剑')
    await wrapper.find('.t-act-confirm__btn--go').trigger('click')
    expect(wrapper.emitted('send')).toEqual([['我用短剑攻击地精']])
    expect(wrapper.emitted('feedback')).toEqual([['已出手 · 我用短剑攻击地精']])
    expect(wrapper.find('.t-act-confirm').exists()).toBe(false)
  })

  it('攻击确认：取消不发；disabled 时点目标不出确认', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: { attackTargets: [target({ name: '地精' })], items: ITEMS },
    })
    await wrapper.find('.t-act-chip--attack').trigger('click')
    await wrapper.findAll('.t-act-confirm__btn')[0]!.trigger('click') // 取消
    expect(wrapper.emitted('send')).toBeUndefined()
    expect(wrapper.find('.t-act-confirm').exists()).toBe(false)

    const disabled = mount(TrpgActionPanel, {
      props: { attackTargets: [target({ name: '地精' })], items: ITEMS, disabled: true },
    })
    await disabled.find('.t-act-chip--attack').trigger('click')
    expect(disabled.find('.t-act-confirm').exists()).toBe(false)
  })

  it('道具点击直接发「我使用{道具}」+ 即时回执；建议行动只填入（prefill）不发送', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: {
        items: [ITEMS[1]!],
        quickActions: [
          { kind: 'observe', label: '观察酒馆', text: '我仔细观察酒馆' },
          { kind: 'talk', label: '与莉亚交谈', text: '我试着与莉亚交谈' },
          { kind: 'advance', label: '推进寻找戒指', text: '我继续推进：寻找戒指' },
        ],
      },
    })
    await wrapper.find('.t-act-chip--item').trigger('click')
    expect(wrapper.emitted('send')).toEqual([['我使用治疗药水']])
    expect(wrapper.emitted('feedback')).toEqual([['已使用 · 治疗药水']])

    const suggests = wrapper.findAll('.t-act-chip--suggest')
    expect(suggests.map((s) => s.text())).toEqual(['观察酒馆', '与莉亚交谈', '推进寻找戒指'])
    await suggests[1]!.trigger('click')
    expect(wrapper.emitted('prefill')).toEqual([['我试着与莉亚交谈']])
    expect(wrapper.emitted('send')).toHaveLength(1) // 建议不直接发送
  })

  it('收尾本幕：满格任务出现按钮 → 上抛 settle；settling 中禁点', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: { settleable: [{ name: '寻找戒指' }] },
    })
    const button = wrapper.find('.t-act-chip--settle')
    expect(button.text()).toContain('收尾本幕 · 寻找戒指')
    await button.trigger('click')
    expect(wrapper.emitted('settle')).toEqual([['寻找戒指']])

    const settling = mount(TrpgActionPanel, {
      props: { settleable: [{ name: '寻找戒指' }], settling: true },
    })
    await settling.find('.t-act-chip--settle').trigger('click')
    expect(settling.emitted('settle')).toBeUndefined()
  })

  it('遭遇进行中：内嵌战况卡（轮次 + 当前行动者高亮）', () => {
    const wrapper = mount(TrpgActionPanel, {
      props: {
        encounter: ENCOUNTER,
        participants: [
          target({ key: 'pc.主角', name: '主角', kind: 'pc', current: false }),
          target({ name: '地精', hp: '7', current: true }),
        ],
      },
    })
    const card = wrapper.find('.t-enc')
    expect(card.text()).toContain('第 2 轮')
    expect(card.text()).toContain('当前：地精')
    expect(card.find('.t-enc__pip.is-current').text()).toContain('地精')
    expect(card.text()).toContain('HP 7')
  })

  it('disabled 时道具/建议/收尾都不可点', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: {
        items: ITEMS,
        quickActions: [{ kind: 'observe', label: '观察', text: '我仔细观察四周' }],
        settleable: [{ name: '寻找戒指' }],
        disabled: true,
      },
    })
    await wrapper.find('.t-act-chip--item').trigger('click')
    await wrapper.find('.t-act-chip--suggest').trigger('click')
    await wrapper.find('.t-act-chip--settle').trigger('click')
    expect(wrapper.emitted('send')).toBeUndefined()
    expect(wrapper.emitted('prefill')).toBeUndefined()
    expect(wrapper.emitted('settle')).toBeUndefined()
  })
})
