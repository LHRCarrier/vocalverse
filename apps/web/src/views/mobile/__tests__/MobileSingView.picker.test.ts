/**
 * `/m/sing` · 顶栏选曲入口接线测试（2026-09-21「在导航栏里集成歌曲跟唱列表」的移动端验收）。
 *
 * 覆盖：
 * - 顶栏存在 44px 选曲入口（icon-only，`aria-label` 带上「当前在唱哪首」的语义）；
 * - 点入口 → 底部弹层打开，里头是 store 的歌曲（与桌面顶栏同一份）；
 * - **在弹层里点另一首 = 切歌**：走页面既有 `openSong()`（含停录音/停原唱/门禁），
 *   弹层自动收起、跟唱面板打开且标题是该曲、`stores/sing.currentSongId` 同步更新；
 * - 2026-09-21 追加：**跟唱面板底部那一排也有「选曲」键**（用户指定落点）——
 *   面板全屏盖住顶栏时仍能一步开列表；键位共六颗（5 键 + 主钮），左右两组各占一半宽度（主钮恒居中）。
 *
 * 修复前必失败证据：改动前顶栏只有「分享」一颗按钮（`button.m-sing-pick-entry` 不存在）、
 * 底部只有五键（无 `button[aria-label="选择跟唱曲目"]`）、也无任何弹层——
 * 本文件的选择器与断言在修复前均取不到元素。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import { useSingStore } from '@/stores/sing'

import { installApiMocks, mountView, openSheet, resetEnvironment } from './singViewUtils'

vi.mock('@/api/sing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/sing')>()
  return {
    ...actual,
    fetchSongs: vi.fn(),
    fetchSongDetail: vi.fn(),
    setSongFavorite: vi.fn(),
    createSingSession: vi.fn(),
    uploadSingAudio: vi.fn(),
    fetchSingStatus: vi.fn(),
    fetchSingResult: vi.fn(),
  }
})

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, loadAudioBlob: vi.fn(async () => new Blob(['ref-audio'])) }
})

/** 弹层走 `Teleport to="body"`：从 body 上找，用例结束手动清干净（VTU unmount 不摘 teleport 节点） */
const pickRows = () => Array.from(document.body.querySelectorAll<HTMLElement>('.m-sing-pick__row'))

describe('/m/sing · 顶栏选曲入口与切歌', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetEnvironment()
    installApiMocks()
  })
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('顶栏入口默认未选曲；点开后弹层列出 store 的歌，选一首即切歌并收起', async () => {
    const w = await mountView()
    const sing = useSingStore()

    const entry = w.find('button.m-sing-pick-entry')
    expect(entry.exists()).toBe(true)
    expect(entry.attributes('aria-label')).toBe('选择跟唱曲目') // 未选曲时不谎报曲名
    expect(sing.currentSong).toBeNull()
    expect(document.body.querySelector('.u-sheet')).toBeNull()

    await entry.trigger('click')
    await flushPromises()

    const rows = pickRows()
    expect(rows).toHaveLength(3) // 与列表同一份数据（Twinkle / Mary / Ode）
    expect(rows.map((r) => r.textContent)).toEqual([
      expect.stringContaining('Twinkle'),
      expect.stringContaining('Mary Had a Little Lamb'),
      expect.stringContaining('Ode to Joy'),
    ])

    // 切歌：点第 2 首（Mary）
    rows[1]!.click()
    await flushPromises()

    expect(sing.currentSongId).toBe(2) // 选中态进 store（需求 7：其他模块可同步读取）
    expect(sing.currentSong?.title).toBe('Mary Had a Little Lamb')
    expect(document.body.querySelector('.m-sing-pick__list')).toBeNull() // 弹层收起
    expect(w.find('.m-sing-song').text()).toBe('Mary Had a Little Lamb') // 跟唱面板开的是新歌
    expect(entry.attributes('aria-label')).toContain('Mary Had a Little Lamb') // 入口语义跟着更新
  })

  it('跟唱面板底部「选曲」键：面板盖住顶栏时也能一步开列表并切歌（六键 / 两组各半宽）', async () => {
    const w = await mountView()
    const sing = useSingStore()

    await openSheet(w) // 打开跟唱面板（原唱旋律已就绪 → 点名 Twinkle）

    // 键位：左右两组各占一半宽度（主钮恒居中，见 SingActionBar 文件头注释）
    expect(w.findAll('.m-sing-dock__group')).toHaveLength(2)
    expect(w.findAll('.m-sing-dock__key')).toHaveLength(5) // 原唱 / 曲线 / 选曲 / 重录 / 完成
    expect(w.findAll('.m-sing-dock__main')).toHaveLength(1)
    expect(w.find('.m-sing-dock button[aria-label="选择跟唱曲目"]').text()).toContain('选曲')

    // 面板全屏时顶栏入口点不到（z-index 30 覆盖），底部键是唯一入口
    await w.find('.m-sing-dock button[aria-label="选择跟唱曲目"]').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.m-sing-pick__list')).not.toBeNull()

    // 选第 3 首（Ode to Joy）→ 切歌 + 弹层收起
    const rows = pickRows()
    rows[2]!.click()
    await flushPromises()

    expect(sing.currentSongId).toBe(3)
    expect(document.body.querySelector('.m-sing-pick__list')).toBeNull()
    expect(w.find('.m-sing-song').text()).toBe('Ode to Joy')
  })
})