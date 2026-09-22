/**
 * MobileSongRow（唱吧歌单行）组件测试 —— 收藏按钮（2026-09-10 组长需求）
 * + 歌单排版优化（2026-09-22 真机截图）。
 *
 * 断言点：
 * - 每首歌都有收藏按钮，且**行点击（去跟唱）与按钮点击（收藏）互不干扰**
 *   （两颗独立 button：原来的整行 button 内嵌按钮是无效 HTML）；
 * - 未收藏 → 点击 emit favorite + aria-pressed=false；已收藏 → aria-label 变「取消收藏」；
 * - **状态只写一遍**（2026-09-22）：原来「可跟唱」(20px 蓝) 与「就绪」(11px 徽标) 同源于
 *   `pitch_ref_status`，两段竖排吃掉 ~60px 横向空间、副文被截断。现在只有一颗徽标，
 *   文案是用户语言四态；本用例断言「不再出现『就绪』」——修复前必失败。
 * - 副文按用处重排：`L{难度} · {句数} 句 · {署名首段}`（artist 长串不再挤掉句数/难度）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobileSongRow from '@/components/mobile/MobileSongRow.vue'
import type { SongSummary } from '@/api/sing'

const song = (over: Partial<SongSummary> = {}): SongSummary => ({
  id: 7,
  title: 'Twinkle Twinkle Little Star',
  artist: 'Traditional',
  level: 1,
  pitch_ref_status: 'ready',
  expected_lines: 6,
  favorited: false,
  ...over,
})

describe('MobileSongRow（歌单行 + 收藏按钮）', () => {
  it('未收藏：aria-pressed=false，点击收藏按钮 emit favorite（不触发 open）', async () => {
    const w = mount(MobileSongRow, { props: { song: song() } })
    const fav = w.get('button.m-sing-fav')
    expect(fav.attributes('aria-pressed')).toBe('false')
    expect(fav.attributes('aria-label')).toBe('收藏 Twinkle Twinkle Little Star')
    expect(w.find('button.m-sing-fav.is-on').exists()).toBe(false)

    await fav.trigger('click')
    expect(w.emitted('favorite')?.[0]).toEqual([song()])
    expect(w.emitted('open')).toBeUndefined() // 收藏不能顺带进跟唱面板
  })

  it('已收藏：is-on + aria-pressed=true，标题/标签变「取消收藏」', () => {
    const w = mount(MobileSongRow, { props: { song: song({ favorited: true }) } })
    const fav = w.get('button.m-sing-fav')
    expect(fav.classes()).toContain('is-on')
    expect(fav.attributes('aria-pressed')).toBe('true')
    expect(fav.attributes('aria-label')).toBe('取消收藏 Twinkle Twinkle Little Star')
    expect(fav.attributes('title')).toBe('取消收藏')
  })

  it('主点击区 emit open(songId)（与收藏按钮分离）', async () => {
    const w = mount(MobileSongRow, { props: { song: song() } })
    await w.get('button.m-sing-row__hit').trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([7])
    expect(w.emitted('favorite')).toBeUndefined()
  })
})

describe('MobileSongRow · 状态单一化（2026-09-22 歌单排版优化）', () => {
  it('每行只有 1 个状态元素，四态文案随 pitch_ref_status 变', () => {
    const states = [
      ['ready', '可跟唱'],
      ['building', '提取中'],
      ['invalid', '提取失败'],
      ['missing', '暂不可唱'], // 未列状态回落
    ] as const
    for (const [status, text] of states) {
      const w = mount(MobileSongRow, { props: { song: song({ pitch_ref_status: status }) } })
      const badges = w.findAll('.m-sing-row__state')
      expect(badges, `${status} 应只有一颗状态徽标`).toHaveLength(1)
      expect(badges[0].text()).toBe(text)
      // 徽标带完整语义（只有 3 个字，读屏要能听懂「为什么不能唱」）
      expect(badges[0].attributes('aria-label')).toBeTruthy()
    }
  })

  it('**不再**出现与徽标重复的「就绪」/「可跟唱」大字（修复前必失败）', () => {
    const w = mount(MobileSongRow, { props: { song: song() } })
    // 旧实现：`.u-item__right` 内「可跟唱」(u-item__value) + 「就绪」(u-badge) 两段同源重复
    expect(w.find('.u-item__right').exists()).toBe(false)
    expect(w.find('.u-item__value').exists()).toBe(false)
    expect(w.text()).not.toContain('就绪')
    expect(w.findAll('.u-badge')).toHaveLength(1)
  })

  it('样式契约：副文行 flex + 徽标 flex:none + 右内边距 16px（读源文件，改回即红）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    const rule = (sel: string, next: string) => css.slice(css.indexOf(sel), css.indexOf(next))
    // 徽标不参与文本宽度分配（副文只省略中间，状态永远可见）
    const state = rule('.m-sing-row__state {', '.m-sing-fav {')
    expect(state).toContain('flex: none')
    // 副文行改横向布局（左副文 + 右徽标）——限定在 .m-sing-row 作用域内，不动共享 .u-item__sub
    const sub = rule('.m-sing-row .u-item__sub {', '.m-sing-row__meta {')
    expect(sub).toContain('display: flex')
    const meta = rule('.m-sing-row__meta {', '.m-sing-row__state {')
    expect(meta).toContain('text-overflow: ellipsis')
    expect(meta).toContain('min-width: 0')
    // 心形与卡片右缘对齐（原来 8px，贴边）
    const row = rule('.m-sing-row {', '.m-sing-row .u-badge {')
    expect(row).toContain('padding-right: 12px')
    // 副文列宽度靠「图标-文本间距 12px + 徽标内边距 8px」腾出（360 档实测 107px → 123px，
    // 「L1 · 6 句 · Traditional」需要 108px → 不再触发省略号）
    const hitRule = rule('.m-sing-row__hit {', '.m-sing-row .u-item__sub {')
    expect(hitRule).toContain('gap: 12px')
    const badgeRule = rule('.m-sing-row .u-badge {', '.m-sing-row .u-item__sub {')
    expect(badgeRule).toContain('padding: 0 8px')
  })
})

describe('MobileSongRow · 专辑封面（2026-09-22）', () => {
  it('有 cover_url → 渲染封面图（站点相对路径直接给 img，dev 下 PYTHON_BASE 为空）', () => {
    const w = mount(MobileSongRow, {
      props: { song: song({ cover_url: '/api/v1/songs/covers/twinkle.svg' }) },
    })
    const img = w.get('.m-sing-row__cover img')
    expect(img.attributes('src')).toBe('/api/v1/songs/covers/twinkle.svg')
    expect(img.attributes('alt')).toBe('') // 装饰图：歌名就在右侧，读屏不重复
    expect(w.find('.m-sing-row__cover svg').exists()).toBe(false) // 图标与封面互斥
  })

  it('无 cover_url → 退回原音符图标（未配封面的歌保持老观感）', () => {
    const w = mount(MobileSongRow, { props: { song: song({ cover_url: null }) } })
    expect(w.find('.m-sing-row__cover img').exists()).toBe(false)
    expect(w.find('.m-sing-row__cover svg').exists()).toBe(true)
  })

  it('图裂（资产缺失/离线）→ 退回音符图标，不留破图占位', async () => {
    const w = mount(MobileSongRow, {
      props: { song: song({ cover_url: '/api/v1/songs/covers/twinkle.svg' }) },
    })
    await w.get('.m-sing-row__cover img').trigger('error')
    expect(w.find('.m-sing-row__cover img').exists()).toBe(false)
    expect(w.find('.m-sing-row__cover svg').exists()).toBe(true)
  })

  it('样式契约：封面只加裁切 + 铺满，几何仍来自共享 .u-icon-block（读源文件，改回即红）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    const cover = css.slice(css.indexOf('.m-sing-row__cover {'), css.indexOf('.m-sing-row__cover img {'))
    expect(cover).toContain('overflow: hidden') // 圆角裁切（几何不在此处重定义）
    expect(cover).not.toContain('width: 48px') // 尺寸仍归共享 .u-icon-block，避免两处漂移
    const imgRule = css.slice(css.indexOf('.m-sing-row__cover img {'))
    expect(imgRule.slice(0, imgRule.indexOf('}'))).toContain('object-fit: cover')
  })
})

describe('MobileSongRow · 副文信息重排', () => {
  it('顺序为「L{难度} · {句数} 句 · {署名}」（句数/难度不再被长 artist 挤掉）', () => {
    const w = mount(
      MobileSongRow,
      { props: { song: song({ level: 3, expected_lines: 4, artist: 'Beethoven' }) } },
    )
    expect(w.find('.m-sing-row__meta').text()).toBe('L3 · 4 句 · Beethoven')
  })

  it('长 artist 只取 `·` 前第一段（制作说明不进署名）', () => {
    const w = mount(
      MobileSongRow,
      { props: { song: song({ artist: 'Traditional · 合成旋律（公有领域童谣）' }) } },
    )
    expect(w.find('.m-sing-row__meta').text()).toBe('L1 · 6 句 · Traditional')
    expect(w.find('.m-sing-row__meta').text()).not.toContain('合成旋律')
  })

  it('artist 缺失 → 回落「歌单」', () => {
    const w = mount(MobileSongRow, { props: { song: song({ artist: null }) } })
    expect(w.find('.m-sing-row__meta').text()).toBe('L1 · 6 句 · 歌单')
  })
})
