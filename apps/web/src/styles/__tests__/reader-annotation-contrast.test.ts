/**
 * 阅读器 · 批注底色对比度门禁（2026-09-09 修复「暗黑模式下批注为粉色看不清」）
 *
 * 缺陷根因：渲染层把用户选的浅粉（#fbcfe8）**直接**当底色，night 主题墨色是浅灰
 * （--ur-theme-ink #d6d3cc）→ 对比度 ≈1.6，正文等于不可读。
 * 修复方式：底色改为 `color-mix(in srgb, <批注色> var(--ur-ann-mix), var(--ur-theme-paper))`，
 * 文字统一 --ur-theme-ink。
 *
 * 本测试**直接解析 CSS 源文件**（而不是断言某一行字符串），对「三主题 × 色板全色」
 * 逐一算 WCAG 对比度，低于 4.5 即红——任何一次调低 --ur-ann-mix 或改深主题墨色都会被拦住。
 * 修复前该用例必然失败（night 主题浅粉底 + 浅灰字 ≈1.6）。
 */
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

import { ANN_FALLBACK_COLOR, ANNOTATION_COLORS, safeAnnColor } from '@/audio/annotation-colors'

// happy-dom 环境下 import.meta.url 不是 file: 协议 → 用 vitest 的 cwd（apps/web）定位源文件
const css = readFileSync(resolve(process.cwd(), 'src/styles/reader-uic.css'), 'utf-8')

/** 提取某个选择器块的 `--var: value` 声明 */
function varsOf(selector: string): Record<string, string> {
  const start = css.indexOf(selector)
  expect(start, `CSS 缺少选择器 ${selector}`).toBeGreaterThan(-1)
  const open = css.indexOf('{', start)
  const close = css.indexOf('}', open)
  const body = css.slice(open + 1, close)
  const out: Record<string, string> = {}
  for (const m of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) out[m[1]] = m[2].trim()
  return out
}

/** 实际可渲染的批注色集合 = 色板（safeAnnColor 之外的色进不了 DOM，见下方用例） */
function palette(): string[] {
  const colors = ANNOTATION_COLORS.map((c) => c.value)
  expect(colors.length).toBeGreaterThanOrEqual(4)
  return colors
}

function rgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)) as [number, number, number]
}

/** CSS `color-mix(in srgb, a p%, b)` 的 sRGB 线性插值 */
function mix(fg: string, pct: number, bg: string): [number, number, number] {
  const a = rgb(fg)
  const b = rgb(bg)
  const t = pct / 100
  return [0, 1, 2].map((i) => a[i] * t + b[i] * (1 - t)) as [number, number, number]
}

/** WCAG 相对亮度 */
function luminance([r, g, b]: [number, number, number]): number {
  const lin = [r, g, b].map((v) => {
    const s = v / 255
    return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4
  })
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
}

/** WCAG 对比度（1..21） */
function contrast(a: [number, number, number], b: [number, number, number]): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

const THEMES: Array<[string, string]> = [
  ['paper', '.u-rd-views {'],
  ['cream', ".u-rd-views[data-theme='cream']"],
  ['night', ".u-rd-views[data-theme='night']"],
]

describe('批注底色对比度（三主题 × 色板全色 ≥ 4.5 · WCAG AA 正文）', () => {
  it('每个主题都声明了 --ur-ann-mix 与纸面/墨色', () => {
    for (const [name, sel] of THEMES) {
      const vars = varsOf(sel)
      // cream/night 继承未覆盖的变量，这里只校验三主题各自显式声明的关键项
      if (name !== 'paper') {
        expect(vars['--ur-ann-mix'], `${name} 缺 --ur-ann-mix`).toBeDefined()
      } else {
        expect(vars['--ur-ann-mix']).toBeDefined()
        expect(vars['--ur-theme-paper']).toBeDefined()
        expect(vars['--ur-theme-ink']).toBeDefined()
      }
    }
  })

  it.each(THEMES)('%s 主题：批注色混底后墨色对比度 ≥ 4.5（修复前 night ≈1.6）', (name, sel) => {
    const base = varsOf('.u-rd-views {')
    const override = varsOf(sel)
    const paper = override['--ur-theme-paper'] ?? base['--ur-theme-paper']
    const ink = override['--ur-theme-ink'] ?? base['--ur-theme-ink']
    const mixPct = parseFloat((override['--ur-ann-mix'] ?? base['--ur-ann-mix']).replace('%', ''))

    expect(paper).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(ink).toMatch(/^#[0-9a-fA-F]{6}$/)
    expect(mixPct).toBeGreaterThan(0)

    for (const color of palette()) {
      const bg = mix(color, mixPct, paper)
      const ratio = contrast(rgb(ink), bg)
      expect(
        ratio,
        `${name} 主题 · 批注色 ${color} · mix ${mixPct}% → 底色 rgb(${bg.map((v) => Math.round(v)).join(',')}) 对比度 ${ratio.toFixed(2)} < 4.5`,
      ).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('批注段用 --ur-ann-color + color-mix（不再把原始色直接当 background）', () => {
    const seg = css.slice(css.indexOf('.u-rd__seg.is-ann'), css.indexOf('.u-rd__seg.is-flash'))
    expect(seg).toContain('color-mix(')
    expect(seg).toContain('var(--ur-ann-color')
    expect(seg).toContain('color: var(--ur-theme-ink)')
    // 兜底：不支持 color-mix 的旧内核也要有可用底色
    expect(css).toContain('@supports not (background: color-mix(')
  })

  /**
   * 对比度门禁的覆盖范围必须等于「实际可能渲染的颜色集合」。
   * 上面按色板算对比度，只有在本用例成立时才等价于「任意后端返回值都安全」：
   * safeAnnColor 把色板外的颜色（含 #ffffff 这类在 night 主题下 30% 混色仅 4.16 的色）拦回默认色。
   */
  it('safeAnnColor 只放行色板内的颜色（否则上面的对比度门禁覆盖不到真实渲染集）', () => {
    for (const c of palette()) expect(safeAnnColor(c)).toBe(c)
    for (const bad of ['#ffffff', '#ffff00', '#000000', '#123456', 'red', 'rgb(1,2,3)', '', null, undefined]) {
      expect(safeAnnColor(bad as string | null | undefined)).toBe(ANN_FALLBACK_COLOR)
    }
  })

  it('最坏情况兜底：色板外任意亮色被拦回默认色后，night 主题对比度仍 ≥ 4.5', () => {
    const base = varsOf('.u-rd-views {')
    const night = varsOf(".u-rd-views[data-theme='night']")
    const paper = night['--ur-theme-paper'] ?? base['--ur-theme-paper']
    const ink = night['--ur-theme-ink'] ?? base['--ur-theme-ink']
    const mixPct = parseFloat((night['--ur-ann-mix'] ?? base['--ur-ann-mix']).replace('%', ''))
    // 用户以为选了纯白/纯黄，实际渲染的是被拦回来的默认色 → 必须可读
    for (const requested of ['#ffffff', '#ffff00']) {
      const rendered = safeAnnColor(requested)
      const ratio = contrast(rgb(ink), mix(rendered, mixPct, paper))
      expect(ratio, `请求色 ${requested} → 渲染 ${rendered} 对比度 ${ratio.toFixed(2)}`).toBeGreaterThanOrEqual(4.5)
    }
  })
})
