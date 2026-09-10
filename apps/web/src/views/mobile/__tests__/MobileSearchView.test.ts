import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import MobileSearchView from '@/views/mobile/MobileSearchView.vue'

/**
 * 搜索页（演示帧 + 真实用户源）
 *
 * 2026-09-10：原「用户」结果取自 `data/messages-demo.ts`（该文件已随私信真实化删除），
 * 改取 `GET /community/follows/recommendations` 的真实作者；本文件改为 mock 该接口。
 */
vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return {
    ...actual,
    fetchFollowRecommendations: vi.fn().mockResolvedValue([
      { author: { id: 2, nickname: 'Teacher Amy', handle: 'amyteach', tint: '#37546e', level: 'L3', avatarUrl: null }, followed: false },
      { author: { id: 3, nickname: 'Kai', handle: 'kai_learns', tint: '#16303a', level: 'L3', avatarUrl: null }, followed: true },
    ]),
  }
})

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

  it('输入关键词：帖子结果过滤（English → VocalVerse News）', async () => {
    const wrapper = mount(MobileSearchView)
    await wrapper.get('input[aria-label="搜索关键词"]').setValue('English')
    expect(wrapper.text()).toContain('VocalVerse News')
    expect(wrapper.text()).not.toContain('最近搜索')
  })

  it('分类切换：用户 tab 检索真实用户源（kai → Kai）', async () => {
    const wrapper = mount(MobileSearchView)
    await flushPromises() // 等待推荐接口回填用户源
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
