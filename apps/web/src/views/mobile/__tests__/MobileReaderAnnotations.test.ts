/**
 * 阅读器 · 批注「可查看 / 可编辑」回归（2026-09-09 组长手机实测读书域系列）
 *
 * 四条缺陷各自一条「修复前必红」的断言（HEAD 63fcaee 上实测：本文件 6 条用例全红）：
 *   Bug1 已批注句子颜色/内容都改不了（只能删除）→ 弹层必须可改色改笔记并走 PATCH；
 *   Bug2 查看已批注句子只能点空格（命中区 4.6px）→ 句首批注角标（任何 kind 都有）；
 *   Bug3 暗黑模式批注「浅粉底 + 浅灰字」不可读 → 底色走 --ur-ann-color + 主题混色
 *        （对比度门禁另见 `src/styles/__tests__/reader-annotation-contrast.test.ts`）；
 *   Bug4 点「高亮这句」不等选色就落默认色 → 先出选色面板（用例在 MobileReaderView.test.ts）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'

import MobileReaderView from '@/views/mobile/MobileReaderView.vue'
import { runNativeBackHandlers } from '@/composables/useNativeBack'

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

/** 批注弹层都走 Teleport to="body"；VTU unmount 不保证摘掉 teleport 节点，残留会被下条用例先命中 */
afterEach(() => {
  document.body.innerHTML = ''
})

describe('阅读器 · 批注可查看可编辑（2026-09-09 系列）', () => {
  beforeEach(() => {
    localStorage.clear()
    api.fetchAnnotations.mockReset()
    api.fetchAnnotations.mockResolvedValue([fixtures.noteAnn])
    api.createAnnotation.mockReset()
    api.patchAnnotation.mockReset()
    api.patchAnnotation.mockResolvedValue({ ...fixtures.noteAnn, note: '改了' })
    api.lookupWord.mockReset()
  })

  it('Bug2：句首有批注角标（任何 kind 都有），点击即看批注内容', async () => {
    const wrapper = await mountReader()
    const mark = wrapper.find('.u-rd__sentmark')
    expect(mark.exists()).toBe(true)
    expect(mark.attributes('aria-label')).toContain('查看这句的批注')
    // 角标颜色走白名单变量，不是裸 background
    expect(mark.attributes('style')).toContain('--ur-ann-color')
    expect(mark.attributes('style')).toContain('#bbf7d0')

    await mark.trigger('click')
    await flushPromises()
    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet).not.toBeNull()
    expect((sheet?.querySelector('textarea') as HTMLTextAreaElement).value).toBe('这里是主人公名字')
    wrapper.unmount()
  })

  it('Bug2：纯高亮批注（kind=highlight，无笔记）也有句首角标（修复前完全无标记）', async () => {
    api.fetchAnnotations.mockResolvedValue([
      { ...fixtures.noteAnn, id: 12, kind: 'highlight' as const, note: null, color: '#fbcfe8' },
    ])
    const wrapper = await mountReader()
    expect(wrapper.find('.u-rd__annmark').exists()).toBe(false) // 段尾笔记角标不出现
    expect(wrapper.find('.u-rd__sentmark').exists()).toBe(true) // 句首角标必须出现
    wrapper.unmount()
  })

  it('Bug2：同句多条批注 → 角标打开「本句批注」列表', async () => {
    api.fetchAnnotations.mockResolvedValue([
      fixtures.noteAnn,
      { ...fixtures.noteAnn, id: 13, kind: 'highlight' as const, note: null, start_offset: 6, end_offset: 9 },
    ])
    const wrapper = await mountReader()
    expect(wrapper.get('.u-rd__sentmark').classes()).toContain('is-multi')
    await wrapper.get('.u-rd__sentmark').trigger('click')
    await flushPromises()

    const sheet = document.querySelector('.u-rd-ann')
    expect(sheet?.textContent).toContain('本句批注')
    expect(sheet?.querySelectorAll('.u-rd-annlist__row').length).toBe(2)
    wrapper.unmount()
  })

  it('Bug1：批注弹层可改色 + 改笔记，保存走 PATCH（修复前只有「删除」）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__sentmark').trigger('click')
    await flushPromises()

    const sheet = document.querySelector('.u-rd-ann')!
    // 编辑态预填服务端值
    const textarea = sheet.querySelector('textarea') as HTMLTextAreaElement
    expect(textarea.value).toBe('这里是主人公名字')

    // 改色 → 蓝
    ;(sheet.querySelector('button[aria-label="改为蓝色"]') as HTMLButtonElement).click()
    await flushPromises()
    // 改笔记
    textarea.value = '改了笔记'
    textarea.dispatchEvent(new Event('input'))
    await flushPromises()

    const save = [...sheet.querySelectorAll('button')].find((b) => b.textContent?.trim() === '保存修改')
    ;(save as HTMLButtonElement).click()
    await flushPromises()

    expect(api.patchAnnotation).toHaveBeenCalledTimes(1)
    const [id, patch] = api.patchAnnotation.mock.calls[0] as [number, Record<string, unknown>]
    expect(id).toBe(11)
    expect(patch.color).toBe('#bfdbfe')
    expect(patch.note).toBe('改了笔记')
    expect(patch.kind).toBe('note')
    wrapper.unmount()
  })

  it('Bug1：笔记清空 → kind 回落 highlight（避免「note 但没有笔记」的脏数据）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__sentmark').trigger('click')
    await flushPromises()

    const sheet = document.querySelector('.u-rd-ann')!
    const textarea = sheet.querySelector('textarea') as HTMLTextAreaElement
    textarea.value = '   '
    textarea.dispatchEvent(new Event('input'))
    await flushPromises()
    ;[...sheet.querySelectorAll('button')]
      .find((b) => b.textContent?.trim() === '保存修改')
      ?.dispatchEvent(new Event('click'))
    await flushPromises()

    expect(api.patchAnnotation).toHaveBeenCalledTimes(1)
    expect((api.patchAnnotation.mock.calls[0][1] as Record<string, unknown>).kind).toBe('highlight')
    wrapper.unmount()
  })

  it('Bug3：批注底色不再裸写 background，非法色回退默认（不再污染 CSS 变量）', async () => {
    api.fetchAnnotations.mockResolvedValue([{ ...fixtures.noteAnn, color: 'red; background:url(x)' }])
    const wrapper = await mountReader()
    const style = wrapper.get('.u-rd__seg.is-ann').attributes('style') ?? ''
    expect(style).toContain('--ur-ann-color: #fde68a')
    expect(style).not.toContain('background:url')
    wrapper.unmount()
  })

  it('安卓返回键：先关批注弹层，再交给原生回退（新增弹层必须进 useReaderBackLayers 层序）', async () => {
    const wrapper = await mountReader()
    await wrapper.get('.u-rd__sentmark').trigger('click')
    await flushPromises()
    expect(document.querySelector('.u-rd-ann')).not.toBeNull()

    // 原生壳调 window.__vvNativeBack() → 走 useReaderBackLayers 的层序
    expect(runNativeBackHandlers()).toBe(true)
    await flushPromises()
    expect(document.querySelector('.u-rd-ann')).toBeNull()
    // 弹层已关 → 再按返回则未消费（交给原生回退历史）
    expect(runNativeBackHandlers()).toBe(false)
    wrapper.unmount()
  })
})
