import { describe, expect, it, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

describe('MobileTopBar', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染标题；点击全局头像打开账户抽屉', async () => {
    const wrapper = mount(MobileTopBar, { props: { title: '私信' } })
    expect(wrapper.get('.u-topbar__title').text()).toBe('私信')

    await wrapper.get('button[aria-label="账户菜单"]').trigger('click')
    expect(useUiStore().drawerOpen).toBe(true)
  })

  /**
   * 2026-09-09 组长手机实测：设了真实头像后，只有侧边抽屉显示新头像，顶栏仍是首字母。
   * 根因是顶栏写死 `avatarLetter`（未换 MobileAvatar）。
   */
  it('顶栏头像用真实头像（设了 avatarUrl 时渲染 img，不再只显示首字母）', () => {
    const auth = useAuthStore()
    auth.me = {
      userId: 1,
      username: 'emma',
      nickname: 'Emma',
      level: 'L3',
      avatarUrl: '/api/v1/media/abcdef0123456789abcdef0123456789',
      tint: '#1e2b26',
    }
    const wrapper = mount(MobileTopBar, { props: { title: '社区' } })
    const img = wrapper.get('.u-topbar__ava .u-ava__img')
    expect(img.attributes('src')).toBe('/api/v1/media/abcdef0123456789abcdef0123456789')
  })

  it('无头像时回退首字母（保持原视觉基线）', () => {
    const auth = useAuthStore()
    auth.me = { userId: 1, username: 'emma', nickname: 'Emma', level: 'L3', avatarUrl: null }
    const wrapper = mount(MobileTopBar, { props: { title: '社区' } })
    expect(wrapper.find('.u-topbar__ava .u-ava__img').exists()).toBe(false)
    expect(wrapper.get('.u-topbar__ava').text()).toContain('E')
  })

  it('back=true 时离开钮（门图标）触发 back 事件', async () => {
    const wrapper = mount(MobileTopBar, { props: { title: '评分报告', back: true } })
    await wrapper.get('button[aria-label="离开"]').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })

  it('actions 插槽渲染右侧扩展按钮', () => {
    const wrapper = mount(MobileTopBar, {
      props: { title: '社区' },
      slots: { actions: '<button class="u-topbar__act">x</button>' },
    })
    expect(wrapper.find('.u-topbar__acts button.u-topbar__act').exists()).toBe(true)
  })
})
