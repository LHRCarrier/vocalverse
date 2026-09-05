import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import MobileAccountDrawer from '@/components/mobile/MobileAccountDrawer.vue'

beforeEach(() => {
  localStorage.clear()
  setActivePinia(createPinia())
})

const me = { userId: 1, username: 'demoadult', nickname: '演示用户', level: 'L3' }

const mountDrawer = (open = true) =>
  mount(MobileAccountDrawer, { props: { open, me }, global: { stubs: { teleport: true } } })

describe('MobileAccountDrawer', () => {
  it('渲染用户卡、三个菜单项与退出登录', () => {
    const wrapper = mountDrawer()
    const text = wrapper.text()
    expect(text).toContain('演示用户')
    expect(text).toContain('@demoadult')
    expect(text).toContain('你的资料')
    expect(text).toContain('消息')
    expect(text).toContain('设置与隐私')
    expect(text).toContain('退出登录')
  })

  it('菜单项 click 触发 navigate(path)', async () => {
    const wrapper = mountDrawer()
    const items = wrapper.findAll('.u-drawer__item')
    expect(items).toHaveLength(3)
    await items[0].trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/m/me']])
    await items[1].trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/m/me'], ['/m/messages']])
  })

  it('退出登录触发 logout', async () => {
    const wrapper = mountDrawer()
    await wrapper.get('.u-drawer__logout').trigger('click')
    expect(wrapper.emitted('logout')).toHaveLength(1)
  })

  it('点击遮罩触发 update:open false', async () => {
    const wrapper = mountDrawer()
    await wrapper.get('.u-drawer-mask').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })
})
