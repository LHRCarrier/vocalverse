/**
 * 阅读器交互回归（2026-09-10 · 组长手机实测三条）
 *
 * bug1：点任意词都该出查词卡（修复前只有「已加入生词本」的词有反应，其余只能长按划词）；
 *       点句子应能对整句做批注（批注 = 读者对某句/某段的理解）。
 * bug2：批注必须在正文里看得见（底色 + 笔记角标），点批注能读到内容。
 * bug3：主题切换要落到 DOM（.u-rd-views[data-theme]）——CSS 生效由无头浏览器量测守护。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
  patchAnnotation: vi.fn(),
  deleteAnnotation: vi.fn(),
  fetchAnnotations: vi.fn(),
}))

vi.mock('@/api/reading', () => ({
  fetchChapter: vi.fn(async () => fixtures.chapter),
  fetchVoices: vi.fn(async () => []),
  fetchVocab: vi.fn(async () => ({ items: [], next_cursor: null, has_more: false })),
  fetchAnnotations: (...args: unknown[]) => api.fetchAnnotations(...args),
  createAnnotation: (...args: unknown[]) => api.createAnnotation(...args),
  patchAnnotation: (...args: unknown[]) => api.patchAnnotation(...args),
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

/**
 * 批注弹层都走 `Teleport to="body"`；VTU 的 unmount 不保证摘掉 teleport 目标里的节点，
 * 残留节点会被下一条用例的 document.querySelector('.u-rd-ann') 先命中（假失败）。
 * 每条用例后清空 body，保证选择器只看到当前用例的弹层。
 */
afterEach(() => {
  document.body.innerHTML = ''
})

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

  it('单击句子 → 选中该句 + 底部动作条（高亮/批注/听这句）；再点「批注」才开弹层', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__sentence').trigger('click')
    await flushPromises()

    // 选中态 + 动作条（2026-09-10 组长拍板：不直接弹层，避免误触）
    expect(wrapper.get('.u-rd__sentence').classes()).toContain('is-selected')
    const bar = wrapper.find('.u-rd-sel') // 非 Teleport，留在组件树内
    expect(bar.exists()).toBe(true)
    expect(bar.text()).toContain('批注')
    expect(bar.text()).toContain('听这句')
    expect(document.querySelector('.u-rd-ann')).toBeNull() // 尚未开弹层

    // 点「批注」→ 批注弹层（整句范围）
    const noteBtn = wrapper.findAll('.u-rd-sel__btn').find((b) => b.text().includes('批注'))
    await noteBtn?.trigger('click')
    await flushPromises()
    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
    expect(sheet?.textContent).toContain('Alice was here.')
    wrapper.unmount()
  })

  it('动作条点色点 → 直接整句高亮（createAnnotation 收到句子范围 + 该颜色）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__sentence').trigger('click')
    await flushPromises()

    const green = wrapper.find('button[aria-label="高亮绿色"]')
    expect(green.exists()).toBe(true)
    await green.trigger('click')
    await flushPromises()

    expect(api.createAnnotation).toHaveBeenCalledTimes(1)
    const payload = api.createAnnotation.mock.calls[0][0] as Record<string, unknown>
    expect(payload.kind).toBe('highlight')
    expect(payload.color).toBe('#bbf7d0')
    expect(payload.start_offset).toBe(0)
    expect(payload.end_offset).toBe(15)
    expect(payload.sentence_idx).toBe(0)
    wrapper.unmount()
  })

  it('查词卡底部「高亮这句」→ 先出选色面板，未选色不能保存（修复前直接落默认黄，用户没得选）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__seg[data-word="Alice"]').trigger('click')
    await flushPromises()

    const card = document.querySelector('.u-rd-word')
    expect(card?.textContent).toContain('高亮这句')
    expect(card?.textContent).toContain('批注这句')

    const btn = [...card!.querySelectorAll('button')].find((b) => b.textContent?.includes('高亮这句'))
    btn?.click()
    await flushPromises()

    // 修复前：这里已经 createAnnotation 落库（默认 #fde68a）——现在必须一条都不写
    expect(api.createAnnotation).not.toHaveBeenCalled()
    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
    expect(sheet?.textContent).toContain('选择高亮颜色')
    expect(sheet?.textContent).toContain('Alice was here.')

    // 未选色 → 保存按钮禁用
    const save = [...sheet!.querySelectorAll('button')].find((b) => b.textContent?.trim() === '高亮') as HTMLButtonElement
    expect(save.disabled).toBe(true)
    save.click()
    await flushPromises()
    expect(api.createAnnotation).not.toHaveBeenCalled()

    // 选蓝色 → 保存 → 才落库（颜色 = 用户选的那一个）
    const blue = sheet!.querySelector('button[aria-label="高亮蓝色"]') as HTMLButtonElement
    expect(blue).toBeTruthy()
    blue.click()
    await flushPromises()
    ;[...sheet!.querySelectorAll('button')].find((b) => b.textContent?.trim() === '高亮')?.click()
    await flushPromises()

    expect(api.createAnnotation).toHaveBeenCalledTimes(1)
    const payload = api.createAnnotation.mock.calls[0][0] as Record<string, unknown>
    expect(payload.kind).toBe('highlight')
    expect(payload.color).toBe('#bfdbfe')
    expect(payload.start_offset).toBe(0)
    expect(payload.end_offset).toBe(15)
    expect(payload.sentence_idx).toBe(0)
    wrapper.unmount()
  })

  it('查词卡「批注这句」→ 收掉词卡并打开整句批注弹层', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__seg[data-word="Alice"]').trigger('click')
    await flushPromises()

    const btn = [...document.querySelectorAll('.u-rd-word button')].find((b) =>
      b.textContent?.includes('批注这句'),
    )
    ;(btn as HTMLButtonElement)?.click()
    await flushPromises()

    expect(document.querySelector('.u-rd-word')).toBeNull()
    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
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

  it('正文按批注色分段上色 + 句尾编号标签（修复前只有句子下划线、note 类连下划线都没有）', async () => {
    const wrapper = await mountReader()
    const seg = wrapper.get('.u-rd__seg.is-ann')
    expect(seg.text()).toContain('Alice')
    expect(seg.attributes('style')).toContain('#bbf7d0')
    expect(wrapper.find('.u-rd__senttag').exists()).toBe(true)
    expect(wrapper.get('.u-rd__sentence').classes()).toContain('is-annotated')
    wrapper.unmount()
  })

  it('点句尾编号标签 → 弹出批注内容（能看到笔记文字，不只是滚动定位）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__senttag').trigger('click')
    await flushPromises()

    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
    expect(sheet?.textContent).toContain('Alice')
    // 笔记在可编辑 textarea 里（2026-09-09 起查看即编辑），值必须预填服务端内容
    expect((sheet?.querySelector('textarea') as HTMLTextAreaElement).value).toBe('这里是主人公名字')
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

