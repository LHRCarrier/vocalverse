import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import TrpgMessageItem from '@/components/mobile/trpg/TrpgMessageItem.vue'

describe('TrpgMessageItem（逐词高亮 + 长按操作 + NPC 分段）', () => {
  it('卡拉OK高亮：句子偏移内的 token 点亮（含中文逐字 + 英文按词）', async () => {
    const wrapper = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: 'Hello there. 你好世界。',
        highlight: { offset: 0, length: 12, progress: 1 }, // 覆盖 "Hello there." 整句
      },
    })
    const lit = wrapper.findAll('.t-tok.is-lit').map((n) => n.text())
    expect(lit.join('')).toContain('Hello')
    expect(lit.join('')).toContain('there')
    expect(lit.join('')).not.toContain('你好')
  })

  it('未在播时无高亮；中文逐字点亮', async () => {
    const off = mount(TrpgMessageItem, {
      props: { role: 'assistant', content: '你好世界。' },
    })
    expect(off.findAll('.t-tok.is-lit')).toHaveLength(0)

    const on = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: '你好世界。',
        highlight: { offset: 0, length: 3, progress: 1 },
      },
    })
    expect(on.findAll('.t-tok.is-lit').map((n) => n.text()).join('')).toBe('你好世')
  })

  it('长按触发操作事件：小抖动不取消，超过阈值移动取消', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(TrpgMessageItem, {
        props: { role: 'assistant', content: 'DM 的叙述。' },
      })
      const target = wrapper.find('.t-msg')
      // 小位移（≤14px）不取消 → 长按成立
      await target.trigger('touchstart', { touches: [{ clientX: 0, clientY: 0 }] })
      vi.advanceTimersByTime(200)
      await target.trigger('touchmove', { touches: [{ clientX: 6, clientY: 4 }] })
      vi.advanceTimersByTime(300)
      await wrapper.vm.$nextTick()
      expect(wrapper.emitted('actions')).toHaveLength(1)
      expect(wrapper.find('.t-msg').classes()).not.toContain('is-pressing')

      // 大位移（>14px）→ 取消（滚动/滑动不误触）
      await target.trigger('touchstart', { touches: [{ clientX: 0, clientY: 0 }] })
      vi.advanceTimersByTime(200)
      await target.trigger('touchmove', { touches: [{ clientX: 40, clientY: 30 }] })
      vi.advanceTimersByTime(500)
      expect(wrapper.emitted('actions')).toHaveLength(1) // 未新增
    } finally {
      vi.useRealTimers()
    }
  })

  it('翻译按钮：点击翻译 → 显示译文与「原文」；再点切回', async () => {
    const wrapper = mount(TrpgMessageItem, {
      props: { role: 'assistant', content: '你推开门。' },
    })
    expect(wrapper.find('.t-tr').text()).toBe('翻译')
    await wrapper.find('.t-tr').trigger('click')
    expect(wrapper.emitted('translate')).toHaveLength(1)

    const translated = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: '你推开门。',
        translation: { status: 'done', text: 'You push the door open.', showing: true },
      },
    })
    expect(translated.find('.t-seg--translated').text()).toBe('You push the door open.')
    expect(translated.find('.t-tr').text()).toBe('原文')
  })

  it('NPC 台词渲染成人名标签段；已标注显示徽标；无重播按钮', () => {
    const wrapper = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: '你推开门。\n\n莉亚：这边坐。',
        npcNames: new Set(['莉亚']),
        marked: true,
      },
    })
    const npc = wrapper.findAll('.t-seg--npc')
    expect(npc).toHaveLength(1)
    expect(npc[0]!.text()).toContain('莉亚')
    expect(wrapper.text()).toContain('已标注')
    expect(wrapper.find('.u-replay').exists()).toBe(false) // 旧气泡尾按钮已移除
  })
})
