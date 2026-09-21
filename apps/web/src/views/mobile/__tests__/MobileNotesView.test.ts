/**
 * 笔记页接真（docs/53 P5）：跨章批注来自 GET /api/v1/reading/notes，点击跳回阅读器章节。
 */
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileNotesView from '@/views/mobile/MobileNotesView.vue'

const mocks = vi.hoisted(() => ({ fetchNotes: vi.fn() }))

vi.mock('@/api/reading', () => ({ fetchNotes: mocks.fetchNotes }))

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/notes', component: MobileNotesView },
    { path: '/m/learn', component: { template: '<div/>' } },
    { path: '/m/bookshelf', component: { template: '<div/>' } },
    { path: '/m/reader/:chapterId', component: { template: '<div/>' } },
  ],
})

async function mountView() {
  await router.push('/m/notes')
  await router.isReady()
  const wrapper = mount(MobileNotesView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  mocks.fetchNotes.mockResolvedValue({
    items: [
      {
        id: 1,
        kind: 'note',
        chapter_id: 5,
        book_id: 2,
        chapter_title: 'Chapter 1',
        book_title: 'Demo Book',
        start_offset: 0,
        end_offset: 5,
        content_version: 1,
        text_snippet: 'Alice knew',
        note: '过去式',
        created_at: '2026-09-21T10:00:00+00:00',
      },
    ],
    has_more: false,
  })
})

describe('笔记页（docs/53 P5）', () => {
  it('渲染跨章批注（书/章/批注文本）并跳回阅读器', async () => {
    const wrapper = await mountView()
    expect(mocks.fetchNotes).toHaveBeenCalledWith(undefined)
    expect(wrapper.text()).toContain('过去式')
    expect(wrapper.text()).toContain('Demo Book · Chapter 1')

    await wrapper.get('button.u-notes__card').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/m/reader/5')
  })

  it('分类切换走服务端 kind 过滤', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.u-x-tab')[1].trigger('click')
    await flushPromises()
    expect(mocks.fetchNotes).toHaveBeenLastCalledWith('highlight')
    await wrapper.findAll('.u-x-tab')[2].trigger('click')
    await flushPromises()
    expect(mocks.fetchNotes).toHaveBeenLastCalledWith('note')
  })

  it('无数据：空态引导去书房（不显示演示笔记）', async () => {
    mocks.fetchNotes.mockResolvedValue({ items: [], has_more: false })
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('这个分类还没有笔记')
    expect(wrapper.text()).not.toContain('pick up')
  })

  it('接口失败：错误与重试', async () => {
    mocks.fetchNotes.mockRejectedValueOnce(new Error('net down'))
    const wrapper = await mountView()
    expect(wrapper.text()).toContain('加载失败')
    await wrapper.get('.u-comm-empty__btn').trigger('click')
    await flushPromises()
    expect(mocks.fetchNotes).toHaveBeenCalledTimes(2)
  })
})
