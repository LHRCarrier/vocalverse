import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TrpgCastBar from '@/components/mobile/trpg/TrpgCastBar.vue'
import type { TavernCastMember } from '@/composables/useTavernCast'

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

describe('TrpgCastBar · 在场角色条', () => {
  it('arriving 显示脉冲「正在赶来…」；departed 置灰；present 无备注', () => {
    const wrapper = mount(TrpgCastBar, {
      props: {
        members: [
          member({ name: '莉亚' }),
          member({ name: '老陈', status: 'arriving', pending: true, note: '从后厨赶来' }),
          member({ name: '幽灵', status: 'departed', entityId: 3 }),
        ],
      },
    })
    const items = wrapper.findAll('.t-cast__item')
    expect(items).toHaveLength(3)
    expect(items[1]!.classes()).toContain('is-arriving')
    expect(items[1]!.text()).toContain('正在赶来…')
    expect(items[2]!.classes()).toContain('is-departed')
    expect(items[2]!.text()).toContain('已离场')
    expect(items[0]!.find('.t-cast__note').exists()).toBe(false)
  })

  it('立绘：有 URL 用 img，无 URL 用首字占位', () => {
    const wrapper = mount(TrpgCastBar, {
      props: {
        members: [
          member({ name: '莉亚', portraitUrl: '/api/v1/media/m1' }),
          member({ name: '无名客', portraitUrl: null }),
        ],
      },
    })
    const items = wrapper.findAll('.t-cast__item')
    expect(items[0]!.find('.t-cast__ava img').attributes('src')).toBe('/api/v1/media/m1')
    expect(items[1]!.find('.t-cast__ava img').exists()).toBe(false)
    expect(items[1]!.find('.t-cast__ava').text()).toBe('无')
  })

  it('点击成员上抛 select（含立绘/状态，供立绘展台聚焦）', async () => {
    const arriving = member({ name: '老陈', status: 'arriving', pending: true, entityId: null })
    const wrapper = mount(TrpgCastBar, { props: { members: [arriving] } })
    await wrapper.find('.t-cast__item').trigger('click')
    expect(wrapper.emitted('select')).toEqual([[arriving]])
  })

  it('空名单不渲染容器', () => {
    const wrapper = mount(TrpgCastBar, { props: { members: [] } })
    expect(wrapper.find('.t-cast').exists()).toBe(false)
  })
})
