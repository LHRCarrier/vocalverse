<script setup lang="ts">
/**
 * **F15 Tick Box** — lieflat Basics 组（`catalog.md`：五数概括 + 异常值的分组分布 · 后备图，
 * 主力里没有对应编码，命中即直接用 · SVG）。
 * 结构正本：`templates/basics-gallery.html` · 卡内标题 `Reply times, boxed by plan`
 * （渲染代码块 `// ════ F15 · tick box ════`，副标题 `box = the middle half of tickets · paper tick = median · hollow dot = an outlier`）。
 *
 * 从该卡搬过来的结构：
 * - **发丝须线**（min→max，`pathLength` 归一到 1 播描线）+ 两端**短横帽**；
 * - **胶囊箱体**（模板 `rx:9`，即箱体是圆头药丸而不是直角矩形）；
 * - **穿过箱体的中位数线**，且中位数读数贴在箱体右侧（模板 `md.toFixed(1)+'h'`）；
 * - **空心点 = 离群值**，横向按 `rnd(k,g)` 微抖（同一条竖线上的多点不重叠）；
 * - 左侧刻度导轨 + 组名贴地，基线不画（箱子自己站在刻度上）。
 *
 * 与模板有意不同的一点（契约硬约束）：**箱体用 `mono.L[1]` 描边、不填充**
 * （模板按"越快越黑"给箱体上明度填充）。中位数是这张图的读数，线宽 2 = 箱线的 2 倍、
 * 用 `mono.L[0]`，于是"谁快谁慢"由**中位数的高低**表达，而不是由色块表达——
 * 明度留给"这是一个箱"的存在感，数据交给位置与长度。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { mono, rnd } from './mono'

export interface BoxGroup {
  label: string
  min: number
  q1: number
  median: number
  q3: number
  max: number
  outliers: number[]
}

const props = withDefaults(
  defineProps<{
    groups: BoxGroup[]
    unit?: string
    revealed?: boolean
  }>(),
  { unit: '', revealed: true },
)

const PAD_L = 32
const PAD_R = 46
const PAD_T = 26
const PAD_B = 20

const host = ref<HTMLElement | null>(null)
const box = ref({ w: 420, h: 240 })
let ro: ResizeObserver | null = null

onMounted(() => {
  const node = host.value
  if (!node) return
  const read = (): void => {
    box.value = { w: Math.max(180, node.clientWidth), h: Math.max(120, node.clientHeight) }
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

const finite = (v: number): boolean => typeof v === 'number' && Number.isFinite(v)

/** 五数概括只做两件事：丢掉非有限值、把五个数排好序（倒挂的箱体是画不出读数的） */
const rows = computed(() =>
  props.groups
    .map((g) => {
      const five = [g.min, g.q1, g.median, g.q3, g.max]
      if (!five.every(finite)) return null
      const [min, q1, median, q3, max] = [...five].sort((a, b) => a - b)
      return {
        label: g.label,
        min,
        q1,
        median,
        q3,
        max,
        outliers: (g.outliers ?? []).filter(finite),
      }
    })
    .filter((r): r is NonNullable<typeof r> => r !== null),
)

const rawMax = computed(() => {
  const vals = rows.value.flatMap((r) => [r.max, ...r.outliers])
  return vals.length ? Math.max(...vals) : 0
})
const hasData = computed(() => rows.value.length > 0 && rawMax.value > 0)

/** 好看的刻度步长（1 / 2 / 2.5 / 5 / 10 × 10^k） */
function niceStep(raw: number): number {
  if (!(raw > 0)) return 1
  const pow = 10 ** Math.floor(Math.log10(raw))
  const n = raw / pow
  const pick = [1, 2, 2.5, 5, 10].find((m) => n <= m) ?? 10
  return pick * pow
}

const scaleInfo = computed(() => {
  const step = niceStep(rawMax.value / 4)
  const top = step * Math.ceil(rawMax.value / step)
  return { step, top: top > 0 ? top : step }
})

