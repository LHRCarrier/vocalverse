/**
 * SingSongPickerSheet（移动端跟唱曲目选择弹层）—— 移动侧的导航栏选曲验收。
 *
 * 覆盖：
 * - 关闭时不渲染；打开才拉列表（懒加载）；
 * - 行内三要素：歌名 / 歌手（只取 `·` 前第一段）/ 难度 `L{level}`；
 * - **6 首 → 6 行全渲染**（靠容器滚动，不砍数据），列表容器 = `.m-sing-pick__list`；
 * - 选中项 `aria-current` + `.is-on`；点击 emit `select`（并请求关闭弹层）；
 * - 加载失败显错误文案 + 重试可用；
 * - **CSS 结构门禁**（读源文件，同 `styles/__tests__/reader-annotation-contrast.test.ts` 做法）：
 *   「超过 5 首才出滚动条」= 行高 44px × 5 = 列表 max-height，且行高必须取同一变量。
 *
 * 修复前必失败证据：改动前不存在本组件（移动端无任何选曲弹层），以下选择器全部取不到元素。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

import SingSongPickerSheet from '@/components/sing/SingSongPickerSheet.vue'
import { useSingStore } from '@/stores/sing'
import type { SongSummary } from '@/api/sing'

vi.mock('@/api/sing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/sing')>()
  return { ...actual, fetchSongs: vi.fn() }
})

import { fetchSongs } from '@/api/sing'

const mockedFetchSongs = vi.mocked(fetchSongs)

function song(id: number, over: Partial<SongSummary> = {}): SongSummary {
  return {
    id,
    title: `曲目 ${id}`,
    artist: 'Traditional · 合成旋律（公有领域童谣）',
    level: id,
    pitch_ref_status: 'ready',
    expected_lines: 4,
    favorited: false,
    ...over,
  } as SongSummary
}

async function mountSheet(open = true) {
  setActivePinia(createPinia())
  const wrapper = mount(SingSongPickerSheet, {
    props: { open },
    global: { stubs: { teleport: true } },
  })
  await flushPromises()
  return wrapper
}

describe('SingSongPickerSheet（移动端选曲弹层）', () => {
  beforeEach(() => {
    localStorage.clear()
    mockedFetchSongs.mockReset()
  })

  it('关闭时不渲染、不发请求；打开才懒加载列表', async () => {
    mockedFetchSongs.mockResolvedValue([song(1)])
    const wrapper = await mountSheet(false)

    expect(wrapper.find('.u-sheet').exists()).toBe(false)
    expect(mockedFetchSongs).not.toHaveBeenCalled()

    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(mockedFetchSongs).toHaveBeenCalledTimes(1)
    expect(wrapper.findAll('.m-sing-pick__row')).toHaveLength(1)
  })

  it('每行：歌名 / 歌手 / 难度 L{level}；6 首时 6 行全在（靠容器滚动不砍数据）', async () => {
    mockedFetchSongs.mockResolvedValue([1, 2, 3, 4, 5, 6].map((i) => song(i)))
    const wrapper = await mountSheet()

    const rows = wrapper.findAll('.m-sing-pick__row')
    expect(rows).toHaveLength(6)
    expect(rows[0]!.text()).toContain('曲目 1')
    expect(rows[0]!.text()).toContain('Traditional') // artist 只取 `·` 前第一段
    expect(rows[0]!.text()).not.toContain('合成旋律')
    expect(rows[2]!.text()).toContain('L3') // 难度标识
    expect(wrapper.find('.m-sing-pick__list').exists()).toBe(true)
    expect(wrapper.text()).toContain('当前跟唱：未选曲') // 未选时的兜底文案
  })

  it('选中项 aria-current + is-on；点击别首 emit select 并请求关闭', async () => {
    mockedFetchSongs.mockResolvedValue([song(1), song(2)])
    const wrapper = await mountSheet()
    const sing = useSingStore()
    sing.selectSong(2)
    await flushPromises()

    const rows = wrapper.findAll('.m-sing-pick__row')
    expect(rows[1]!.attributes('aria-current')).toBe('true')
    expect(rows[1]!.classes()).toContain('is-on')
    expect(rows[0]!.attributes('aria-current')).toBeUndefined()
    expect(wrapper.text()).toContain('当前跟唱：曲目 2') // 弹层副标题与列表同源

    await rows[0]!.trigger('click')
    expect(wrapper.emitted('select')).toEqual([[1]])
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })

  it('列表失败：显示原因 + 重试按钮（重试成功即出列表）', async () => {
    mockedFetchSongs.mockRejectedValue(new Error('network down'))
    const wrapper = await mountSheet()

    expect(wrapper.text()).toContain('network down')
    const retry = wrapper.findAll('button').find((b) => b.text() === '重试')!
    expect(retry).toBeTruthy()

    mockedFetchSongs.mockResolvedValue([song(9)])
    await retry.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.m-sing-pick__row')).toHaveLength(1)
  })

  it('CSS 门禁：「超过 5 首才出滚动条」= 44px 行高 × 5，且行高与上限同源', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')

    expect(css).toContain('--m-sing-pick-row: 44px') // 44 = 仓库触控最小尺寸
    expect(css).toContain('max-height: calc(var(--m-sing-pick-row) * 5)') // 5 行封顶
    // 行高必须取同一变量：否则改行高会出现「滚动条在 4 首就出现 / 6 首还没出现」的错位
    const rowBlock = css.slice(css.indexOf('.m-sing-pick__row {'))
    expect(rowBlock.slice(0, rowBlock.indexOf('}'))).toContain('height: var(--m-sing-pick-row)')
    expect(css).toContain('overflow-y: auto')
  })

  it('深色口径（2026-09-22）：弹层自带 --sing-* token 与深底，且不再吃浅色卡片底', () => {
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    const block = css.slice(
      css.indexOf('.m-sing-pick {'),
      css.indexOf('.m-sing-pick .u-sheet__title'),
    )
    expect(block).toContain('--sing-bg: #0b1114') // 与 .m-sing-sheet 同族色值
    expect(block).toContain('color-scheme: dark') // 原生滚动条跟着转深
    // 弹层 Teleport 到 body → 继承不到面板那组 token，必须自带；也不该再引用浅色 token
    expect(block).not.toContain('var(--u-card)')
    expect(block).not.toContain('var(--u-track')
  })
})