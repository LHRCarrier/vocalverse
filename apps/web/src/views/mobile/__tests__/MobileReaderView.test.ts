/**
 * 阅读器交互回归（2026-09-10 · 组长手机实测三条）
 *
 * bug1：点任意词都该出查词卡（修复前只有「已加入生词本」的词有反应，其余只能长按划词）；
 *       点句子应能对整句做批注（批注 = 读者对某句/某段的理解）。
 * bug2：批注必须在正文里看得见（底色 + 笔记角标），点批注能读到内容。
 * bug3：主题切换要落到 DOM（.u-rd-views[data-theme]）——CSS 生效由无头浏览器量测守护。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import MobileReaderView from '@/views/mobile/MobileReaderView.vue'

const fixtures = vi.hoisted(() => ({
  chapter: {
    id: 7,
    book_id: 1,
    chapter_no: 1,
    title: 'Chapter I',
    content_version: 1,
    content: 'Alice was here.',
    paragraphs: ['Alice was here.'],
    sentences: [{ idx: 0, text: 'Alice was here.', para_idx: 0, start: 0, end: 15 }],
    word_count: 3,
    char_count: 15,
  },
  /** 一条「笔记批注」：覆盖 Alice（绝对 offset 0..5） */
  noteAnn: {
    id: 11,
    kind: 'note' as const,
    start_offset: 0,
    end_offset: 5,
    content_version: 1,
    sentence_idx: 0,
    text_snippet: 'Alice',
    note: '这里是主人公名字',
    color: '#bbf7d0',
    created_at: '2026-09-10T10:00:00Z',
    updated_at: null,
  },
}))

const api = vi.hoisted(() => ({
  lookupWord: vi.fn(),
  createAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
  fetchAnnotations: vi.fn(),
}))

vi.mock('@/api/reading', () => ({
  fetchChapter: vi.fn(async () => fixtures.chapter),
  fetchVoices: vi.fn(async () => []),
  fetchVocab: vi.fn(async () => ({ items: [], next_cursor: null, has_more: false })),
  fetchAnnotations: (...args: unknown[]) => api.fetchAnnotations(...args),
  createAnnotation: (...args: unknown[]) => api.createAnnotation(...args),
  deleteAnnotation: (...args: unknown[]) => api.deleteAnnotation(...args),
  lookupWord: (...args: unknown[]) => api.lookupWord(...args),
  addVocab: vi.fn(),
  saveProgress: vi.fn(async () => undefined),
  segmentAudioUrl: vi.fn(() => ''),
  loadSegmentAudio: vi.fn(),
  prepareChapter: vi.fn(),
}))

function makeRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/m/reader/:chapterId', component: MobileReaderView },
      { path: '/m/books/:bookId', component: { template: '<div />' } },
    ],
  })
}

async function mountReader() {
  const router = makeRouter()
  await router.push('/m/reader/7?book=1')
  await router.isReady()
  const wrapper = mount(MobileReaderView, { global: { plugins: [router, createPinia()] } })
  await flushPromises()
  return wrapper
}

