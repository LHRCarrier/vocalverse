<script setup lang="ts">
/**
 * **F11 Tick Gauge** — lieflat Basics 组（`catalog.md`：单值进度 0–100% · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `How far to the quarter's goal`
 * （渲染代码块 `// ════ C7 · tick gauge ════`，副标题 `one tick = one percent of target · inked = earned`）。
 *
 * 从该卡搬过来的结构：
 * - **一格 = 目标的 1%**（模板口径 `ONE TICK = 1% OF TARGET`）：整条尺子 100 格，
 *   已达成的格子**长且黑**，未达成的格子**短且浅**（模板 `inked?13+rnd*6 : 5+rnd*2.5`）——
 *   长度差本身是第二编码，不靠颜色；
 * - **里程碑 25/50/75/100 点标 + 小字**，给"读到哪了"的参照；
 * - **已达成区段**：轨道上从 0 到当前值的实心胶囊段（契约要求的"已达成区段"）；
 * - 收笔"珠子"落在当前值上；中心大数改成**横尺上方的大字**（契约：不是仪表盘指针造型）。
 *
 * 与模板有意不同的一点（契约硬约束）：模板是 210° 弧形表盘，这里是**水平刻度尺**——
 * SKILL §7 拒绝拟物指针，横向刻度尺 + 大字既保留"逐格可数"的语法，又没有表盘造型。
 *
 * `tone` 只改「明度 + 形状标记」：ok = `mono.L[0]` ●、warn = `mono.L[2]` ▲、
 * danger = `mono.L[4]` ■（Mono 无彩色，形状是第二编码）。
 * `value > max` 时**不截断读数**：格子铺满 + 脚注写明"已超目标"，大字仍报真实占比。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { mono, rnd } from './mono'

const props = withDefaults(
  defineProps<{
    value: number
    /** 目标上限，默认 100 */
    max?: number
    unit?: string
    caption?: string
    tone?: 'ok' | 'warn' | 'danger'
    revealed?: boolean
  }>(),
  { max: 100, unit: '', caption: '', tone: 'ok', revealed: true },
)

/** 尺子格数：上限 100 格（= 目标的 1%）；目标本身 ≤20 时可数（1 格 = 1 个单位） */
const MAX_TICKS = 100
const PAD_X = 12
/** 刻度基线离底边的距离：下面要放里程碑小字 */
const BASE_GAP = 24

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 420, h: 150 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(160, node.clientWidth), h: Math.max(72, node.clientHeight) }
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

const toneShade = computed(() => (props.tone === 'danger' ? mono.L[4] : props.tone === 'warn' ? mono.L[2] : mono.L[0]))
const toneMark = computed(() => (props.tone === 'danger' ? '■' : props.tone === 'warn' ? '▲' : '●'))

const max = computed(() => (Number.isFinite(props.max) && props.max > 0 ? props.max : 100))
const value = computed(() => (Number.isFinite(props.value) ? Math.max(0, props.value) : 0))
const hasData = computed(() => Number.isFinite(props.value))

/** 一格代表多少（目标 ≤20 就 1 格 = 1 个单位，否则 1 格 = 目标的 1%） */
const perTick = computed(() => (max.value <= 20 ? 1 : max.value / MAX_TICKS))
const tickCount = computed(() => Math.max(1, Math.round(max.value / perTick.value)))
const ratio = computed(() => value.value / max.value)
const pct = computed(() => ratio.value * 100)
const inked = computed(() => Math.min(tickCount.value, Math.round(ratio.value * tickCount.value)))
const over = computed(() => value.value > max.value)

const geo = computed(() => {
  const { w, h } = box.value
  const innerW = Math.max(60, w - PAD_X * 2)
  return {
    w,
    h,
    innerW,
    x0: PAD_X,
    baseY: h - BASE_GAP,
    pitch: innerW / tickCount.value,
    /** 达成段可读的最小厚度 */
    bandH: 3.4,
  }
})

interface Tick {
  x: number
  h: number
  color: string
  width: number
  delay: number
}

const ticks = computed<Tick[]>(() => {
  const g = geo.value
  return Array.from({ length: tickCount.value }, (_, k) => {
    const earned = k < inked.value
    return {
      x: g.x0 + g.pitch * (k + 0.5),
      h: earned ? Math.min(g.baseY - 6, 13 + rnd(k + 1, 3) * 5) : 5 + rnd(k + 1, 7) * 2.5,
      color: earned ? toneShade.value : mono.L[6],
      width: earned ? 1 : 0.6,
      delay: k * mono.MOTION.staggerDot,
    }
  })
})

/** 里程碑：25/50/75/100% 的点标 + 小字 */
const milestones = computed(() =>
  [0.25, 0.5, 0.75, 1].map((r) => {
    const g = geo.value
    return { x: g.x0 + g.innerW * r, y: g.baseY + 7, label: `${Math.round(r * 100)}%` }
  }),
)

const tipX = computed(() => geo.value.x0 + geo.value.innerW * Math.min(1, ratio.value))
const bandW = computed(() => geo.value.innerW * Math.min(1, ratio.value))
const fmt = (v: number): string =>
  String(Math.round(v * 100) / 100).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
