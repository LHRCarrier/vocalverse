/**
 * SingTabBar（唱吧页内底部导航 · 2026-09-23 用户原型 1:1）组件测试。
 *
 * 契约：5 项（首页/视频/刷歌/星光/我的）、刷歌为激活态；
 * 内容接真——首页跳 /m/home、我的开账户抽屉、视频/星光提示「后续版本」。
 */
import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'

import SingTabBar from '@/components/sing/SingTabBar.vue'
import { useUiStore } from '@/stores/ui'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: { template: '<div />' } },
    { path: '/m/home', component: { template: '<div />' } },
  ],
})

async function mountBar() {
  setActivePinia(createPinia())
  await router.push('/')
  await router.isReady()
  return mount(SingTabBar, { global: { plugins: [router] } })
}

describe('SingTabBar', () => {
  it('5 项导航；刷歌为当前页（active）', async () => {
    const w = await mountBar()
    const tabs = w.findAll('.m-sing-tab')
    expect(tabs.map((t) => t.text())).toEqual(['首页', '视频', '刷歌', '星光', '我的'])
    expect(tabs[2].classes()).toContain('active')
    expect(tabs[2].attributes('aria-current')).toBe('page')
  })

  it('首页 → 跳 /m/home', async () => {
    const w = await mountBar()
    await w.findAll('.m-sing-tab')[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/m/home')
  })

  it('我的 → 打开全局账户抽屉', async () => {
    const w = await mountBar()
    await w.findAll('.m-sing-tab')[4].trigger('click')
    expect(useUiStore().drawerOpen).toBe(true)
  })

  it('视频 / 星光 → 无对应能力，提示「后续版本」（不假装有页面）', async () => {
    const w = await mountBar()
    const ui = useUiStore()
    const spy = vi.spyOn(ui, 'showToast')
    await w.findAll('.m-sing-tab')[1].trigger('click')
    expect(spy).toHaveBeenLastCalledWith('视频 · 后续版本')
    await w.findAll('.m-sing-tab')[3].trigger('click')
    expect(spy).toHaveBeenLastCalledWith('星光 · 后续版本')
  })
})
