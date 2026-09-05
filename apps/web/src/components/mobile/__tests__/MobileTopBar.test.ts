import { describe, expect, it, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useUiStore } from '@/stores/ui'

describe('MobileTopBar', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('渲染标题；点击全局头像打开账户抽屉', async () => {
    const wrapper = mount(MobileTopBar, { props: { title: '私信' } })
    expect(wrapper.get('.u-topbar__title').text()).toBe('私信')

    await wrapper.get('button[aria-label="账户菜单"]').trigger('click')
    expect(useUiStore().drawerOpen).toBe(true)
  })

  it('back=true 时返回钮触发 back 事件', async () => {
    const wrapper = mount(MobileTopBar, { props: { title: '评分报告', back: true } })
    await wrapper.get('button[aria-label="返回"]').trigger('click')
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
