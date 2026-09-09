/**
 * 帖子详情页（社区 S3 · docs/47 §5.1）
 *
 * 锁四件事（都是「修复前不可能通过」的闭环能力）：
 * 1. 点帖子有查看方式 → /m/post/:id 渲染详情（作者真实头像 + 多图 + 正文）；
 * 2. 互动在详情页可用（点赞乐观更新，回写 store 不炸）；
 * 3. 正文划词 → 查词卡（复用读书域 MobileWordCard）+ 加入生词本带 scene=community；
 * 4. 媒体灯箱打开时，安卓返回键先关灯箱（不直接退页）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobilePostDetailView from '@/views/mobile/MobilePostDetailView.vue'
import { runNativeBackHandlers } from '@/composables/useNativeBack'

const fixtures = vi.hoisted(() => ({
  post: {
    id: 42,
    author: { id: 1, nickname: 'Emma', handle: 'emmaenglish', tint: '#1e2b26', level: 'L3', avatarUrl: '/api/v1/media/aaaa' },
    kind: 'article',
    domain: 'teaching',
    title: '5 phrasal verbs',
    body: 'This wonderful post is for you.',
    media: {
      type: 'image',
      items: [
        { id: 'a', url: '/api/v1/media/a', width: 800, height: 600, size: 1024, mimeType: 'image/png' },
        { id: 'b', url: '/api/v1/media/b', width: 800, height: 600, size: 2048, mimeType: 'image/png' },
      ],
    },
    createdAt: '2026-09-09T02:00:00Z',
    likeCount: 3,
    coinCount: 1,
    commentCount: 2,
    shareCount: 0,
    liked: false,
    coined: false,
    checkinOverall: null,
    checkinPracticeCount: null,
    checkinDate: null,
  },
}))

const api = vi.hoisted(() => ({
  fetchPost: vi.fn(),
  fetchComments: vi.fn(),
  likePost: vi.fn(),
  coinPost: vi.fn(),
  sharePost: vi.fn(),
  deletePost: vi.fn(),
  lookupWord: vi.fn(),
  addVocab: vi.fn(),
}))

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  return {
    ...actual,
    fetchPost: (...a: unknown[]) => api.fetchPost(...a),
    fetchComments: (...a: unknown[]) => api.fetchComments(...a),
    likePost: (...a: unknown[]) => api.likePost(...a),
    coinPost: (...a: unknown[]) => api.coinPost(...a),
    sharePost: (...a: unknown[]) => api.sharePost(...a),
    deletePost: (...a: unknown[]) => api.deletePost(...a),
  }
})

vi.mock('@/api/reading', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/reading')>()
  return {
    ...actual,
    lookupWord: (...a: unknown[]) => api.lookupWord(...a),
    addVocab: (...a: unknown[]) => api.addVocab(...a),
    wordAudioUrl: () => '/api/v1/reading/tts/word/x',
  }
})

vi.mock('@/stores/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/stores/auth')>()
  return {
    ...actual,
    useAuthStore: () => ({ me: { userId: 1, username: 'emma', nickname: 'Emma' }, fetchMe: vi.fn() }),
  }
})

async function mountDetail() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/m/post/:postId', component: MobilePostDetailView },
      { path: '/m/home', component: { template: '<div />' } },
    ],
  })
  await router.push('/m/post/42')
  await router.isReady()
  const wrapper = mount(MobilePostDetailView, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return { wrapper, router }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('帖子详情页（社区 S3）', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    api.fetchPost.mockReset().mockResolvedValue(fixtures.post)
    api.fetchComments.mockReset().mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
    api.likePost.mockReset().mockResolvedValue({ data: { liked: true, likeCount: 4 } })
    api.lookupWord.mockReset().mockResolvedValue({
      word: 'wonderful',
      matched: 'wonderful',
      phonetic: '/ˈwʌndəfl/',
      translation: 'adj. 精彩的',
      definition: null,
      pos: 'adj.',
      exchange: null,
      frequency: 900,
      in_vocab: false,
      vocab_id: null,
    })
    api.addVocab.mockReset().mockResolvedValue({ added: true, vocab: {} })
  })

  it('渲染详情：作者真实头像 + 标题正文 + 多图宫格 + 评论区', async () => {
    const { wrapper } = await mountDetail()
    expect(api.fetchPost).toHaveBeenCalledWith(42)
    expect(wrapper.text()).toContain('5 phrasal verbs')
    expect(wrapper.text()).toContain('This wonderful post is for you.')
    // 真实头像（相对路径拼 PYTHON_BASE；dev 下 PYTHON_BASE 为空 → 原样）
    expect(wrapper.get('.u-ava__img').attributes('src')).toBe('/api/v1/media/aaaa')
    // 多图宫格 2 张
    expect(wrapper.findAll('.u-media-grid__cell')).toHaveLength(2)
    expect(wrapper.text()).toContain('评论 · 2')
  })

  it('点赞：乐观更新 + 用后端返回计数收口', async () => {
    const { wrapper } = await mountDetail()
    const likeBtn = wrapper.findAll('.u-comm-action').find((b) => b.attributes('aria-label') === '点赞')
    await likeBtn?.trigger('click')
    await flushPromises()
    expect(api.likePost).toHaveBeenCalledWith(42, true)
    expect(wrapper.text()).toContain('4')
  })

  it('点图 → 灯箱打开；安卓返回键先关灯箱（不直接退页）', async () => {
    const { wrapper, router } = await mountDetail()
    await wrapper.get('.u-media-grid__cell').trigger('click')
    await flushPromises()
    expect(document.querySelector('.u-lb')).not.toBeNull()

    expect(runNativeBackHandlers()).toBe(true)
    await flushPromises()
    expect(document.querySelector('.u-lb')).toBeNull()
    expect(router.currentRoute.value.fullPath).toBe('/m/post/42')
    wrapper.unmount()
  })

  it('划词正文 → 查词卡；加入生词本带 scene=community', async () => {
    const { wrapper } = await mountDetail()

    // 模拟长按选中「wonderful」
    const textEl = wrapper.get('.u-pd__text').element as HTMLElement
    const range = document.createRange()
    const textNode = textEl.firstChild as Text
    range.setStart(textNode, 5)
    range.setEnd(textNode, 14)
    const sel = window.getSelection()!
    sel.removeAllRanges()
    sel.addRange(range)
    document.dispatchEvent(new Event('selectionchange'))
    await flushPromises()

    expect(api.lookupWord).toHaveBeenCalledWith('wonderful')
    const card = document.querySelector('.u-rd-word')
    expect(card).not.toBeNull()
    expect(card?.textContent).toContain('精彩的')

    // 加入生词本：scene=community（后端 CHECK 已含该值）
    const btn = [...card!.querySelectorAll('button')].find((b) => b.textContent?.includes('加入生词本'))
    ;(btn as HTMLButtonElement)?.click()
    await flushPromises()
    expect(api.addVocab).toHaveBeenCalledWith(
      'wonderful',
      expect.objectContaining({ scene: 'community', context: expect.stringContaining('wonderful') }),
    )
    wrapper.unmount()
  })

  it('删自己的帖 → 回社区首页', async () => {
    api.deletePost.mockResolvedValue(undefined)
    const { wrapper, router } = await mountDetail()
    await wrapper.get('button[aria-label="删除这条内容"]').trigger('click')
    await flushPromises()
    expect(api.deletePost).toHaveBeenCalledWith(42)
    expect(router.currentRoute.value.fullPath).toBe('/m/home')
  })

  it('帖子不存在（40402）→ 空态 + 返回社区', async () => {
    api.fetchPost.mockRejectedValue(Object.assign(new Error('内容不存在或已删除'), { code: 40402 }))
    const { wrapper } = await mountDetail()
    expect(wrapper.text()).toContain('内容不存在或已删除')
    expect(wrapper.text()).toContain('返回社区')
  })
})
