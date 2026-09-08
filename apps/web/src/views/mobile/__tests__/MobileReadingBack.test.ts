/**
 * 读书域返回导航回归测试（2026-09-10 · 组长手机实测 bug 1）
 *
 * 复现路径（修复前必失败）：书架 → 点书进详情 → 开始阅读 → 阅读器顶栏「离开」→ 详情 → 详情顶栏「离开」
 * 期望：最终回到书架（历史栈单调回退）
 * 修复前：阅读器「离开」是 router.push(书详情)，历史栈变 [书架, 详情, 阅读器, 详情]；
 *        详情页「离开」是 router.back() → 又回到阅读器 → 两页来回跳、退不出这一本书。
 *        因此第 3 步断言（详情「离开」应到书架）在修复前必失败。
 *
 * 注意：本测试用 createWebHistory（与生产 router/index.ts 一致）——
 * useMobileBack 依据 history.state.back 判断有无上一条，memory history 不维护该字段，
 * 用它测不出真实行为。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import type { Router } from 'vue-router'

import MobileBookDetailView from '@/views/mobile/MobileBookDetailView.vue'
import MobileReaderView from '@/views/mobile/MobileReaderView.vue'
import { runNativeBackHandlers } from '@/composables/useNativeBack'

const fixtures = vi.hoisted(() => ({
  detail: {
    id: 1,
    title: 'Alice in Wonderland',
    author: 'Lewis Carroll',
    description: '公版书',
    level: 'B1',
    cover_color: '#123456',
    cover_emoji: '🐇',
    word_count: 26000,
    chapter_count: 12,
    progress: null,
    chapters: [{ id: 7, chapter_no: 1, title: 'Chapter I', word_count: 2000, char_count: 9000, current: true }],
  },
  chapter: {
    id: 7,
    book_id: 1,
    chapter_no: 1,
    title: 'Chapter I',
    content_version: 1,
    content: 'Alice was beginning to get very tired.',
    paragraphs: ['Alice was beginning to get very tired.'],
    sentences: [{ idx: 0, text: 'Alice was beginning to get very tired.', para_idx: 0, start: 0, end: 38 }],
    word_count: 8,
    char_count: 38,
  },
}))

vi.mock('@/api/reading', () => ({
  fetchBookDetail: vi.fn(async () => fixtures.detail),
  fetchChapter: vi.fn(async () => fixtures.chapter),
  fetchVoices: vi.fn(async () => []),
  fetchVocab: vi.fn(async () => ({ items: [], next_cursor: null, has_more: false })),
  fetchAnnotations: vi.fn(async () => []),
  saveProgress: vi.fn(async () => undefined),
  lookupWord: vi.fn(),
  addVocab: vi.fn(),
  segmentAudioUrl: vi.fn(() => ''),
  loadSegmentAudio: vi.fn(),
  prepareChapter: vi.fn(),
}))

const stub = { template: '<div class="stub" />' }

function makeRouter(): Router {
  return createRouter({
    history: createWebHistory(),
    routes: [
      { path: '/m/bookshelf', component: stub },
      { path: '/m/learn', component: stub },
      { path: '/m/books/:bookId', component: MobileBookDetailView },
      { path: '/m/reader/:chapterId', component: MobileReaderView },
    ],
  })
}

async function mountAt(router: Router, path: string) {
  const wrapper = mount({ template: '<router-view />' }, { global: { plugins: [router, createPinia()] } })
  await router.push(path)
  await flushPromises()
  return wrapper
}

/** 点击当前页顶栏「离开」钮并等待路由稳定 */
async function clickLeave(wrapper: ReturnType<typeof mount>) {
  await wrapper.get('button[aria-label="离开"]').trigger('click')
  await flushPromises()
}

describe('读书域返回导航（修复前必失败）', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('阅读器「离开」→ 书详情；书详情「离开」→ 书架（不再来回跳）', async () => {
    const router = makeRouter()
    const wrapper = await mountAt(router, '/m/bookshelf')

    await router.push('/m/books/1')
    await flushPromises()
    await router.push('/m/reader/7?book=1')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/m/reader/7?book=1')

    // 1) 阅读器「离开」→ 回书详情
    await clickLeave(wrapper)
    expect(router.currentRoute.value.fullPath).toBe('/m/books/1')

    // 2) 书详情「离开」→ 必须到书架（修复前这里会弹回阅读器）
    await clickLeave(wrapper)
    expect(router.currentRoute.value.fullPath).toBe('/m/bookshelf')

    wrapper.unmount()
  })

  it('冷启直达书详情（无上一条历史）时「离开」回退到书架，而不是卡死', async () => {
    const router = makeRouter()
    // 冷启：直接以书详情为第一条历史
    const wrapper = await mountAt(router, '/m/books/1')
    await clickLeave(wrapper)
    expect(router.currentRoute.value.fullPath).toBe('/m/bookshelf')
    wrapper.unmount()
  })

  it('冷启直达阅读器（无上一条历史）时「离开」回退到本书详情', async () => {
    const router = makeRouter()
    const wrapper = await mountAt(router, '/m/reader/7?book=1')
    await clickLeave(wrapper)
    expect(router.currentRoute.value.fullPath).toBe('/m/books/1')
    wrapper.unmount()
  })

  it('阅读器弹层打开时，原生返回手势先关弹层、不回退页面（bug 3）', async () => {
    const router = makeRouter()
    const wrapper = await mountAt(router, '/m/reader/7?book=1')

    // 打开阅读设置弹层（Teleport 到 body）
    await wrapper.get('button[aria-label="设置"]').trigger('click')
    await flushPromises()
    expect(document.querySelector('.u-sheet')).not.toBeNull()

    // 原生壳调 window.__vvNativeBack() → 弹层被消费
    expect(runNativeBackHandlers()).toBe(true)
    await flushPromises()
    expect(document.querySelector('.u-sheet')).toBeNull()
    // 页面没有回退（仍停在阅读器）
    expect(router.currentRoute.value.fullPath).toBe('/m/reader/7?book=1')

    // 弹层已关 → 再按返回则未消费（交给原生回退历史）
    expect(runNativeBackHandlers()).toBe(false)
    wrapper.unmount()
  })
})
