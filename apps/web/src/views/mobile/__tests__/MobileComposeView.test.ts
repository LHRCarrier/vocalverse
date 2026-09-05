import { beforeEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileComposeView from '@/views/mobile/MobileComposeView.vue'
import { useUiStore } from '@/stores/ui'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/compose', component: MobileComposeView },
    { path: '/m/home', component: { template: '<div/>' } },
  ],
})

beforeEach(() => setActivePinia(createPinia()))

describe('MobileComposeView', () => {
  it('空内容发布钮禁用；输入后启用；发布 → toast + 回社区', async () => {
    await router.push('/m/compose')
    await router.isReady()
    const wrapper = mount(MobileComposeView, { global: { plugins: [router] } })

    const btn = wrapper.get('button[aria-label="发布"]')
    expect(btn.attributes('disabled')).toBeDefined()

    await wrapper.get('textarea').setValue('  Hello VocalVerse  ')
    expect(btn.attributes('disabled')).toBeUndefined()

    await btn.trigger('click')
    expect(useUiStore().toastText).toBe('已发布（演示）')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/m/home')
  })
})
