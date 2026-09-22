/**
 * 页首吸顶区「下滚收起 / 上滚出现」（2026-09-21 组长反馈落地，见 useAutoHideOnScroll 头注）。
 * 修复前必失败：不接 composable 时宿主不会出现 is-hidden（下滚后顶栏仍占位/不收起）。
 */
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'

import { useAutoHideOnScroll } from '@/composables/useAutoHideOnScroll'

function makeHarness() {
  return defineComponent({
    setup() {
      const host = ref<HTMLElement | null>(null)
      useAutoHideOnScroll(() => host.value)
      return { host }
    },
    template: `
      <div>
        <div ref="host" class="u-head">
          <input class="head-input" />
        </div>
        <div style="height: 3000px" />
      </div>
    `,
  })
}

function scrollTo(y: number) {
  window.scrollTo(0, y)
  window.dispatchEvent(new Event('scroll'))
}

describe('useAutoHideOnScroll · 下滚收起 / 上滚出现', () => {
  // 挂载时以当前 scrollY 为基准，用例之间必须回到顶部（否则上一用例的滚动量会吃掉本用例的位移）
  beforeEach(() => {
    window.scrollTo(0, 0)
  })

  it('下滚超过阈值 → 收起；上滚 → 出现', () => {
    const wrapper = mount(makeHarness(), { attachTo: document.body })
    const host = wrapper.find('.u-head').element

    scrollTo(400)
    expect(host.classList.contains('is-hidden')).toBe(true)

    scrollTo(360)
    expect(host.classList.contains('is-hidden')).toBe(false)
  })

  it('距顶 56px 内恒显示（下滚也不收起）', () => {
    const wrapper = mount(makeHarness(), { attachTo: document.body })
    const host = wrapper.find('.u-head').element

    scrollTo(20)
    scrollTo(40)
    expect(host.classList.contains('is-hidden')).toBe(false)

    scrollTo(400)
    expect(host.classList.contains('is-hidden')).toBe(true)
  })

  it('小幅抖动（≤6px）不切换状态', () => {
    const wrapper = mount(makeHarness(), { attachTo: document.body })
    const host = wrapper.find('.u-head').element

    scrollTo(400)
    expect(host.classList.contains('is-hidden')).toBe(true)

    scrollTo(404)
    scrollTo(400)
    scrollTo(405)
    expect(host.classList.contains('is-hidden')).toBe(true)
  })

  it('焦点在吸顶区内的输入框时下滚不收起（软键盘带动滚动不藏输入条）', () => {
    const wrapper = mount(makeHarness(), { attachTo: document.body })
    const host = wrapper.find('.u-head').element
    const input = wrapper.find('.head-input').element as HTMLInputElement
    input.focus()

    scrollTo(400)
    expect(host.classList.contains('is-hidden')).toBe(false)
  })

  it('卸载后解除监听并清掉收起态', () => {
    const wrapper = mount(makeHarness(), { attachTo: document.body })
    const host = wrapper.find('.u-head').element

    scrollTo(400)
    expect(host.classList.contains('is-hidden')).toBe(true)

    wrapper.unmount()
    expect(host.classList.contains('is-hidden')).toBe(false)
    expect(() => scrollTo(800)).not.toThrow()
  })
})
