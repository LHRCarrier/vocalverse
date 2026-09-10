<script setup lang="ts">
/**
 * **F9 Rung Waterfall** — lieflat Basics 组（`catalog.md`：瀑布 / 增减分解 ≤6 级 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `From gross to net, step by step`
 * （渲染代码块 `// ════ C5 · rung waterfall ════`，副标题 `solid rungs add, hollow rungs take away`）。
 *
 * 从该卡搬过来的结构：
 * - **每级一把小梯子**：一格 = 一个单位，梯子从"上一级的交接位"往上/往下长，
 *   加项实格、减项虚格（模板脚注 `SOLID RUNGS ADD · DASHED RUNGS TAKE AWAY`）——
 *   方向（上/下）已经说明增减，虚线只是冗余的第二编码，不靠颜色区分正负；
 * - **虚线台阶承接**：每级结束后一条虚线横拉到下一级的起点高度（模板 `step hand-off`），
 *   这是瀑布"能对上账"的关键家具；
 * - 起点/终点是**存量柱**（`total: true`）：从 0 立起，用 `mono.L[0]` 实心；
 *   中间增量用 `mono.L[2]`（契约硬约束）；
 * - 值写在自己那一级的顶上，类目名贴地，底线收口。
 *
 * 诚实的边界：末级 `total: true` 时**以累计口径为准**绘制（瀑布的第一要务是能对上），
 * 若传入的 `delta` 与累计差出 0.01 以上，脚注里明写两者，不偷偷改数。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { mono, rnd } from './mono'

export interface WaterfallStep {
  label: string
  delta: number
  /** 存量柱（起点/终点）：从 0 立起而不是从上一级续接 */
  total?: boolean
}

const props = withDefaults(
  defineProps<{
    steps: WaterfallStep[]
    unit?: string
    revealed?: boolean
  }>(),
  { unit: '', revealed: true },
)

const PAD_T = 22
const PAD_B = 20
const PAD_X = 8
/** 单格最小可辨高度（px） */
const MIN_STEP = 2.4

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 420, h: 230 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(160, node.clientWidth), h: Math.max(120, node.clientHeight) }
  }
  read()
  if (typeof ResizeObserver === 'undefined') return
  ro = new ResizeObserver(read)
  ro.observe(node)
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
})

interface Level {
  label: string
  /** 该级传入的增减值（原样保留，读数与脚注都用它） */
  delta: number
  /** 柱底（单位坐标） */
  from: number
  /** 柱顶（单位坐标） */
  to: number
  /** 这一级结束后的交接位 */
  level: number
  total: boolean
  neg: boolean
  /** 传入 delta 与累计口径不一致时的差额（只在末级 total 上可能出现） */
  mismatch: number
}

/** 把增减序列摊成"每级从哪立到哪"的梯级（纯函数，便于核对口径） */
function toLevels(steps: WaterfallStep[]): Level[] {
  const out: Level[] = []
  let run = 0
  steps.forEach((s, i) => {
    const v = Number.isFinite(s.delta) ? s.delta : 0
    if (s.total) {
      // 起点存量：用传入值当基数；终点存量：用累计值（瀑布必须能对上账）
      const level = i === 0 ? v : run
      out.push({
        label: s.label,
        delta: v,
        from: 0,
        to: i === 0 ? v : level,
        level,
        total: true,
        neg: false,
        mismatch: i === 0 || run === 0 ? 0 : v - level,
      })
      run = i === 0 ? v : run
      return
    }
    out.push({
      label: s.label,
      delta: v,
      from: run,
      to: run + v,
      level: run + v,
      total: false,
      neg: v < 0,
      mismatch: 0,
    })
    run += v
  })
  return out
}

const levels = computed(() => toLevels(props.steps))
const hasData = computed(() =>
  levels.value.some((l) => (l.total ? Math.abs(l.to) > 0 : Math.abs(l.to - l.from) > 0)),
)

/** 单位坐标的极值（含 0：地板必须在场） */
const extent = computed(() => {
  const vals = levels.value.flatMap((l) => [l.from, l.to, l.level, 0])
  return { lo: Math.min(...vals), hi: Math.max(...vals) }
})

