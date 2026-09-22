import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import TrpgEndingCard from '@/components/mobile/trpg/TrpgEndingCard.vue'

const PAYLOAD = {
  trpg_sys: 'ending',
  quest: '寻找戒指',
  outcome: 'strong',
  title: '圆满结局 · 寻找戒指',
  text: '你以出色的行动力让「寻找戒指」迎来了最好的收束。',
  epilogue: '多年以后，酒馆里仍有人提起这一夜。',
}

describe('TrpgEndingCard · 尾声卡', () => {
  it('渲染档位徽标 / 标题 / 正文 / 后日谈', () => {
    const wrapper = mount(TrpgEndingCard, { props: { payload: PAYLOAD } })
    const card = wrapper.find('.t-ending')
    expect(card.exists()).toBe(true)
    expect(card.classes()).toContain('t-ending--strong')
    expect(card.text()).toContain('圆满结局')
    expect(card.find('.t-ending__title').text()).toContain('圆满结局 · 寻找戒指')
    expect(card.find('.t-ending__text').text()).toContain('最好的收束')
    expect(card.find('.t-ending__epilogue').text()).toContain('多年以后')
  })

  it('miss 档位样式 + 空后日谈不渲染尾注', () => {
    const wrapper = mount(TrpgEndingCard, {
      props: { payload: { ...PAYLOAD, outcome: 'miss', epilogue: '' } },
    })
    expect(wrapper.find('.t-ending').classes()).toContain('t-ending--miss')
    expect(wrapper.find('.t-ending__badge').text()).toBe('遗憾收场')
    expect(wrapper.find('.t-ending__epilogue').exists()).toBe(false)
  })

  it('非法/缺失 payload → 降级为细线（不炸）', () => {
    const wrapper = mount(TrpgEndingCard, { props: { payload: { trpg_sys: 'dice' } } })
    expect(wrapper.find('.t-ending').exists()).toBe(false)
    expect(wrapper.find('.t-scene-line').text()).toContain('尾声')
  })
})
