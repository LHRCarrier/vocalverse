/**
 * SingFeaturedCard（唱吧「本周精选」深色卡）组件测试 —— 2026-09-22 真机截图问题。
 *
 * 修复前症状：meta 与标题**同处**卡片顶部那条横向带，而右上角是**绝对定位的插画**
 * （`.u-dark-card__art{right:20px;top:16px;width:104px}`）→ 长 artist 把 meta 挤成两行，
 * 第二行读作「句 · 可跟唱」，行数「6」正好被插画盖住。
 *
 * 本用例锁四件事：
 * 1. **结构**：meta 排在标题之后 + 拆成「歌手 · 专辑 / 时长」两段；
 * 2. **文案**：meta = 歌手 · 专辑，facts = 时长；「N 句 · 可跟唱」下架；
 *    第六轮（用户口径）再删说明段——「一次最多 3 分钟，逐句评分。」不再上卡；
 * 3. **卡带**：封面贴纸（`cover_url`，图裂退音符）+ 双卷轴转动（keyframes + 动效分级降级）；
 * 4. **样式契约**（读组件源文件）：meta 左段可省略、时长段永不省略；卡带 `flex:none` 不绝对定位（防压字回归）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SingFeaturedCard from '@/components/sing/SingFeaturedCard.vue'
import type { SongSummary } from '@/api/sing'

const song = (over: Partial<SongSummary> = {}): SongSummary => ({
  id: 1,
  title: 'Twinkle Twinkle Little Star',
  artist: 'Traditional · 合成旋律（公有领域童谣）',
  album: '童谣精选集',
  level: 1,
  duration_s: 30,
  pitch_ref_status: 'ready',
  expected_lines: 6,
  favorited: false,
  cover_url: '/api/v1/songs/covers/twinkle.svg',
  ...over,
})

const mountCard = (over: Partial<SongSummary> = {}) =>
  mount(SingFeaturedCard, { props: { song: song(over) } })

describe('SingFeaturedCard · 信息分层', () => {
  it('meta = 「歌手 · 专辑」（署名只取 `·` 前第一段）；facts = 时长', () => {
    const w = mountCard()
    expect(w.find('.m-feat__artist').text()).toBe('Traditional · 童谣精选集')
    expect(w.find('.m-feat__artist').text()).not.toContain('合成旋律')
    expect(w.find('.m-feat__facts').text()).toBe('00:30')
    // 第四轮口径：练习元数据（句数/难度）与默认态「可跟唱」不再上卡
    expect(w.text()).not.toContain('6 句')
    expect(w.text()).not.toContain('可跟唱')
  })

  it('album 缺失 → meta 只有歌手，不留空分隔符', () => {
    const w = mountCard({ album: null })
    expect(w.find('.m-feat__artist').text()).toBe('Traditional')
    expect(w.find('.m-feat__artist').text()).not.toContain('·')
  })

  it('未就绪：chip 变「参考旋律提取中」（时长仍照常显示）', () => {
    const w = mountCard({ pitch_ref_status: 'building' })
    expect(w.text()).toContain('参考旋律提取中')
    expect(w.find('.m-feat__facts').text()).toBe('00:30')
  })

  it('说明段下架（2026-09-22 第六轮用户口径）：不再有 desc 段落与「一次最多 3 分钟」文案', () => {
    const w = mountCard()
    expect(w.find('.m-feat__desc').exists()).toBe(false)
    expect(w.text()).not.toContain('一次最多')
    expect(w.text()).not.toContain('逐句评分')
    expect(w.text()).not.toContain('音准/节奏/发音')
    expect(w.text()).not.toContain('D3')
  })

  it('CTA：点「去跟唱」emit open(song.id)', async () => {
    const w = mountCard()
    const cta = w.findAll('button').find((b) => b.text().includes('去跟唱'))
    expect(cta, '应有「去跟唱」').toBeTruthy()
    await cta!.trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([1])
  })

  it('artist 缺失 → 署名回落「歌单」（专辑照常拼在后面）', () => {
    expect(mountCard({ artist: null }).find('.m-feat__artist').text()).toBe('歌单 · 童谣精选集')
  })
})

describe('SingFeaturedCard · 卡带（第六轮）', () => {
  it('卡带贴纸渲染封面（cover_url 过 mediaUrl）；窗口内两个卷轴', () => {
    const w = mountCard()
    const tape = w.find('.m-feat__tape')
    expect(tape.exists()).toBe(true)
    expect(tape.attributes('aria-hidden')).toBe('true') // 装饰视觉：读屏只播标题
    const img = w.find('.m-feat__tape-label img')
    expect(img.exists()).toBe(true)
    expect(img.attributes('src')).toContain('twinkle.svg')
    expect(img.attributes('alt')).toBe('')
    expect(w.findAll('.m-feat__reel').length).toBe(2)
  })

  it('无封面 → 贴纸位退音符图标（不留破图）', () => {
    const w = mountCard({ cover_url: null })
    expect(w.find('.m-feat__tape-label img').exists()).toBe(false)
    expect(w.find('.m-feat__tape-label svg').exists()).toBe(true)
  })

  it('图裂（资产缺失/离线）→ 退音符图标', async () => {
    const w = mountCard()
    await w.find('.m-feat__tape-label img').trigger('error')
    expect(w.find('.m-feat__tape-label img').exists()).toBe(false)
    expect(w.find('.m-feat__tape-label svg').exists()).toBe(true)
  })
})

describe('SingFeaturedCard · 版式契约（插画压字回归护栏）', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { readFileSync } = require('node:fs') as typeof import('node:fs')
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { resolve } = require('node:path') as typeof import('node:path')
  const src = readFileSync(
    resolve(process.cwd(), 'src/components/sing/SingFeaturedCard.vue'),
    'utf-8',
  )

  it('meta 排在标题**之后**；左段可省略、时长段永不省略', () => {
    const titleAt = src.indexOf('class="u-dark-card__title m-feat__title"')
    const metaAt = src.indexOf('class="u-dark-card__meta m-feat__meta"')
    expect(titleAt, '标题必须在模板里').toBeGreaterThan(-1)
    expect(metaAt, 'meta 必须在模板里').toBeGreaterThan(-1)
    expect(metaAt).toBeGreaterThan(titleAt)

    const style = src.slice(src.indexOf('<style scoped>'))
    const artist = style.slice(style.indexOf('.m-feat__artist {'), style.indexOf('.m-feat__facts {'))
    expect(artist).toContain('text-overflow: ellipsis')
    expect(artist).toContain('min-width: 0')
    const facts = style.slice(style.indexOf('.m-feat__facts {'), style.indexOf('.m-feat__tape {'))
    expect(facts).toContain('flex: none')
    expect(facts).toContain('white-space: nowrap')
  })

  it('现代化重置（2026-09-22）：无装饰插画 / 无径向渐变，改为实心中性面 + 发丝边框 + 投影', () => {
    // 删装饰是本轮重置的核心口径：插画（`.u-dark-card__art`）+ 两层径向辉光一起移除
    expect(src).not.toContain('u-dark-card__art')
    expect(src).not.toContain('MobileArt')
    const style = src.slice(src.indexOf('<style scoped>'))
    expect(style).not.toContain('radial-gradient')
    const card = style.slice(style.indexOf('.m-feat {'), style.indexOf('.m-feat .u-chip {'))
    expect(card).toContain('background: #15181c') // 中性深灰面（覆盖 `.u-dark-card` 浅底与 teal 渐变）
    expect(card).toContain('border: 1px solid rgba(255, 255, 255, 0.08)') // 发丝分隔
    expect(card).toContain('box-shadow: 0 10px 30px rgba(16, 20, 24, 0.18)') // 适度投影（层次感）
  })

  it('单一强调动作：白底实心 CTA；chip 降级为发丝描边标签（不再有两个彩色元素抢焦点）', () => {
    const style = src.slice(src.indexOf('<style scoped>'))
    const cta = style.slice(style.indexOf('.m-feat__cta {'), style.indexOf('.m-feat__cta:hover'))
    expect(cta).toContain('background: #fff')
    expect(cta).toContain('color: #0d1117')
    expect(style).not.toContain('u-btn--ghost') // 白描边 ghost 在深灰面上撑不起主操作
    const chip = style.slice(style.indexOf('.m-feat .u-chip {'), style.indexOf('.m-feat__title {'))
    expect(chip).toContain('background: transparent')
    expect(chip).toContain('border: 1px solid rgba(255, 255, 255, 0.14)')
    expect(chip).toContain('letter-spacing: 0.04em')
    expect(src).not.toContain('u-chip--teal') // 旧的实心青底胶囊变体不再使用
  })

  it('信息层次（色阶）：曲名 > 时长 > 歌曲信息；标题两行截断', () => {
    const style = src.slice(src.indexOf('<style scoped>'))
    const facts = style.slice(style.indexOf('.m-feat__facts {'), style.indexOf('.m-feat__tape {'))
    expect(facts).toContain('rgba(255, 255, 255, 0.78)')
    expect(facts).toContain('font-weight: 600')
    const artist = style.slice(style.indexOf('.m-feat__artist {'), style.indexOf('.m-feat__facts {'))
    expect(artist).toContain('rgba(255, 255, 255, 0.55)')
    // 标题仍是卡片里最大的一档（20px/600），并限两行防窄列下卡片过高
    const title = style.slice(style.indexOf('.m-feat__title {'), style.indexOf('.m-feat__meta {'))
    expect(title).toContain('font-size: 20px')
    expect(title).toContain('font-weight: 600')
    expect(title).toContain('-webkit-line-clamp: 2')
  })

  it('卡带布局不做绝对定位（防「插画压字」回归）：右列 flex:none，左列可伸缩', () => {
    const style = src.slice(src.indexOf('<style scoped>'))
    const body = style.slice(style.indexOf('.m-feat__body {'), style.indexOf('.m-feat__info {'))
    expect(body).toContain('display: flex')
    expect(body).not.toContain('position: absolute')
    const info = style.slice(style.indexOf('.m-feat__info {'), style.indexOf('.m-feat .u-chip {'))
    expect(info).toContain('flex: 1')
    expect(info).toContain('min-width: 0')
    const tape = style.slice(style.indexOf('.m-feat__tape {'), style.indexOf('.m-feat__tape-label {'))
    expect(tape).toContain('flex: none')
    expect(tape).not.toContain('position: absolute') // 绝对定位只允许在卡带内部的贴纸/窗口
  })

  it('动效分级契约：卷轴转动 + `data-motion=off` 停转 / `low` 放缓', () => {
    const style = src.slice(src.indexOf('<style scoped>'))
    expect(style).toContain('@keyframes m-feat-spin')
    const reel = style.slice(style.indexOf('.m-feat__reel {'), style.indexOf('.m-feat__reel::after'))
    expect(reel).toContain('animation: m-feat-spin')
    expect(reel).toContain('linear infinite')
    expect(style).toContain("html[data-motion='off'] .m-feat__reel")
    expect(style).toContain("html[data-motion='low'] .m-feat__reel")
  })
})
