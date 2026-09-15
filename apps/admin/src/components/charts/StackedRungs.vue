<script setup lang="ts">
/**
 * **F7 Stacked Rungs** — lieflat Basics 组（`catalog.md`：堆叠构成 ≤4 类 × ≤3 段 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Where each region's revenue sits`
 * （渲染代码块 `// ════ C3 · stacked rungs ════`，副标题 `three products stack up the ladder, darkest carries the most`）。
 *
 * 从该卡搬过来的结构：
 * - **同一把梯子分几段**：每类一列，段沿 `mono.L` 阶梯从黑到浅（最深 = 第一段，最重），
 *   段与段之间**空半格呼吸**（模板是整格 `+si`，这里收成 0.55 格，省高度不省语义）；
 * - **一格 = 一个单位**：段内逐格横档，档宽/明度按 `rnd(k,i)` 微抖，近看数得出；
 * - 段值贴在段中（右侧），**合计贴柱顶**，类目名贴柱脚，底线收口；
 * - 脚注把"哪段是哪段"说清（模板 `DARKEST = CORE · MID = ADD-ONS` 的句式）。
 *
 * 明度即数据的落法：段序 = 数据段序（`segments` 的数组顺序就是"最重要→次要"），
 * 明度只标段身份，长度才标数值——两套编码不重复同一维度。
 * 段数 > 3 时沿 ladder 继续取（`L[2]/L[4]/L[6]`），仍然不出灰阶。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { capsuleBarTop, mono, rnd } from './mono'

export interface StackSegment {
  name: string
  /** 与 `categories` 等长 */
  values: number[]
}

const props = withDefaults(
  defineProps<{
    categories: string[]
    segments: StackSegment[]
    unit?: string
    revealed?: boolean
  }>(),
  { unit: '', revealed: true },
)

/** 段序 → 灰阶档位（前 3 段与 gallery 的 INK / #8F8E88 / #C0BFB8 对齐） */
const SEG_LADDER = [0, 3, 5, 2, 4, 6]
/** 段间呼吸（单位：格） */
const SEG_GAP = 0.55
/** 单格最小可辨高度（px），细于此值退化为实心段 */
const MIN_STEP = 2.5
const PAD_T = 22
const PAD_B = 20
const PAD_X = 8

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 400, h: 230 })
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

const num = (v: number | undefined): number => (typeof v === 'number' && Number.isFinite(v) && v > 0 ? v : 0)

/** 每类的段值（长度固定 = segments 数，缺项当 0，绝不当"没这段"） */
const cells = computed(() =>
  props.categories.map((label, i) => ({
    label,
    parts: props.segments.map((s, si) => ({
      name: s.name,
      value: num(s.values[i]),
      shade: mono.L[SEG_LADDER[Math.min(si, SEG_LADDER.length - 1)]],
    })),
  })),
)

const hasData = computed(
  () => cells.value.length > 0 && props.segments.length > 0 && cells.value.some((c) => c.parts.some((p) => p.value > 0)),
)

/** 每类的"格子跨度" = 合计 + 段间呼吸 */
const spans = computed(() =>
  cells.value.map((c) => {
    const filled = c.parts.filter((p) => p.value > 0).length
    return c.parts.reduce((sum, p) => sum + Math.round(p.value), 0) + Math.max(0, filled - 1) * SEG_GAP
  }),
)
const maxSpan = computed(() => (spans.value.length ? Math.max(...spans.value) : 0))

const geo = computed(() => {
  const { w, h } = box.value
  const innerW = Math.max(40, w - PAD_X * 2)
  const innerH = Math.max(40, h - PAD_T - PAD_B)
  const slot = innerW / Math.max(cells.value.length, 1)
  const step = maxSpan.value > 0 ? innerH / maxSpan.value : innerH
  return {
    w,
    h,
    innerW,
    slot,
    step,
    baseY: h - PAD_B,
    halfW: Math.min(17, Math.max(8, slot * 0.22)),
    solid: step < MIN_STEP,
  }
})

interface Part {
  key: string
  /** 顶格用胶囊路径（只圆上端），其余用矩形 */
  path: string
  x: number
  y: number
  w: number
  h: number
  top: boolean
  fill: string
  opacity: number
  delay: number
  /** 段值标签 */
  labY: number
  labText: string
  labFill: string
  readout: string
}

interface Col {
  label: string
  cx: number
  parts: Part[]
  total: number
  totalY: number
  totalText: string
  readout: string
}

