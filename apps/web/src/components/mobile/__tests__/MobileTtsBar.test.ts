/**
 * 听书播放条组件测试（docs/45 §6：按钮 → 事件；进度/倍速反映状态）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobileTtsBar from '../MobileTtsBar.vue'

function mountBar(props = {}) {
  return mount(MobileTtsBar, {
    props: {
      label: '1/10',
      playing: false,
      progress: 0.3,
      rate: 1,
      ...props,
    },
  })
}

describe('MobileTtsBar', () => {
  it('渲染播放/暂停/上句/下句/倍速/关闭', () => {
    const wrapper = mountBar()
    expect(wrapper.find('.u-rd-tts').exists()).toBe(true)
    expect(wrapper.find('[aria-label="播放"]').exists()).toBe(true)
    expect(wrapper.findAll('[title="上一句"]').length).toBe(1)
    expect(wrapper.findAll('[title="下一句"]').length).toBe(1)
    expect(wrapper.find('.u-rd-tts__rate').text()).toBe('1x')
  })

  it('playing 时显示暂停钮', () => {
    const wrapper = mountBar({ playing: true })
    expect(wrapper.find('[aria-label="暂停"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="播放"]').exists()).toBe(false)
  })

  it('事件：toggle/prev/next/change-rate/close', async () => {
    const wrapper = mountBar()
    await wrapper.find('[aria-label="播放"]').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
    await wrapper.find('[aria-label="上一句"]').trigger('click')
    expect(wrapper.emitted('prev')).toHaveLength(1)
    await wrapper.find('[aria-label="下一句"]').trigger('click')
    expect(wrapper.emitted('next')).toHaveLength(1)
    await wrapper.find('.u-rd-tts__rate').trigger('click')
    expect(wrapper.emitted('change-rate')).toHaveLength(1)
    await wrapper.find('[aria-label="关闭听书"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('进度条宽度按 progress 映射', () => {
    const wrapper = mountBar({ progress: 0.42 })
    const fill = wrapper.find('.u-rd-tts__fill')
    expect(fill.attributes('style')).toContain('width: 42%')
  })
})
