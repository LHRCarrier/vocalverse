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

describe('TrpgActionPanel · 快速行动条', () => {
  it('攻击：点目标出确认（目标名 + 武器下拉），确认发「我攻击{目标}」', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: { attackTargets: [target({ name: '地精', hp: '7' })], items: ITEMS },
    })
    const chip = wrapper.find('.t-act-chip--attack')
    expect(chip.text()).toContain('攻击 地精')
    expect(chip.text()).toContain('HP 7')

    await chip.trigger('click')
    expect(wrapper.find('.t-act-confirm').text()).toContain('攻击 地精')
    await wrapper.find('.t-act-confirm__btn--go').trigger('click')
    expect(wrapper.emitted('send')).toEqual([['我攻击地精']])
    expect(wrapper.find('.t-act-confirm').exists()).toBe(false)
  })

  it('攻击确认：可选持有道具当武器 → 「我用{武器}攻击{目标}」；取消不发', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: { attackTargets: [target({ name: '地精' })], items: ITEMS },
    })
    await wrapper.find('.t-act-chip--attack').trigger('click')
    await wrapper.find('select[aria-label="选择武器"]').setValue('短剑')
    await wrapper.find('.t-act-confirm__btn--go').trigger('click')
    expect(wrapper.emitted('send')).toEqual([['我用短剑攻击地精']])

    await wrapper.find('.t-act-chip--attack').trigger('click')
    await wrapper.findAll('.t-act-confirm__btn')[0]!.trigger('click') // 取消
    expect(wrapper.emitted('send')).toHaveLength(1)
    expect(wrapper.find('.t-act-confirm').exists()).toBe(false)
  })

  it('道具点击直接发「我使用{道具}」；建议行动发对应台词', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: {
        items: [ITEMS[1]!],
        quickActions: [{ label: '观察', text: '我仔细观察四周' }],
      },
    })
    await wrapper.find('.t-act-chip--item').trigger('click')
    await wrapper.find('.t-act-chip:not(.t-act-chip--item)').trigger('click')
    expect(wrapper.emitted('send')).toEqual([['我使用治疗药水'], ['我仔细观察四周']])
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

  it('disabled 时点击不发动作', async () => {
    const wrapper = mount(TrpgActionPanel, {
      props: { attackTargets: [target({ name: '地精' })], items: ITEMS, disabled: true },
    })
    await wrapper.find('.t-act-chip--attack').trigger('click')
    expect(wrapper.find('.t-act-confirm').exists()).toBe(false)
  })
})