const geo = computed(() => {
  const { w, h } = box.value
  const innerW = Math.max(60, w - PAD_L - PAD_R)
  const innerH = Math.max(40, h - PAD_T - PAD_B)
  const slot = innerW / Math.max(rows.value.length, 1)
  return {
    w,
    h,
    innerW,
    slot,
    bw: Math.min(26, Math.max(12, slot * 0.44)),
    baseY: h - PAD_B,
    yOf: (v: number): number => h - PAD_B - (v / scaleInfo.value.top) * innerH,
  }
})

const yTicks = computed(() => {
  const { step, top } = scaleInfo.value
  const out: number[] = []
  for (let v = 0; v <= top + step / 1000; v += step) out.push(Math.round(v * 1000) / 1000)
  return out
})

interface Drawn {
  label: string
  x: number
  whisker: string
  yMin: number
  yMax: number
  boxY: number
  boxH: number
  medianY: number
  medianText: string
  outlierDots: { x: number; y: number; readout: string }[]
  delay: number
  readout: string
}

const drawn = computed<Drawn[]>(() => {
  if (!hasData.value) return []
  const g = geo.value
  return rows.value.map((r, i) => {
    const x = PAD_L + g.slot * (i + 0.5)
    const yMin = g.yOf(r.min)
    const yMax = g.yOf(r.max)
    const yQ1 = g.yOf(r.q1)
    const yQ3 = g.yOf(r.q3)
    return {
      label: r.label,
      x,
      whisker: `M${x.toFixed(2)} ${yMax.toFixed(2)} L${x.toFixed(2)} ${yMin.toFixed(2)}`,
      yMin,
      yMax,
      boxY: yQ3,
      boxH: Math.max(1.5, yQ1 - yQ3),
      medianY: g.yOf(r.median),
      medianText: `${Math.round(r.median * 100) / 100}`,
      outlierDots: r.outliers.map((o, k) => ({
        x: x + (rnd(k + 1, i + 3) - 0.5) * g.bw * 0.55,
        y: g.yOf(o),
        readout: `${r.label} 离群值 — ${o}${props.unit}`,
      })),
      delay: i * 120,
      readout: `${r.label} — 中位数 ${r.median}${props.unit}，半数落在 ${r.q1}–${r.q3}${props.unit}（最小 ${r.min}／最大 ${r.max}，离群 ${r.outliers.length} 个）`,
    }
  })
})
</script>

