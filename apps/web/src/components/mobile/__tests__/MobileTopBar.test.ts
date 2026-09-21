import { describe, expect, it, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

describe('MobileTopBar', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    window.scrollTo(0, 0)
  })

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

  /**
   * 2026-09-21 组长反馈：改语言/切领域要滑回顶部 → 顶栏吸顶 + 下滚收起、上滚出现。
   * 接线断言：顶栏单独用时收起自身；包在 .u-head 吸顶区时收起整块（顶栏 + 页首控制行）。
   */
  it('顶栏单独使用：下滚收起自身、上滚恢复', () => {
    const wrapper = mount(MobileTopBar, { props: { title: '酒馆' }, attachTo: document.body })
    const bar = wrapper.get('header.u-topbar').element

    window.scrollTo(0, 400)
    window.dispatchEvent(new Event('scroll'))
    expect(bar.classList.contains('is-hidden')).toBe(true)

    window.scrollTo(0, 300)
    window.dispatchEvent(new Event('scroll'))
    expect(bar.classList.contains('is-hidden')).toBe(false)
  })

  it('包在 .u-head 吸顶区：收起的是整块（顶栏自身不加 is-hidden）', () => {
    const wrapper = mount(
      {
        components: { MobileTopBar },
        template: '<div class="u-head"><MobileTopBar title="社区" /></div>',
      },
      { attachTo: document.body },
    )
    const head = wrapper.get('.u-head').element
    const bar = wrapper.get('header.u-topbar').element

    window.scrollTo(0, 400)
    window.dispatchEvent(new Event('scroll'))
    expect(head.classList.contains('is-hidden')).toBe(true)
    expect(bar.classList.contains('is-hidden')).toBe(false)
  })
})
