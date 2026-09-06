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
    expect(text).toContain('我的学习')
    expect(text).toContain('通知')
    expect(text).toContain('设置与隐私')
    expect(text).toContain('退出登录')
  })

  it('菜单项 click：我的学习 → 四模块；通知 → 三子项（私信/互动/关注?tab=）；设置 → 子项 toast', async () => {
    const wrapper = mountDrawer()
    const items = wrapper.findAll('.u-drawer__item')
    expect(items).toHaveLength(3)
    // 我的学习：展开四模块
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(false)
    await items[0].trigger('click')
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(true)
    expect(wrapper.text()).toContain('我的单词')
    expect(wrapper.text()).toContain('社区足迹')
    expect(wrapper.text()).toContain('我的发音')
    expect(wrapper.text()).toContain('练习情况')
    // 点子项 → navigate 详情 + 面板收起
    await wrapper.findAll('.u-drawer__subitem')[2].trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/m/learn/speaking']])
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(false)
    // 通知：展开三子项（私信/互动通知/关注动态 → ?tab= 直达）
    await items[1].trigger('click')
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(true)
    expect(wrapper.text()).toContain('私信')
    expect(wrapper.text()).toContain('互动通知')
    expect(wrapper.text()).toContain('关注动态')
    await wrapper.findAll('.u-drawer__subitem')[2].trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/m/learn/speaking'], ['/m/notifications?tab=follow']])
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(false)
    // 设置与隐私：展开子面板（帮助与反馈/数据与隐私/关于声语界），无 navigate
    await items[2].trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/m/learn/speaking'], ['/m/notifications?tab=follow']])
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(true)
    expect(wrapper.text()).toContain('帮助与反馈')
    // 子项点击 → toast + 收起
    await wrapper.findAll('.u-drawer__subitem')[0].trigger('click')
    expect(wrapper.find('.u-drawer__submenu').exists()).toBe(false)
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
