import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import type { TrpgFactItem } from '@/api/trpg'
import TrpgCardsView from '@/components/mobile/trpg/TrpgCardsView.vue'
import type { TavernCastMember } from '@/composables/useTavernCast'

/** 角色卡视图：PC 卡（HP/位置/行囊）+ 在场/赶来/离场三段 NPC + 关系事实 + 点卡开立绘。 */
let factId = 0
function fact(key: string, value: string): TrpgFactItem {
  factId += 1
  return {
    id: factId,
    key,
    value,
    kind: 'state',
    modality: 'fact',
    speaker: null,
    importance: 0.5,
    user_touched_at: null,
    user_deleted_at: null,
  }
}

function member(partial: Partial<TavernCastMember> & { name: string }): TavernCastMember {
  return {
    kind: 'npc',
    status: 'active',
    pending: false,
    note: null,
    entityId: 1,
    portraitUrl: null,
    ...partial,
  }
}

const MEMBERS: TavernCastMember[] = [
  member({ name: '主角', kind: 'pc', status: 'active' }),
  member({ name: '莉亚', entityId: 2 }),
  member({ name: '老陈', status: 'arriving', pending: true, note: '从后厨赶来', entityId: 3 }),
  member({ name: '幽灵', status: 'departed', entityId: 4 }),
]

const FACTS = [
  fact('pc.主角.hp', '12/12'),
  fact('pc.主角.location', '吧台'),
  fact('pc.主角.inventory', '短剑, 黄铜钥匙'),
  fact('rel.莉亚.attitude', '友好'),
  fact('rel.莉亚.trust', '3'),
]

describe('TrpgCardsView · 角色卡（页内视图）', () => {
  it('玩家角色卡：立绘回退内置素材、HP/位置/行囊来自 facts', () => {
    const wrapper = mount(TrpgCardsView, { props: { pcName: '冒险者', facts: FACTS, members: MEMBERS } })
    const pc = wrapper.find('.t-cards__pc')
    expect(pc.text()).toContain('主角')
    expect(pc.text()).toContain('HP 12/12')
    expect(pc.text()).toContain('吧台')
    expect(pc.text()).toContain('短剑')
    expect(pc.text()).toContain('黄铜钥匙')
    expect(pc.find('.t-cards__pc-img').attributes('src')).toContain('pc-avatar.webp')
  })

  it('NPC 三段：在场（含关系事实）/ 赶来（note）/ 离场（置灰段）', () => {
    const wrapper = mount(TrpgCardsView, { props: { pcName: '冒险者', facts: FACTS, members: MEMBERS } })
    const present = wrapper.findAll('.t-cards__npc')
    expect(present.map((n) => n.text())).toEqual([
      expect.stringContaining('莉亚'),
      expect.stringContaining('老陈'),
      expect.stringContaining('幽灵'),
    ])
    expect(wrapper.find('button[aria-label="查看 莉亚 的角色卡"]').text()).toContain('态度：友好')
    expect(wrapper.find('button[aria-label="查看 莉亚 的角色卡"]').text()).toContain('信任：3')
    expect(wrapper.find('button[aria-label="查看 老陈 的角色卡"]').text()).toContain('赶来中')
    expect(wrapper.find('button[aria-label="查看 老陈 的角色卡"]').text()).toContain('从后厨赶来')
    expect(wrapper.find('.t-cards__sec--departed').text()).toContain('已离场')
    expect(wrapper.find('.t-cards__sec--departed').find('.t-cards__npc').classes()).toContain('is-departed')
  })

  it('点 NPC 卡上抛 select（开既有立绘展台）；点 PC 卡上抛 selectPc', async () => {
    const wrapper = mount(TrpgCardsView, { props: { pcName: '冒险者', facts: FACTS, members: MEMBERS } })
    await wrapper.find('button[aria-label="查看 莉亚 的角色卡"]').trigger('click')
    await wrapper.find('button[aria-label="查看我的角色卡"]').trigger('click')
    expect(wrapper.emitted('select')?.[0]?.[0]).toMatchObject({ name: '莉亚', kind: 'npc' })
    expect(wrapper.emitted('selectPc')).toHaveLength(1)
  })

  it('空态：无 PC 无 NPC 时给引导文案', () => {
    const wrapper = mount(TrpgCardsView)
    expect(wrapper.text()).toContain('本局暂无人物档案')
    expect(wrapper.find('.t-cards__pc').exists()).toBe(false)
  })
})
