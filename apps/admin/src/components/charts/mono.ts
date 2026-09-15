/**
 * Monaco 图表语法层 —— lieflat-charts `mono-tokens.js` 的 **Vue 移植**（docs/50 §12.1）。
 *
 * 来源：skill 仓库 `local/skills/lieflat-charts-main/mono-tokens.js`（结构正本）。
 * 移植时**保留**：色板与 7 级灰阶（明度即数据）、字号与最小字号下限、圆角、动画参数、
 * `rnd` 确定性伪随机、几何原语（`pol` / `sect` / `blob`）。
 *
 * **改写**：`obsReveal` / `eReveal` 原版是命令式 DOM 操作（`getElementById` + `innerHTML=''` +
 * 模块级 `timers` 字典）。在 Vue SPA 里直接照搬会有两个真问题：
 *   ① 组件卸载后 IntersectionObserver 与 timer 不释放（路由切换反复挂载 → 泄漏）；
 *   ② `innerHTML=''` 清空的不是 Vue 的虚拟 DOM 所管理的节点，后续 patch 会错位。
 * 因此改为 `useReveal()`：**只暴露一个 `revealed` 布尔**，动画交给各图表组件自己的
 * CSS transition + 逐元素 delay 完成 —— 结构与动画解耦，卸载时自动清理。
 */

import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Ref } from 'vue'

import { mono } from '@/styles/tokens'

export { mono }

/** 确定性伪随机：演示/兜底数据一律用它，禁用 Math.random()（刷新必须长一样） */
export const rnd = (i: number, k: number): number =>
  Math.abs(((i * 73856093) ^ (k * 19349663)) % 1000) / 1000

const D2R = Math.PI / 180

/** 极坐标 → 直角坐标 */
export const pol = (cx: number, cy: number, r: number, deg: number): [number, number] => [
  cx + r * Math.cos(deg * D2R),
  cy + r * Math.sin(deg * D2R),
]

/** 环形扇区 path（角度制，a0 < a1） */
export function sect(
  cx: number,
  cy: number,
  r0: number,
  r1: number,
  a0: number,
  a1: number,
): string {
  const big = a1 - a0 > 180 ? 1 : 0
  const [xa, ya] = pol(cx, cy, r1, a0)
  const [xb, yb] = pol(cx, cy, r1, a1)
  const [xc, yc] = pol(cx, cy, r0, a1)
  const [xd, yd] = pol(cx, cy, r0, a0)
  const f = (n: number) => n.toFixed(2)
  return `M${f(xa)} ${f(ya)} A${f(r1)} ${f(r1)} 0 ${big} 1 ${f(xb)} ${f(yb)} L${f(xc)} ${f(yc)} A${f(r0)} ${f(r0)} 0 ${big} 0 ${f(xd)} ${f(yd)} Z`
}

/** 手绘感圆（editorial 系气泡用）：圆周叠两个慢波 + 噪声，seed 定形 */
export function blob(x: number, y: number, r: number, seed: number): string {
  const n = Math.max(14, Math.round(r * 1.6))
  const pts: [number, number][] = []
  for (let t = 0; t < n; t += 1) {
    const a = (t / n) * Math.PI * 2
    const w =
      1 +
      0.055 * Math.sin(a * 2 + seed * 7) +
      0.04 * Math.sin(a * 3 + seed * 13) +
      (rnd(seed + t, 3) - 0.5) * 0.03
    pts.push([x + Math.cos(a) * r * w, y + Math.sin(a) * r * w])
  }
  const f = (n2: number) => n2.toFixed(1)
  let d = `M${f(pts[0][0])} ${f(pts[0][1])}`
  for (let t = 0; t < n; t += 1) {
    const p = pts[t]
    const q = pts[(t + 1) % n]
    d += ` Q${f(p[0])} ${f(p[1])} ${f((p[0] + q[0]) / 2)} ${f((p[1] + q[1]) / 2)}`
  }
  return `${d} Z`
}

/**
 * 面积编码：**必须**开方换算半径（面积 ∝ 数值，不能拿数值直接当半径）。
 * lieflat 硬规则；单独抽成函数便于单测覆盖。
 */
export const areaRadius = (value: number, max: number, rMax: number): number =>
  max <= 0 ? 0 : rMax * Math.sqrt(Math.max(0, value) / max)

/** 线性映射（带除零保护） */
export function scale(value: number, d0: number, d1: number, r0: number, r1: number): number {
  if (d1 === d0) return (r0 + r1) / 2
  return r0 + ((value - d0) / (d1 - d0)) * (r1 - r0)
}

/** 竖柱路径：柱端胶囊圆角（只圆上端），顶部圆角不超过半宽 */
export function capsuleBarTop(x: number, y: number, w: number, h: number): string {
  const r = Math.min(w / 2, h)
  if (h <= 0) return ''
  return `M${x} ${y + h} L${x} ${y + r} Q${x} ${y} ${x + r} ${y} L${x + w - r} ${y} Q${x + w} ${y} ${x + w} ${y + r} L${x + w} ${y + h} Z`
}

/** 横柱路径：柱端胶囊圆角（只圆外端 = 右端） */
export function capsuleBarRight(x: number, y: number, w: number, h: number): string {
  const r = Math.min(h / 2, w)
  if (w <= 0) return ''
  return `M${x} ${y} L${x + w - r} ${y} Q${x + w} ${y} ${x + w} ${y + r} L${x + w} ${y + h - r} Q${x + w} ${y + h} ${x + w - r} ${y + h} L${x} ${y + h} Z`
}

