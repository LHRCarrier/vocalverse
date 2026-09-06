import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

const ALL_NAMES = [
  'home', 'mic', 'note', 'user', 'plus', 'back', 'chevron', 'clock', 'flame', 'star', 'chart',
  'coffee', 'briefcase', 'book', 'headphone', 'wave', 'check', 'refresh', 'logout', 'info',
  'heart', 'music', 'arrow', 'play', 'chat', 'coin', 'share', 'user-plus', 'stop', 'volume',
  'mail', 'bell', 'settings', 'search', 'hash',
] as const

describe('MobileIcon（单一源规范：Tabler 官方 path · stroke 2，docs/35 硬规则①）', () => {
  it('全部显示名均可渲染出 svg（无空块/缺模板）', () => {
    for (const name of ALL_NAMES) {
      const wrapper = mount(MobileIcon, { props: { name } })
      expect(wrapper.find('svg').exists(), `图标 ${name} 渲染为空`).toBe(true)
    }
  })

  it('stroke-width 统一 2（与底栏 Tabler 同规格）', () => {
    const wrapper = mount(MobileIcon, { props: { name: 'heart' } })
    expect(wrapper.find('svg').attributes('stroke-width')).toBe('2')
  })

  it('icon 无填充背景（无底图标），颜色随 currentColor', () => {
    const wrapper = mount(MobileIcon, { props: { name: 'home' } })
    expect(wrapper.find('svg').attributes('fill')).toBe('none')
    expect(wrapper.find('svg').attributes('stroke')).toBe('currentColor')
  })
})