/** 上下各留 8px，避免最高一级贴顶被裁 */
const EDGE = 8

interface Geo {
  w: number
  h: number
  innerW: number
  slot: number
  step: number
  /** 单位坐标 → 像素 y */
  yOf: (u: number) => number
  halfW: number
  /** 格子细到不可辨 → 退化为整柱 */
  solid: boolean
}

const geo = computed<Geo>(() => {
  const { w, h } = box.value
  const innerH = Math.max(40, h - PAD_T - PAD_B - EDGE * 2)
  const innerW = Math.max(40, w - PAD_X * 2)
  const span = Math.max(extent.value.hi - extent.value.lo, 1e-6)
  const step = innerH / span
  const slot = innerW / Math.max(levels.value.length, 1)
  return {
    w,
    h,
    innerW,
    slot,
    step,
    yOf: (u: number): number => h - PAD_B - EDGE - (u - extent.value.lo) * step,
    halfW: Math.min(16, Math.max(8, slot * 0.26)),
    solid: step < MIN_STEP,
  }
})

interface Rung {
  key: string
  x: number
  y: number
  w: number
  h: number
  dashed: boolean
  color: string
  opacity: number
  delay: number
}

interface Col {
  label: string
  cx: number
  rungs: Rung[]
  labY: number
  labX: number
  labText: string
  labFill: string
  handoff: { x1: number; x2: number; y: number } | null
  readout: string
}

/** 一级 → 一串横档：>=1 单位时逐格，<1 单位时一根"部分格"（长度仍然 ∝ 数值） */
function rungsFor(l: Level, i: number, g: Geo): Rung[] {
  const cx = PAD_X + g.slot * (i + 0.5)
  const span = Math.abs(l.to - l.from)
  const n = g.solid ? 1 : Math.max(1, Math.ceil(span))
  const color = l.total ? mono.L[0] : mono.L[2]
  const out: Rung[] = []
  for (let k = 0; k < n; k += 1) {
    const a = g.solid ? 0 : Math.min(span, k)
    const b = g.solid ? span : Math.min(span, k + 1)
    const uTop = l.to >= l.from ? l.from + b : l.from - a
    const uBot = l.to >= l.from ? l.from + a : l.from - b
    const shrink = 0.9 + rnd(k + 1, i + 2) * 0.1
    const w = Math.max(4, g.halfW * 2 * shrink)
    const yTop = g.yOf(uTop)
    const yBot = g.yOf(uBot)
    out.push({
      key: `${l.label}-${k}`,
      x: cx - w / 2,
      y: Math.min(yTop, yBot),
      w,
      h: Math.max(0.7, Math.abs(yBot - yTop) - 0.9),
      dashed: l.neg,
      color,
      opacity: l.total ? 1 : 0.66 + rnd(k + 2, i + 4) * 0.34,
      delay: i * mono.MOTION.staggerBar + k * mono.MOTION.staggerDot,
    })
  }
  return out
}

const cols = computed<Col[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  return levels.value.map((l, i) => {
    const cx = PAD_X + g.slot * (i + 0.5)
    const next = levels.value[i + 1]
    const level = l.total ? l.to : l.level
    return {
      label: l.label,
      cx,
      rungs: rungsFor(l, i, g),
      labY: Math.min(g.yOf(l.to), g.yOf(l.from)) - 7,
      labX: cx,
      labText: `${l.total ? '' : l.neg ? '−' : '+'}${Math.abs(Math.round(l.delta * 100) / 100)}`,
      labFill: l.neg ? mono.L[2] : l.total ? mono.L[0] : mono.L[1],
      handoff: next
        ? { x1: cx + g.halfW + 2, x2: PAD_X + g.slot * (i + 1.5) - g.halfW - 2, y: g.yOf(level) }
        : null,
      readout:
        `${l.label} — ${l.total ? '存量' : l.neg ? '减' : '增'} ${Math.abs(l.delta)}${props.unit}` +
        `（交接位 ${Math.round(level * 100) / 100}${props.unit}）`,
    }
  })
})

