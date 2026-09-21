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

  it('长按 450ms 触发动操作事件；移动手指取消', async () => {
    vi.useFakeTimers()
    try {
      const wrapper = mount(TrpgMessageItem, {
        props: { role: 'assistant', content: 'DM 的叙述。' },
      })
      await wrapper.find('.t-msg').trigger('touchstart')
      vi.advanceTimersByTime(500)
      expect(wrapper.emitted('actions')).toHaveLength(1)

      await wrapper.find('.t-msg').trigger('touchstart')
      vi.advanceTimersByTime(200)
      await wrapper.find('.t-msg').trigger('touchmove')
      vi.advanceTimersByTime(500)
      expect(wrapper.emitted('actions')).toHaveLength(1) // 未新增
    } finally {
      vi.useRealTimers()
    }
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
