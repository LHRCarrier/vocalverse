/**
 * 生词本落库（docs/53 P5）：状态循环走 PATCH /vocab/{id}（失败回滚），
 * 分页 cursor 加载更多；不再本地假装保存。
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileVocabView from '@/views/mobile/MobileVocabView.vue'

import type { VocabItem } from '@/api/reading'

const mocks = vi.hoisted(() => ({
  fetchVocab: vi.fn(),
  patchVocab: vi.fn(),
  deleteVocab: vi.fn(),
}))

vi.mock('@/api/reading', () => ({
  fetchVocab: mocks.fetchVocab,
  patchVocab: mocks.patchVocab,
  deleteVocab: mocks.deleteVocab,
}))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/vocab', component: MobileVocabView },
    { path: '/m/learn', component: { template: '<div/>' } },
    { path: '/m/reader/:chapterId', component: { template: '<div/>' } },
    { path: '/m/books/:bookId', component: { template: '<div/>' } },
    { path: '/m/bookshelf', component: { template: '<div/>' } },
  ],
})

const item = (over: Partial<VocabItem> = {}): VocabItem => ({
  id: 1,
  word: 'coffee',
  status: 'new',
  scene: 'reading',
  ...over,
})

async function mountView() {
  await router.push('/m/vocab')
  await router.isReady()
  const wrapper = mount(MobileVocabView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  mocks.fetchVocab.mockResolvedValue({ items: [item()], next_cursor: null, has_more: false })
})

describe('生词本 · 状态落库（docs/53 P5）', () => {
  it('点击状态 → PATCH status=new→learning，成功显示服务端返回值', async () => {
    mocks.patchVocab.mockResolvedValue(item({ status: 'learning' }))
    const wrapper = await mountView()
    await wrapper.get('.u-vb-card__status').trigger('click')
    await flushPromises()
    expect(mocks.patchVocab).toHaveBeenCalledWith(1, { status: 'learning' })
    expect(wrapper.get('.u-vb-card__status').text()).toBe('学习中')
  })

  it('PATCH 失败 → 回滚本地状态（不假装成功）', async () => {
    mocks.patchVocab.mockRejectedValue(new Error('net down'))
    const wrapper = await mountView()
    await wrapper.get('.u-vb-card__status').trigger('click')
    await flushPromises()
    expect(wrapper.get('.u-vb-card__status').text()).toBe('新词')
  })

  it('有 next_cursor → 加载更多按 cursor 追加', async () => {
    mocks.fetchVocab
      .mockResolvedValueOnce({ items: [item()], next_cursor: 'c1', has_more: true })
      .mockResolvedValueOnce({
        items: [item({ id: 2, word: 'lighthouse', status: 'known' })],
        next_cursor: null,
        has_more: false,
      })
    const wrapper = await mountView()
    const more = wrapper.get('.u-comm-more')
    await more.trigger('click')
    await flushPromises()

    expect(mocks.fetchVocab).toHaveBeenLastCalledWith(undefined, 'c1')
    expect(wrapper.text()).toContain('lighthouse')
    expect(wrapper.find('.u-comm-more').exists()).toBe(false)
  })
})
