/**
 * MobileSongRow（唱吧歌单行）组件测试 —— 收藏按钮（2026-09-10 组长需求）
 * + 歌单排版优化（2026-09-22 真机截图 · 含第三轮 QQ 音乐式改版）。
 *
 * 断言点：
 * - 每首歌都有收藏按钮，且**行点击（去跟唱）与按钮点击（收藏）互不干扰**
 *   （两颗独立 button：原来的整行 button 内嵌按钮是无效 HTML）；
 * - 未收藏 → 点击 emit favorite + aria-pressed=false；已收藏 → aria-label 变「取消收藏」；
 * - **状态徽标整体下架**（2026-09-22 第五轮，用户口径「暂不可唱必须去掉，因为我们上架歌曲
 *   必须是可唱的，这是逻辑问题」）：ready / 提取中 / 提取失败 / 暂不可唱 **都不再上卡片**，
 *   曲库只上架可唱的曲子（导入即生成歌词时间轴 + 参考旋律，见 `local/_make_songs_singable.py`）；
 *   服务端 40905 门禁仍在（异常态点击 toast，不在卡片展示）。修复前必失败：旧实现会渲染徽标。
 * - 副文 = **歌曲信息**（2026-09-22 第四轮，用户口径「把这个 L2 L3 这类删掉，还有『几句』
 *   这种，卡片上应该是歌曲信息」）：`歌手 · 专辑`（专辑可空，缺省不留分隔符）+ 右端**时长**；
 *   难度与句数不再上卡片。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobileSongRow from '@/components/mobile/MobileSongRow.vue'
import type { SongSummary } from '@/api/sing'

const song = (over: Partial<SongSummary> = {}): SongSummary => ({
  id: 7,
  title: 'Twinkle Twinkle Little Star',
  artist: 'Traditional',
  album: '童谣精选集',
  level: 1,
  duration_s: 30,
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

describe('MobileSongRow · 状态徽标整体下架（2026-09-22 第五轮）', () => {
  it('任何 pitch_ref_status 都不渲染徽标，也不出现「可跟唱/就绪/暂不可唱」字样（修复前必失败）', () => {
    for (const status of ['ready', 'building', 'invalid', 'missing'] as const) {
      const w = mount(MobileSongRow, { props: { song: song({ pitch_ref_status: status }) } })
      expect(w.findAll('.m-sing-row__state'), `${status} 不应有徽标`).toHaveLength(0)
      expect(w.findAll('.u-badge'), `${status} 不应有 u-badge`).toHaveLength(0)
      expect(w.text()).not.toContain('可跟唱')
      expect(w.text()).not.toContain('就绪')
      expect(w.text()).not.toContain('暂不可唱')
      expect(w.find('.u-item__right').exists()).toBe(false)
      expect(w.find('.u-item__value').exists()).toBe(false)
    }
  })

  it('样式契约：副文行 flex + 时长 flex:none + 行内边距 8/12/20（读源文件，改回即红）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    const rule = (sel: string, next: string) => css.slice(css.indexOf(sel), css.indexOf(next))
    // 行高 72px = 封面 56 + 上下 8（QQ 音乐式紧凑行）
    const row = rule('.m-sing-row {', '.m-sing-row__hit {')
    expect(row).toContain('padding: 8px 12px 8px 20px')
    // 时长不参与文本宽度分配（副文只省略中间）
    const dur = rule('.m-sing-row__dur {', '.m-sing-row__cover {')
    expect(dur).toContain('flex: none')
    expect(dur).toContain('tabular-nums')
    // 副文行改横向布局（左副文 + 右时长）——限定在 .m-sing-row 作用域内，不动共享 .u-item__sub
    const sub = rule('.m-sing-row .u-item__sub {', '.m-sing-row__meta {')
    expect(sub).toContain('display: flex')
    const meta = rule('.m-sing-row__meta {', '.m-sing-row__dur {')
    expect(meta).toContain('text-overflow: ellipsis')
    expect(meta).toContain('min-width: 0')
    // 徽标类名与样式必须已从本页下架（防回流）
    expect(css).not.toContain('.m-sing-row__state')
    expect(css).not.toContain('.m-sing-row .u-badge')
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

  it('样式契约：封面 56×56/圆角 12 在本页作用域内定义 + 图片铺满（读源文件，改回即红）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    const cover = css.slice(css.indexOf('.m-sing-row__cover {'), css.indexOf('.m-sing-row__cover img {'))
    expect(cover).toContain('width: 56px')
    expect(cover).toContain('border-radius: 12px')
    expect(cover).toContain('overflow: hidden') // 圆角裁切
    const imgRule = css.slice(css.indexOf('.m-sing-row__cover img {'))
    expect(imgRule.slice(0, imgRule.indexOf('}'))).toContain('object-fit: cover')
  })
})

describe('MobileSongRow · 副文 = 歌曲信息（2026-09-22 第四轮）', () => {
  it('顺序为「歌手 · 专辑」（难度 Lx 与句数不再上卡片）', () => {
    const w = mount(
      MobileSongRow,
      { props: { song: song({ level: 3, expected_lines: 4, artist: 'Beethoven' }) } },
    )
    expect(w.find('.m-sing-row__meta').text()).toBe('Beethoven · 童谣精选集')
    expect(w.find('.m-sing-row__meta').text()).not.toContain('L3')
    expect(w.find('.m-sing-row__meta').text()).not.toContain('4 句')
  })

  it('长 artist 只取 `·` 前第一段（制作说明不进署名）', () => {
    const w = mount(
      MobileSongRow,
      { props: { song: song({ artist: 'Traditional · 合成旋律（公有领域童谣）' }) } },
    )
    expect(w.find('.m-sing-row__meta').text()).toBe('Traditional · 童谣精选集')
    expect(w.find('.m-sing-row__meta').text()).not.toContain('合成旋律')
  })

  it('artist 缺失 → 回落「歌单」；album 缺失 → 不留空分隔符', () => {
    const w = mount(MobileSongRow, { props: { song: song({ artist: null }) } })
    expect(w.find('.m-sing-row__meta').text()).toBe('歌单 · 童谣精选集')
    const wNoAlbum = mount(MobileSongRow, { props: { song: song({ album: null }) } })
    expect(wNoAlbum.find('.m-sing-row__meta').text()).toBe('Traditional')
    expect(wNoAlbum.find('.m-sing-row__meta').text()).not.toContain('·')
  })

  it('时长：`duration_s` 秒 → `mm:ss`；缺失时不留 `--:--` 占位', () => {
    const w = mount(MobileSongRow, { props: { song: song({ duration_s: 65 }) } })
    expect(w.find('.m-sing-row__dur').text()).toBe('01:05')
    const wNull = mount(MobileSongRow, { props: { song: song({ duration_s: null }) } })
    expect(wNull.find('.m-sing-row__dur').exists()).toBe(false)
  })
})