function buildCol(
  cell: { label: string; parts: { name: string; value: number; shade: string }[] },
  i: number,
  g: { slot: number; step: number; baseY: number; halfW: number; solid: boolean },
): Col {
  const cx = PAD_X + g.slot * (i + 0.5)
  const parts: Part[] = []
  let k0 = 0
  let segIdx = 0
  for (const p of cell.parts) {
    if (p.value <= 0) continue
    const count = Math.round(p.value)
    const yOf = (u: number): number => g.baseY - (k0 + u + segIdx * SEG_GAP) * g.step
    const ranges: [number, number][] = g.solid ? [[0, count]] : Array.from({ length: count }, (_, k) => [k, k + 1])
    ranges.forEach(([from, to], k) => {
      const shrink = 0.92 + rnd(k + 1, i * 3 + segIdx + 2) * 0.08
      const w = Math.max(4, g.halfW * 2 * shrink)
      const x = cx - w / 2
      const y = yOf(to)
      const h = Math.max(0.7, yOf(from) - yOf(to) - 0.9)
      const isTop = segIdx === cell.parts.filter((q) => q.value > 0).length - 1 && to === count
      parts.push({
        key: `${cell.label}-${segIdx}-${k}`,
        path: isTop ? capsuleBarTop(x, y, w, h) : '',
        x,
        y,
        w,
        h,
        top: isTop,
        fill: p.shade,
        opacity: 0.62 + rnd(k + 2, i + segIdx + 4) * 0.38,
        delay: i * mono.MOTION.staggerBar + (k0 + k) * mono.MOTION.staggerDot,
        labY: (yOf(from) + yOf(to)) / 2 + 2.5,
        labText: String(p.value),
        labFill: p.shade === mono.L[5] || p.shade === mono.L[6] ? mono.L[3] : p.shade,
        readout: `${cell.label} ${p.name} — ${p.value}${props.unit}`,
      })
    })
    k0 += count
    segIdx += 1
  }
  const total = cell.parts.reduce((s, p) => s + p.value, 0)
  return {
    label: cell.label,
    cx,
    parts,
    total,
    totalY: g.baseY - (spans.value[i] + 0.9) * g.step,
    totalText: `${Math.round(total * 100) / 100}`,
    readout: `${cell.label} — 合计 ${Math.round(total * 100) / 100}${props.unit}（${cell.parts
      .map((p) => `${p.name} ${p.value}`)
      .join(' · ')}）`,
  }
}

const cols = computed<Col[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  return cells.value.map((c, i) => buildCol(c, i, g))
})

const footNote = computed(() => {
  if (!hasData.value) return ''
  const legend = props.segments
    .map((s, si) => `${si === 0 ? '最深' : si === 1 ? '中' : '浅'} = ${s.name}`)
    .join(' · ')
  const tail = geo.value.solid ? ' · 单位过密，已退化为实心段（仅示长度）' : ' · 1 格 = 1 个单位'
  return `${legend}${tail}`
})
</script>

<template>
  <div v-if="!hasData" class="sr-empty">暂无数据（没有可堆叠的构成）</div>
  <div v-else ref="host" class="sr">
    <svg
      class="sr-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`堆叠柱状图，${cols.length} 个类目 × ${segments.length} 段`"
    >
      <line
        :x1="PAD_X - 2"
        :x2="geo.w - PAD_X + 2"
        :y1="geo.baseY"
        :y2="geo.baseY"
        :stroke="mono.GRID"
        stroke-width="0.8"
      />

      <g class="sr-g" :class="{ 'sr-g--in': revealed }">
        <g v-for="col in cols" :key="col.label">
          <template v-for="p in col.parts" :key="p.key">
            <rect
              v-if="!p.top"
              class="sr-part"
              :x="p.x"
              :y="p.y"
              :width="p.w"
              :height="p.h"
              rx="0.8"
              :fill="p.fill"
              :style="{ opacity: p.opacity, animationDelay: `${p.delay}ms` }"
            />
            <path
              v-else
              class="sr-part"
              :d="p.path"
              :fill="p.fill"
              :style="{ opacity: p.opacity, animationDelay: `${p.delay}ms` }"
            />
            <text
              class="sr-seglab"
              :x="col.cx + geo.halfW + 7"
              :y="p.labY"
              font-size="8"
              font-weight="800"
              :fill="p.labFill"
              :style="{ animationDelay: `${p.delay + 120}ms` }"
            >
              {{ p.labText }}
            </text>
            <rect
              :x="p.x"
              :y="p.y"
              :width="p.w"
              :height="Math.max(1, p.h)"
              fill="transparent"
            >
              <title>{{ p.readout }}</title>
            </rect>
          </template>

          <text
            class="sr-total"
            :x="col.cx"
            :y="col.totalY"
            text-anchor="middle"
            font-size="10.5"
            font-weight="800"
            :fill="mono.INK"
            :style="{ animationDelay: `${col.parts.length * mono.MOTION.staggerDot + 320}ms` }"
          >
            {{ col.totalText }}<tspan v-if="unit" font-size="7.5" :fill="mono.MUTED">{{ unit }}</tspan>
          </text>
          <text
            class="sr-cat"
            :x="col.cx"
            :y="geo.baseY + 13"
            text-anchor="middle"
            font-size="7.5"
            font-weight="700"
            letter-spacing="0.06em"
            :fill="mono.MUTED"
          >
            {{ col.label }}
          </text>
          <rect :x="col.cx - geo.slot / 2" y="0" :width="geo.slot" :height="PAD_T" fill="transparent">
            <title>{{ col.readout }}</title>
          </rect>
        </g>
      </g>
    </svg>

    <p class="sr-foot">{{ footNote }}</p>
  </div>
</template>

<style scoped>
.sr-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.sr {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.sr-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.sr-g {
  opacity: 0;
}
.sr-g--in {
  opacity: 1;
}
.sr-part,
.sr-seglab,
.sr-total,
.sr-cat {
  animation: sr-rise 0.85s cubic-bezier(0.25, 1, 0.5, 1) both;
}
@keyframes sr-rise {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}
.sr-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
  font-variant-numeric: tabular-nums;
}
@media (prefers-reduced-motion: reduce) {
  .sr-g {
    opacity: 1;
  }
  .sr-part,
  .sr-seglab,
  .sr-total,
  .sr-cat {
    animation: none;
  }
}
</style>
