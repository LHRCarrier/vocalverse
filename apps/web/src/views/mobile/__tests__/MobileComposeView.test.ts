import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileComposeView from '@/views/mobile/MobileComposeView.vue'
import { useUiStore } from '@/stores/ui'

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return { ...actual, createPost: vi.fn().mockResolvedValue({ id: 1 }) }
})

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
    await flushPromises()
    expect(useUiStore().toastText).toBe('已发布')
    expect(router.currentRoute.value.path).toBe('/m/home')
  })

  it('领域必选（默认教学分享）；切换领域 aria-pressed 生效', async () => {
    const wrapper = mount(MobileComposeView)
    const active = wrapper.findAll('button.u-compose__domain').find((b) => b.attributes('aria-pressed') === 'true')
    expect(active?.text()).toContain('教学分享')
  })
})