const footNote = computed(() => {
  if (!hasData.value) return ''
  const base =
    perTick.value === 1
      ? `1 格 = 1 ${props.unit || '个单位'}（目标 ${fmt(max.value)}）`
      : `1 格 = 目标的 1%（= ${fmt(perTick.value)}${props.unit}）`
  return over.value ? `${base} · 已超目标 ${fmt(value.value - max.value)}${props.unit}，格子铺满但仍报真实占比` : base
})
</script>

<template>
  <div v-if="!hasData" class="tg-empty">暂无数据（没有可读的进度值）</div>
  <div v-else ref="host" class="tg">
    <!-- 数值大字放外层 HTML：不进 SVG，可选中、可被读屏念出来 -->
    <div class="tg-head">
      <span class="tg-mark" :style="{ color: toneShade }" aria-hidden="true">{{ toneMark }}</span>
      <span class="tg-value" :style="{ color: toneShade }">{{ Math.round(pct) }}<i>%</i></span>
      <span class="tg-rest">
        已达成 {{ fmt(value) }}{{ unit }} / {{ fmt(max) }}{{ unit }}
        <template v-if="over"> · 超出 {{ fmt(value - max) }}{{ unit }}</template>
        <template v-else> · 还差 {{ fmt(max - value) }}{{ unit }}</template>
      </span>
    </div>

    <svg
      class="tg-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`进度刻度尺，${Math.round(pct)}% 达成，共 ${tickCount} 格，已上墨 ${inked} 格`"
    >
      <g class="tg-g" :class="{ 'tg-g--in': revealed }">
        <!-- 达成的区段（胶囊），压在刻度下面当地基 -->
        <rect
          v-if="bandW > 0"
          class="tg-band"
          :x="geo.x0"
          :y="geo.baseY - geo.bandH + 1"
          :width="Math.max(1.6, bandW)"
          :height="geo.bandH"
          :rx="geo.bandH / 2"
          :fill="toneShade"
        />
        <!-- 未达成轨道 -->
        <line
          class="tg-track"
          :x1="geo.x0"
          :y1="geo.baseY - geo.bandH / 2 + 1"
          :x2="geo.x0 + geo.innerW"
          :y2="geo.baseY - geo.bandH / 2 + 1"
          :stroke="mono.GRID"
          stroke-width="0.7"
        />

        <line
          v-for="(t, k) in ticks"
          :key="`t-${k}`"
          class="tg-tick"
          :x1="t.x"
          :x2="t.x"
          :y1="geo.baseY - 3"
          :y2="geo.baseY - 3 - t.h"
          :stroke="t.color"
          :stroke-width="t.width"
          :style="{ animationDelay: `${t.delay}ms` }"
        />

        <!-- 里程碑 -->
        <g v-for="m in milestones" :key="`m-${m.label}`">
          <circle
            class="tg-mile"
            :cx="m.x"
            :cy="m.y"
            r="1"
            :fill="mono.L[4]"
            :style="{ animationDelay: '820ms' }"
          />
          <text
            class="tg-milelab"
            :x="m.x"
            :y="m.y + 12"
            text-anchor="middle"
            font-size="6.5"
            font-weight="600"
            :fill="mono.L[3]"
            :style="{ animationDelay: '860ms' }"
          >
            {{ m.label }}
          </text>
        </g>

        <!-- 收笔珠子：当前值站在这 -->
        <circle
          class="tg-tip"
          :cx="tipX"
          :cy="geo.baseY - 3"
          r="2.6"
          :fill="toneShade"
          :style="{ animationDelay: '1040ms' }"
        />
      </g>

      <rect :x="0" y="0" :width="geo.w" :height="geo.h" fill="transparent">
        <title>{{ Math.round(pct) }}% · 已达成 {{ fmt(value) }}{{ unit }} / {{ fmt(max) }}{{ unit }}</title>
      </rect>
    </svg>

    <p class="tg-foot">
      <template v-if="caption">{{ caption }} · </template>{{ footNote }} ·
      短浅格 = 未达成（长度差是第二编码，不靠颜色）
    </p>
  </div>
</template>

<style scoped>
.tg-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.tg {
  display: flex;
  flex-direction: column;
  height: 100%;
  justify-content: center;
}
.tg-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 2px;
}
.tg-mark {
  font-size: 11px;
}
.tg-value {
  font-size: 34px;
  font-weight: 800;
  letter-spacing: -0.03em;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.tg-value i {
  font-size: 15px;
  font-style: normal;
  font-weight: 700;
  margin-left: 1px;
}
.tg-rest {
  font-size: 11px;
  color: #6a6963; /* mono.L[2] */
  font-variant-numeric: tabular-nums;
}
.tg-svg {
  display: block;
  flex: 0 0 auto;
}
.tg-g {
  opacity: 0;
}
.tg-g--in {
  opacity: 1;
}
.tg-tick,
.tg-band,
.tg-track,
.tg-mile,
.tg-milelab,
.tg-tip {
  animation: tg-in 0.7s cubic-bezier(0.25, 1, 0.5, 1) both;
}
@keyframes tg-in {
  from {
    opacity: 0;
  }
}
.tg-foot {
  margin: 6px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  line-height: 1.5;
}
@media (prefers-reduced-motion: reduce) {
  .tg-g {
    opacity: 1;
  }
  .tg-tick,
  .tg-band,
  .tg-track,
  .tg-mile,
  .tg-milelab,
  .tg-tip {
    animation: none;
  }
}
</style>