<template>
  <div v-if="!hasData" class="tb-empty">暂无数据（没有可汇总的分布）</div>
  <div v-else ref="host" class="tb">
    <svg
      class="tb-svg"
      :width="geo.w"
      :height="geo.h"
      :viewBox="`0 0 ${geo.w} ${geo.h}`"
      role="img"
      :aria-label="`箱线图，${drawn.length} 组，纵轴 0 到 ${scaleInfo.top}${unit}`"
    >
      <!-- 横向导轨 + 刻度（环境结构层：没有它读不出高低） -->
      <g class="tb-grid">
        <line
          v-for="t in yTicks"
          :key="`g-${t}`"
          :x1="PAD_L - 6"
          :y1="geo.yOf(t)"
          :x2="geo.w - PAD_R + 6"
          :y2="geo.yOf(t)"
          :stroke="mono.GRID"
          stroke-width="0.7"
          stroke-dasharray="1.5 3"
        />
      </g>
      <text
        v-for="t in yTicks"
        :key="`gl-${t}`"
        class="tb-ylab"
        :x="PAD_L - 9"
        :y="geo.yOf(t) + 2.6"
        text-anchor="end"
        font-size="7.5"
        font-weight="600"
        :fill="mono.MUTED"
      >
        {{ t }}<tspan v-if="unit" font-size="6.5">{{ unit }}</tspan>
      </text>

      <g class="tb-g" :class="{ 'tb-g--in': revealed }">
        <g v-for="d in drawn" :key="d.label">
          <rect :x="d.x - geo.slot / 2" y="0" :width="geo.slot" :height="geo.h" fill="transparent">
            <title>{{ d.readout }}</title>
          </rect>

          <!-- 须线 + 两端短横帽 -->
          <path
            class="tb-whisker"
            :class="{ 'tb-whisker--in': revealed }"
            :d="d.whisker"
            fill="none"
            :stroke="mono.L[1]"
            stroke-width="0.8"
            path-length="1"
            :style="{ animationDelay: `${d.delay}ms` }"
          />
          <line
            v-for="(y, k) in [d.yMin, d.yMax]"
            :key="`cap-${k}`"
            class="tb-cap"
            :x1="d.x - 7"
            :x2="d.x + 7"
            :y1="y"
            :y2="y"
            :stroke="mono.L[1]"
            stroke-width="1"
            :style="{ animationDelay: `${d.delay + 200}ms` }"
          />

          <!-- 箱体：描边不填充（契约），中位数线 2× 宽 -->
          <rect
            class="tb-box"
            :x="d.x - geo.bw / 2"
            :y="d.boxY"
            :width="geo.bw"
            :height="d.boxH"
            :rx="Math.min(geo.bw / 2, 9)"
            fill="none"
            :stroke="mono.L[1]"
            stroke-width="0.9"
            :style="{ animationDelay: `${d.delay + 150}ms` }"
          />
          <line
            class="tb-median"
            :x1="d.x - geo.bw / 2 + 1.5"
            :x2="d.x + geo.bw / 2 - 1.5"
            :y1="d.medianY"
            :y2="d.medianY"
            :stroke="mono.L[0]"
            stroke-width="2"
            :style="{ animationDelay: `${d.delay + 420}ms` }"
          />
          <text
            class="tb-medval"
            :x="d.x + geo.bw / 2 + 6"
            :y="d.medianY + 3"
            font-size="9.5"
            font-weight="800"
            :fill="mono.L[0]"
            :style="{ animationDelay: `${d.delay + 480}ms` }"
          >
            {{ d.medianText }}<tspan v-if="unit" font-size="6.5" :fill="mono.MUTED">{{ unit }}</tspan>
          </text>

          <!-- 离群值：空心点（点在纸底上，不填充） -->
          <circle
            v-for="(o, k) in d.outlierDots"
            :key="`o-${k}`"
            class="tb-out"
            :cx="o.x"
            :cy="o.y"
            r="2.6"
            :fill="mono.PAPER"
            :stroke="mono.L[2]"
            stroke-width="1.1"
            :style="{ animationDelay: `${d.delay + 560 + k * 60}ms` }"
          >
            <title>{{ o.readout }}</title>
          </circle>

          <text
            class="tb-lab"
            :x="d.x"
            :y="geo.baseY + 13"
            text-anchor="middle"
            font-size="7.5"
            font-weight="700"
            letter-spacing="0.05em"
            :fill="mono.MUTED"
          >
            {{ d.label }}
          </text>
        </g>
      </g>
    </svg>

    <p class="tb-foot">
      箱 = 中间一半（q1–q3，描边不填充） · 中位数线 2× 宽 · 须 = 最小/最大 · 空心点 = 离群值 · 纵轴从 0 起
    </p>
  </div>
</template>

<style scoped>
.tb-empty {
  display: grid;
  place-items: center;
  height: 100%;
  color: #8f8e88; /* mono.MUTED */
  font-size: 12.5px;
}
.tb {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.tb-svg {
  display: block;
  flex: 1 1 auto;
  min-height: 0;
}
.tb-grid {
  opacity: 0;
  animation: tb-fade 0.6s ease both;
}
.tb-g {
  opacity: 0;
}
.tb-g--in {
  opacity: 1;
}
.tb-box,
.tb-cap,
.tb-median,
.tb-medval,
.tb-lab,
.tb-out {
  animation: tb-fade 0.6s ease both;
}
@keyframes tb-fade {
  from {
    opacity: 0;
  }
}
.tb-whisker {
  stroke-dasharray: 1;
  stroke-dashoffset: 1;
  transition: stroke-dashoffset 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
.tb-whisker--in {
  stroke-dashoffset: 0;
}
.tb-foot {
  margin: 4px 0 0;
  font-size: 10px;
  color: #8f8e88; /* mono.MUTED */
}
@media (prefers-reduced-motion: reduce) {
  .tb-g,
  .tb-grid {
    opacity: 1;
    animation: none;
  }
  .tb-box,
  .tb-cap,
  .tb-median,
  .tb-medval,
  .tb-lab,
  .tb-out {
    animation: none;
  }
  .tb-whisker {
    transition: none;
    stroke-dashoffset: 0;
  }
}
</style>
