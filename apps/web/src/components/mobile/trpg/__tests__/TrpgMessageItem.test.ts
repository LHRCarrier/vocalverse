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

  it('译文按钮：点击翻译 → 显示译文与「原文」；再点切回', async () => {
    const wrapper = mount(TrpgMessageItem, {
      props: { role: 'assistant', content: '你推开门。' },
    })
    expect(wrapper.find('.t-tr').text()).toBe('译文')
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

  it('头像框/立绘链接点击上抛 standee（DM → assistant，玩家 → user）', async () => {
    const dm = mount(TrpgMessageItem, {
      props: { role: 'assistant', content: '你推开门。' },
    })
    await dm.find('.t-ava-frame').trigger('click')
    expect(dm.emitted('standee')).toEqual([['assistant']])

    const me = mount(TrpgMessageItem, {
      props: { role: 'user', content: '我走进去。', userName: '林' },
    })
    await me.find('.t-ava-frame--me').trigger('click')
    expect(me.emitted('standee')).toEqual([['user']])
    expect(me.find('.t-msg__name--me').text()).toBe('林')
  })

  it('NPC 台词渲染成独立 whisper 卡；已标注显示徽标；无重播按钮', () => {
    const wrapper = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: '你推开门。\n\n莉亚：这边坐。',
        npcNames: new Set(['莉亚']),
        marked: true,
      },
    })
    const npc = wrapper.findAll('.t-npc-card')
    expect(npc).toHaveLength(1)
    expect(npc[0]!.text()).toContain('莉亚')
    expect(npc[0]!.text()).toContain('这边坐')
    // NPC 卡不在 DM 气泡里（设计稿：三种说话人三种呈现）
    expect(npc[0]!.find('.u-bubble').exists()).toBe(false)
    expect(wrapper.text()).toContain('已标注')
    expect(wrapper.find('.u-replay').exists()).toBe(false) // 旧气泡尾按钮已移除
  })

  it('整行引号 → dm-quote 高亮（仅整行，行内引号不动）', () => {
    const wrapper = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: '他压低声音：\n\n“不要相信静止的树。”',
      },
    })
    const quotes = wrapper.findAll('.t-seg--quote')
    expect(quotes).toHaveLength(1)
    expect(quotes[0]!.text()).toContain('不要相信静止的树')
  })

  it('行内引语 → 逐 token「画重点」高亮（旁白行；NPC 卡不叠加）', () => {
    const wrapper = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        content: '他补了一句：“只有树在动。”\n\n老陈：别数叶子。',
        npcNames: new Set(['老陈']),
      },
    })
    const lit = wrapper.findAll('.t-tok--quote').map((n) => n.text()).join('')
    expect(lit).toContain('只有树在动')
    expect(lit).not.toContain('他补了一句') // 引号外的旁白不亮
    expect(wrapper.find('.t-npc-card').findAll('.t-tok--quote')).toHaveLength(0) // NPC 卡斜体台词不叠加
  })

  it('DM 头像用设计稿图，玩家头像用账号头像（缺省回退 PC 占位图）', () => {
    const dm = mount(TrpgMessageItem, { props: { role: 'assistant', content: '你推开门。' } })
    expect(dm.find('.t-ava-frame--dm img').attributes('src')).toContain('dm-avatar.webp')
    const me = mount(TrpgMessageItem, { props: { role: 'user', content: '我走进去。' } })
    expect(me.find('.t-ava-frame--me img').attributes('src')).toContain('pc-avatar.webp')
  })

  it('ending 系统卡走尾声卡（刷新恢复路径；不退化成未知系统卡）', () => {
    const wrapper = mount(TrpgMessageItem, {
      props: {
        role: 'assistant',
        kind: 'system',
        content: '',
        payload: {
          trpg_sys: 'ending',
          quest: '寻找戒指',
          outcome: 'weak',
          title: '尘埃落定 · 寻找戒指',
          text: '事情没有变得更好，但也没有彻底失控。',
          epilogue: '有些账，只能留给下一次相遇。',
        },
      },
    })
    const card = wrapper.find('.t-ending')
    expect(card.exists()).toBe(true)
    expect(card.text()).toContain('尘埃落定')
    expect(card.find('.t-ending__epilogue').text()).toContain('下一次相遇')
    expect(wrapper.find('.t-scene-line').exists()).toBe(false)
  })
})