const footNote = computed(() => {
  if (!hasData.value) return ''
  const gap = levels.value.find((l) => Math.abs(l.mismatch) > 0.01)
  const base = geo.value.solid
    ? '单位过密，已退化为整柱（仅示长度）· 实柱 = 加项 · 虚柱 = 减项 · 虚线 = 交接位'
    : `实格 = 加项 · 虚格 = 减项 · 1 格 = 1 个 ${props.unit || '单位'} · 虚线台阶 = 交接位`
  if (!gap) return base
  return `${base} · 末级以累计口径 ${Math.round(gap.level * 100) / 100}${props.unit} 为准（传入 ${Math.round(gap.delta * 100) / 100}）`
})
</script>

<template>
  <div v-if="!hasData" class="rw-empty">暂无数据（没有可分解的增减序列）</div>
  <div v-else ref="host" class="rw">
    <svg
      class="rw-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`瀑布分解图，共 ${cols.length} 级，终点 ${Math.round(extent.hi * 100) / 100}${unit}`"
    >
      <!-- 零线：瀑布的"地平线"，没有它就不知道谁在地上谁在地下 -->
      <line
        :x1="PAD_X - 2"
        :x2="geo.w - PAD_X + 2"
        :y1="geo.yOf(0)"
        :y2="geo.yOf(0)"
        :stroke="mono.GRID"
        stroke-width="0.8"
      />

      <g class="rw-g" :class="{ 'rw-g--in': revealed }">
        <g v-for="(col, i) in cols" :key="col.label">
          <!-- 交接台阶（虚线，先画，压在柱子下面） -->
          <line
            v-if="col.handoff"
            class="rw-step"
            :x1="col.handoff.x1"
            :y1="col.handoff.y"
            :x2="col.handoff.x2"
            :y2="col.handoff.y"
            :stroke="mono.FAINT"
            stroke-width="0.7"
            stroke-dasharray="2 3"
            :style="{ animationDelay: `${240 + i * mono.MOTION.staggerBar}ms` }"
          />

          <rect
            v-for="r in col.rungs"
            :key="r.key"
            class="rw-rung"
            :x="r.x"
            :y="r.y"
            :width="r.w"
            :height="r.h"
            rx="0.8"
            :fill="r.dashed ? 'none' : r.color"
            :stroke="r.color"
            :stroke-width="r.dashed ? 0.9 : 0"
            :stroke-dasharray="r.dashed ? '2.5 2.5' : undefined"
            :opacity="r.opacity"
            :style="{ animationDelay: `${r.delay}ms` }"
          />

          <text
            class="rw-num"
            :x="col.labX"
            :y="col.labY"
            text-anchor="middle"
            font-size="10"
            font-weight="800"
            :fill="col.labFill"
            :style="{ animationDelay: `${i * mono.MOTION.staggerBar + 320}ms` }"
          >
            {{ col.labText }}<tspan v-if="unit" font-size="7" :fill="mono.MUTED">{{ unit }}</tspan>
          </text>
          <text
            class="rw-cat"
            :x="col.cx"
            :y="geo.h - PAD_B + 13"
            text-anchor="middle"
            font-size="7.5"
            font-weight="700"
            letter-spacing="0.06em"
            :fill="mono.MUTED"
          >
            {{ col.label }}
          </text>

          <rect :x="col.cx - geo.slot / 2" y="0" :width="geo.slot" :height="geo.h" fill="transparent">
            <title>{{ col.readout }}</title>
          </rect>
        </g>
      </g>
    </svg>

    <p class="rw-foot">{{ footNote }}</p>
  </div>
</template>

<style scoped>
.rw-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.rw {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.rw-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.rw-g {
  opacity: 0;
}
.rw-g--in {
  opacity: 1;
}
.rw-rung,
.rw-step,
.rw-num,
.rw-cat {
  animation: rw-in 0.8s cubic-bezier(0.25, 1, 0.5, 1) both;
}
@keyframes rw-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}
.rw-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .rw-g {
    opacity: 1;
  }
  .rw-rung,
  .rw-step,
  .rw-num,
  .rw-cat {
    animation: none;
  }
}
</style>