/**
 * 滚入视野才播的 reveal（点击可重播）。
 *
 * 与 lieflat 原版的差异：**不再清空 DOM**，只翻转一个布尔；
 * 重播通过递增 `replayToken` 让图表重新走一遍入场。
 */
export function useReveal(el: Ref<HTMLElement | null>, threshold = 0.3) {
  const revealed = ref(false)
  const replayToken = ref(0)
  let observer: IntersectionObserver | null = null

  function replay(): void {
    replayToken.value += 1
    revealed.value = true
  }

  onMounted(() => {
    const node = el.value
    if (!node) {
      revealed.value = true
      return
    }
    // 无 IntersectionObserver（测试环境 / 老浏览器）→ 直接显示，不能白屏
    if (typeof IntersectionObserver === 'undefined') {
      revealed.value = true
      return
    }
    observer = new IntersectionObserver(
      (entries) => {
        if (entries[0]?.isIntersecting) {
          revealed.value = true
          observer?.disconnect()
          observer = null
        }
      },
      { threshold },
    )
    observer.observe(node)
    node.style.cursor = 'pointer'
    node.addEventListener('click', replay)
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
    el.value?.removeEventListener('click', replay)
  })

  return { revealed, replayToken, replay }
}

/** 用户是否要求减弱动效（图表入场统一降级为直接呈现） */
export function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  )
}

/**
 * 数据变化时重新播放入场。
 * 返回递增的 key，图表把它拼进 `:key` 即可重挂载 DOM 节点（触发 CSS 动画）。
 */
export function useReplayOnData(source: Ref<unknown>) {
  const token = ref(0)
  watch(source, () => {
    token.value += 1
  })
  return token
}

/** 逐元素入场延迟（ms），点阵 12ms / 条形 100ms —— 取自 mono.MOTION */
export const staggerDelay = (index: number, kind: 'dot' | 'bar' = 'bar'): number =>
  index * (kind === 'dot' ? mono.MOTION.staggerDot : mono.MOTION.staggerBar)

/**
 * ## Mono 偏离清单（偏离 lieflat 正本之处，逐条有理由）
 *
 * UI/图表拷问（docs/51 §6）要求：**凡偏离必须写明**，不能默认"差不多就是 Mono"。
 *
 * | # | 偏离 | 理由 |
 * |---|---|---|
 * | 1 | **字体用系统栈，不用 Inter**（`mono-tokens.js:37-39` 规定 Inter） | 控制台要能在内网/离线跑，不引 CDN 字体；仓库现况是 UI 侧只有 `/login` 会加载 Google Fonts（`apps/web/src/styles/mobile-soft.css:11`），成不了全局基线。代价：**Inter 的 800 字重在系统栈里退化**，故本项目把 `FONT.value` 的 800 降级为 700 + `font-variant-numeric: tabular-nums`，靠等宽数字保住"读数对齐"这一真正起作用的部分 |
 * | 2 | **图表卡画在纸底 `#F0EFEB` 而非白卡**，且用 24px 圆角 | 这是**遵守**而非偏离：Mono 契约本就是"卡底 = 页面底、无边框无阴影"（SKILL §2/§3）。v1 文档写成白卡是错的，已改（docs/50 §11.2）。控制台因此给图表区单独一块 `.mono-surface` |
 * | 3 | **副标题/来源行不用 `MUTED`/`FAINT` 原值** | 实测 `MUTED #8f8e88` 在纸底上 2.86:1、`FAINT #c6c5bf` 约 1.6:1，**都不达 WCAG AA**。副标题承载**口径说明**（是要读的信息）→ 压深到 `#6a6963`（4.79:1）；来源行是装饰性归属 → 提到 `MUTED`（仍偏低但至少可见），并在此登记 |
 * | 4 | **瀑布图用 DOM 而非 SVG**，且长度带 `MIN_BAR` 下限 | 见 `TraceWaterfall.vue` 顶部注释：形状会被非等比缩放破坏的图用真像素坐标；最小宽度属 SKILL §7 的"撕柱不撕轴"第 ③ 条，且**必须在界面上写明** |
 * | 5 | **状态靠"明度 + 形状标记"而非色相** | Mono 无彩色；错误态另加端头标记，保证去掉明度差异后仍可辨（SKILL §8 自检第 2 条的同类要求） |
 */
export const MONO_DEVIATIONS = [
  'font: system stack instead of Inter (offline-safe); weight 800 → 700 + tabular-nums',
  'chart card on paper #F0EFEB with 24px radius (this is compliance, not deviation)',
  'subtitle #6a6963 / source line MUTED for contrast (MUTED 2.86:1 and FAINT ~1.6:1 fail WCAG AA)',
  'TraceWaterfall uses DOM pixels and a MIN_BAR floor (SKILL §7 option 3, disclosed in the UI)',
  'status encoded by lightness + shape marker, never hue (Mono has no colour)',
] as const

/** ECharts 通用基座样式（与 Mono 一致：无边框 tooltip、发丝轴、无背景） */
export const echartsMonoBase = {
  backgroundColor: 'transparent',
  animationDuration: mono.MOTION.enter,
  animationEasing: 'quarticOut' as const,
  tooltip: mono.tipLight,
  textStyle: { fontFamily: 'Inter, "Segoe UI", "Microsoft YaHei UI", sans-serif' },
  grid: { left: 8, right: 12, top: 16, bottom: 8, containLabel: true },
  axisLine: { lineStyle: { color: mono.GRID, width: 0.7 } },
  splitLine: { lineStyle: { color: mono.GRID, width: 0.5 } },
  axisLabel: { color: mono.MUTED, fontSize: mono.FONT.axis.size, fontWeight: mono.FONT.axis.weight },
}
