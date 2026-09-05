import { beforeEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import MobileSearchView from '@/views/mobile/MobileSearchView.vue'

beforeEach(() => setActivePinia(createPinia()))

describe('MobileSearchView（演示搜索）', () => {
  it('空关键词：显示历史与热门 chips', () => {
    const wrapper = mount(MobileSearchView)
    const text = wrapper.text()
    expect(text).toContain('最近搜索')
    expect(text).toContain('phrasal verbs')
    expect(text).toContain('热门话题')
    expect(text).toContain('#Shadowing')
  })

  it('输入关键词：帖子结果过滤（English → Global Post）', async () => {
    const wrapper = mount(MobileSearchView)
    await wrapper.get('input[aria-label="搜索关键词"]').setValue('English')
    expect(wrapper.text()).toContain('Global Post')
    expect(wrapper.text()).not.toContain('最近搜索')
  })

  it('分类切换：用户 tab 检索 kai', async () => {
    const wrapper = mount(MobileSearchView)
    await wrapper.get('input[aria-label="搜索关键词"]').setValue('kai')
    await wrapper.findAll('.u-x-tab')[1].trigger('click') // ['帖子','用户','教程'] → 用户
    expect(wrapper.text()).toContain('Kai')
  })

  it('无结果：空态文案', async () => {
    const wrapper = mount(MobileSearchView)
    await wrapper.get('input[aria-label="搜索关键词"]').setValue('zzz 不存在')
    expect(wrapper.text()).toContain('没找到相关内容')
  })

  it('热门 chip 点击回填关键词并出结果', async () => {
    const wrapper = mount(MobileSearchView)
    const chip = wrapper.findAll('button.u-search__chip').find((b) => b.text().includes('#Shadowing'))
    expect(chip).toBeTruthy()
    await chip!.trigger('click')
    expect(wrapper.text()).toContain('Teacher Lee')
  })
})