describe('阅读器 · 点词查义（bug1）', () => {
  beforeEach(() => {
    localStorage.clear()
    api.lookupWord.mockReset()
    api.lookupWord.mockResolvedValue({
      word: 'Alice',
      matched: 'alice',
      phonetic: '/ˈælɪs/',
      translation: 'n. 爱丽丝',
      definition: null,
      pos: 'n.',
      exchange: null,
      frequency: 1200,
      in_vocab: false,
      vocab_id: null,
    })
    api.fetchAnnotations.mockReset()
    api.fetchAnnotations.mockResolvedValue([])
    api.createAnnotation.mockReset()
    api.createAnnotation.mockResolvedValue({})
  })

  it('点任意词（未加入生词本）→ 查词卡 + 有「加入生词本」按钮（修复前无反应）', async () => {
    const wrapper = await mountReader()
    const alice = wrapper.get('.u-rd__seg[data-word="Alice"]')
    // 修复前：只有 .is-word（已在生词本）才可点 → 这里断言「不是生词标记也能点」
    expect(alice.classes()).not.toContain('is-word')

    await alice.trigger('click')
    await flushPromises()

    expect(api.lookupWord).toHaveBeenCalledWith('Alice')
    const card = document.querySelector('.u-rd-word')
    expect(card).not.toBeNull()
    expect(card?.textContent).toContain('爱丽丝')
    expect(card?.textContent).toContain('加入生词本')
    wrapper.unmount()
  })

  it('点句子（非听书态）→ 打开整句批注弹层（批注针对句子，不再强制长按划词）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__sentence').trigger('click')
    await flushPromises()

    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
    expect(sheet?.textContent).toContain('添加批注')
    expect(sheet?.textContent).toContain('Alice was here.')
    wrapper.unmount()
  })
})

describe('阅读器 · 批注可见（bug2）', () => {
  beforeEach(() => {
    localStorage.clear()
    api.fetchAnnotations.mockReset()
    api.fetchAnnotations.mockResolvedValue([fixtures.noteAnn])
    api.lookupWord.mockReset()
    api.createAnnotation.mockReset()
  })

  it('正文按批注色分段上色 + 笔记角标（修复前只有句子下划线、note 类连下划线都没有）', async () => {
    const wrapper = await mountReader()
    const seg = wrapper.get('.u-rd__seg.is-ann')
    expect(seg.text()).toContain('Alice')
    expect(seg.attributes('style')).toContain('#bbf7d0')
    expect(wrapper.find('.u-rd__annmark').exists()).toBe(true)
    expect(wrapper.get('.u-rd__sentence').classes()).toContain('is-annotated')
    wrapper.unmount()
  })

  it('点批注角标 → 弹出批注内容（能看到笔记文字，不只是滚动定位）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__annmark').trigger('click')
    await flushPromises()

    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
    expect(sheet?.textContent).toContain('这里是主人公名字')
    expect(sheet?.textContent).toContain('Alice')
    wrapper.unmount()
  })

  it('被批注的词：点词仍走查词（查词优先），读笔记走角标', async () => {
    api.lookupWord.mockResolvedValue({
      word: 'Alice',
      matched: 'alice',
      phonetic: null,
      translation: 'n. 爱丽丝',
      definition: null,
      pos: null,
      exchange: null,
      frequency: null,
      in_vocab: false,
      vocab_id: null,
    })
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__seg.is-ann').trigger('click')
    await flushPromises()
    expect(api.lookupWord).toHaveBeenCalledWith('Alice')
    expect(document.querySelector('.u-rd-word')).not.toBeNull()
    wrapper.unmount()
  })
})

describe('阅读器 · 主题切换落到 DOM（bug3）', () => {
  beforeEach(() => {
    localStorage.clear()
    api.fetchAnnotations.mockResolvedValue([])
    api.lookupWord.mockReset()
    api.createAnnotation.mockReset()
  })

  it('设置里选「暗黑」→ .u-rd-views[data-theme=night]（底色/墨色由 CSS 变量跟随）', async () => {
    const wrapper = await mountReader()
    expect(wrapper.get('.u-rd-views').attributes('data-theme')).toBe('paper')

    // 打开设置弹层 → 点「暗黑」
    await wrapper.get('button[aria-label="设置"]').trigger('click')
    await flushPromises()
    const nightBtn = [...document.querySelectorAll<HTMLButtonElement>('.u-rd-settings__chip')].find(
      (b) => b.textContent?.trim() === '暗黑',
    )
    expect(nightBtn).toBeTruthy()
    nightBtn?.click()
    await flushPromises()

    expect(wrapper.get('.u-rd-views').attributes('data-theme')).toBe('night')
    expect(localStorage.getItem('vv_rd_theme')).toBe('night')
    wrapper.unmount()
  })
})
