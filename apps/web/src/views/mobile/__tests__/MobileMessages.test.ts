import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileChatView from '@/views/mobile/MobileChatView.vue'
import MobileMessagesView from '@/views/mobile/MobileMessagesView.vue'
import MobileNotificationsView from '@/views/mobile/MobileNotificationsView.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/messages', component: MobileMessagesView },
    { path: '/m/messages/:id', component: MobileChatView },
    { path: '/m/notifications', component: MobileNotificationsView },
  ],
})

beforeEach(() => setActivePinia(createPinia()))

describe('MobileMessagesView', () => {
  it('渲染会话列表：名字 / LV 徽章 / 最后消息 / 未读点（仅 Kai）', async () => {
    await router.push('/m/messages')
    await router.isReady()
    const wrapper = mount(MobileMessagesView, { global: { plugins: [router] } })
    const text = wrapper.text()
    expect(text).toContain('Kai')
    expect(text).toContain('LV3') // Kai L3
    expect(text).toContain('LV4') // Teacher Lee L4
    expect(text).toContain('Momo')
    expect(text).toContain('Teacher Lee')
    expect(text).toContain('Great point! I will check it out tonight.')
    expect(wrapper.findAll('.u-msg__dot')).toHaveLength(1)
  })
})

describe('MobileNotificationsView（通知中心 · 消息收敛 2026-09-09）', () => {
  it('默认私信 tab：会话列表；切通知/关注 tab 各自内容', async () => {
    await router.push('/m/notifications')
    await router.isReady()
    const wrapper = mount(MobileNotificationsView, { global: { plugins: [router] } })
    // 默认 = 私信 tab（收敛的会话列表）
    expect(wrapper.text()).toContain('Kai')
    expect(wrapper.text()).toContain('Teacher Lee')
    // 切通知 tab → 互动通知
    await wrapper.findAll('.u-notif-tab')[1].trigger('click')
    let text = wrapper.text()
    expect(text).toContain('Momo 赞了你的帖子')
    expect(text).toContain('Kai 评论了你')
    expect(text).toContain('Teacher Lee 关注了你')
    expect(wrapper.findAll('.u-notices__row')).toHaveLength(4)
    // 切关注 tab → 关注的动态（按时间/未读）
    await wrapper.findAll('.u-notif-tab')[2].trigger('click')
    text = wrapper.text()
    expect(text).toContain('Momo 发布了新帖')
    expect(text).toContain('BBC Learning English 发布了新视频')
    expect(text).toContain('更新了影子跟读素材')
    expect(wrapper.findAll('.u-notices__row')).toHaveLength(4)
  })

  it('?tab= 参数直达对应 tab（抽屉通知下拉子项）', async () => {
    await router.push('/m/notifications?tab=follow')
    await router.isReady()
    const wrapper = mount(MobileNotificationsView, { global: { plugins: [router] } })
    expect(wrapper.text()).toContain('Momo 发布了新帖')
    expect(wrapper.findAll('.u-notif-tab')[2].classes()).toContain('active')
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
