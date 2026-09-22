/**
 * SingFeaturedCard（唱吧「本周精选」深青卡）组件测试 —— 2026-09-22 真机截图问题。
 *
 * 修复前症状：meta 与标题**同处**卡片顶部那条横向带，而右上角是**绝对定位的插画**
 * （`.u-dark-card__art{right:20px;top:16px;width:104px}`）→ 长 artist 把 meta 挤成两行，
 * 第二行读作「句 · 可跟唱」，行数「6」正好被插画盖住。
 *
 * 本用例锁三件事：
 * 1. **结构**：meta 排在标题之后（不再与插画抢同一条横向带）+ 拆成「署名 / 句数·状态」两段；
 * 2. **文案**：署名只取 `·` 前第一段；就绪与否决定 chip 与状态文案；
 * 3. **样式契约**（读组件源文件）：署名可省略、「N 句 · 状态」永不省略。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SingFeaturedCard from '@/components/sing/SingFeaturedCard.vue'
import type { SongSummary } from '@/api/sing'

const song = (over: Partial<SongSummary> = {}): SongSummary => ({
  id: 1,
  title: 'Twinkle Twinkle Little Star',
  artist: 'Traditional · 合成旋律（公有领域童谣）',
  level: 1,
  pitch_ref_status: 'ready',
  expected_lines: 6,
  favorited: false,
  ...over,
})

const mountCard = (over: Partial<SongSummary> = {}) =>
  mount(SingFeaturedCard, { props: { song: song(over) } })

describe('SingFeaturedCard · 信息分层', () => {
  it('署名只取 `·` 前第一段；句数与状态各成一段（不再拼成一句长串）', () => {
    const w = mountCard()
    expect(w.find('.m-feat__artist').text()).toBe('Traditional')
    expect(w.find('.m-feat__artist').text()).not.toContain('合成旋律')
    expect(w.find('.m-feat__facts').text()).toBe('6 句 · 可跟唱')
  })

  it('未就绪：chip 变「参考旋律提取中」，状态变「稍后开放」，desc 同步换文案', () => {
    const w = mountCard({ pitch_ref_status: 'building' })
    expect(w.text()).toContain('参考旋律提取中')
    expect(w.find('.m-feat__facts').text()).toBe('6 句 · 稍后开放')
    expect(w.text()).toContain('参考旋律生成中')
  })

  it('文案精简（2026-09-22 二次优化）：删掉与页面重复的评分清单与实现词，只留约束 + 一句价值', () => {
    const ready = mountCard()
    const desc = ready.find('.m-feat__desc').text()
    expect(desc).toBe('一次最多 3 分钟，逐句评分。')
    expect(desc).toContain('3 分钟') // 硬约束保留（别处没有的信息）
    // 修复前必失败：旧文案含评分维度清单（与页面副标题/页脚公式重复）与实现词
    expect(ready.text()).not.toContain('音准/节奏/发音')
    expect(ready.text()).not.toContain('D3')
  })

  it('CTA：点「去跟唱」emit open(song.id)', async () => {
    const w = mountCard()
    const cta = w.findAll('button').find((b) => b.text().includes('去跟唱'))
    expect(cta, '应有「去跟唱」').toBeTruthy()
    await cta!.trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([1])
  })

  it('artist 缺失 → 署名回落「歌单」', () => {
    expect(mountCard({ artist: null }).find('.m-feat__artist').text()).toBe('歌单')
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

  it('meta 排在标题**之后**；署名可省略、「N 句 · 状态」永不省略', () => {
    const titleAt = src.indexOf('class="u-dark-card__title m-feat__title"')
    const metaAt = src.indexOf('class="u-dark-card__meta m-feat__meta"')
    expect(titleAt, '标题必须在模板里').toBeGreaterThan(-1)
    expect(metaAt, 'meta 必须在模板里').toBeGreaterThan(-1)
    expect(metaAt).toBeGreaterThan(titleAt)

    const style = src.slice(src.indexOf('<style scoped>'))
    const artist = style.slice(style.indexOf('.m-feat__artist {'), style.indexOf('.m-feat__facts {'))
    expect(artist).toContain('text-overflow: ellipsis')
    expect(artist).toContain('min-width: 0')
    const facts = style.slice(style.indexOf('.m-feat__facts {'), style.indexOf('.m-feat__desc {'))
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
    expect(card).toContain('padding: 18px 24px')
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

  it('信息层次（色阶 4 档）：曲名 > 关键属性 > 说明 > 署名', () => {
    const style = src.slice(src.indexOf('<style scoped>'))
    const desc = style.slice(style.indexOf('.m-feat__desc {'), style.indexOf('.m-feat__cta {'))
    expect(desc).toContain('font-size: 13px')
    expect(desc).toContain('line-height: 1.5')
    expect(desc).toContain('rgba(255, 255, 255, 0.62)')
    // 关键属性（句数/状态）比署名亮一档且半粗 —— 决策依据优先于出处
    const facts = style.slice(style.indexOf('.m-feat__facts {'), style.indexOf('.m-feat__desc {'))
    expect(facts).toContain('rgba(255, 255, 255, 0.78)')
    expect(facts).toContain('font-weight: 600')
    const artist = style.slice(style.indexOf('.m-feat__artist {'), style.indexOf('.m-feat__facts {'))
    expect(artist).toContain('rgba(255, 255, 255, 0.55)')
    // 标题仍是卡片里最大的一档（20px/600），与属性行（12px）差 8px 形成明显层级
    const title = style.slice(style.indexOf('.m-feat__title {'), style.indexOf('.m-feat__meta {'))
    expect(title).toContain('font-size: 20px')
    expect(title).toContain('font-weight: 600')
  })
})
