import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileChatView from '@/views/mobile/MobileChatView.vue'
import MobileMessagesView from '@/views/mobile/MobileMessagesView.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/messages', component: MobileMessagesView },
    { path: '/m/messages/:id', component: MobileChatView },
  ],
})

beforeEach(() => setActivePinia(createPinia()))

describe('MobileMessagesView', () => {
  it('渲染会话列表：名字 / 最后消息 / 未读点（仅 Kai）', async () => {
    await router.push('/m/messages')
    await router.isReady()
    const wrapper = mount(MobileMessagesView, { global: { plugins: [router] } })
    const text = wrapper.text()
    expect(text).toContain('Kai')
    expect(text).toContain('Momo')
    expect(text).toContain('Teacher Lee')
    expect(text).toContain('Great point! I will check it out tonight.')
    expect(wrapper.findAll('.u-msg__dot')).toHaveLength(1)
  })
})

describe('MobileChatView', () => {
  it('渲染历史消息；发送后我方气泡上屏，1.2s 后自动回复轮换', async () => {
    vi.useFakeTimers()
    await router.push('/m/messages/1')
    await router.isReady()
    const wrapper = mount(MobileChatView, { global: { plugins: [router] } })

    expect(wrapper.text()).toContain('That article we talked about')

    await wrapper.get('input[aria-label="消息内容"]').setValue('See you tomorrow!')
    await wrapper.get('button[aria-label="发送消息"]').trigger('click')
    expect(wrapper.text()).toContain('See you tomorrow!')

    await vi.advanceTimersByTimeAsync(1300)
    expect(wrapper.text()).toContain('True — and the shadowing routine helps me a lot too.')
    vi.useRealTimers()
  })
})
