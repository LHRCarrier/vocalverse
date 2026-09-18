<script setup lang="ts">
/**
 * 实时音准线（docs/06 §9.4 注记：练习辅助——"看得见的修正"）。
 *
 * 自包含：props 只给 detail（参考旋律 f0s）+ stream + active；
 * 内部 createLivePitch（useLivePitch）挂同一录音流 → YIN → 绘制；
 * 开关默认开、localStorage 记忆（vv_sing_live_pitch）；关闭即停检测（零 CPU）。
 * 参考线 t0 = 录音开始（不做整首对齐——那是离线评分的事，实时阶段正该暴露起唱偏移）。
 *
 * 2026-09-18 性能改造（跟唱卡顿根因实测见 local/sing-bench-before-*.json）：
 * - 帧数据 → 非响应式环形缓冲（lib/live-chart.createFrameRing）：零分配零 Vue 代理，
 *   旧实现每帧 `[...frames]` 重建（最长 4000 元素）且逐点走 proxy getter；
 * - 参考线 → 整曲 f0s 压平一次（flattenRefF0s），绘制只取可见窗内点（旧实现每帧 5625 点）；
 * - 视口 → 时间基（performance.now() - startedAt）60fps 匀速推进（旧实现按最后一帧跳变）；
 * - ctx/尺寸缓存、document.hidden 早退、动效档 off 时不连续插值（docs/31 规则 4 降级）。
 * 静音语义：静音仍 tick（V 帧为 null 不回调）→ 视口照走，只有「检测停摆 >1s」才冻结；
 * 末尾点随静音时长淡出（仅透明度，符合 docs/31）。
 */
import { computed, onUnmounted, ref, watch } from 'vue'

import type { SongDetail } from '@/api/sing'
import { createLivePitch } from '@/composables/useLivePitch'
import { useMotionTier } from '@/composables/useMotionTier'
import { createFrameRing, flattenRefF0s, LOOKAHEAD_MS, renderChart } from '@/lib/live-chart'
import type { LiveScoreRead } from '@/lib/live-score'

const props = defineProps<{
  detail: SongDetail
  stream: MediaStream | null
  active: boolean
}>()

const STORE_KEY = 'vv_sing_live_pitch'
const enabled = ref(localStorage.getItem(STORE_KEY) !== 'off')
function toggle(on: boolean) {
  enabled.value = on
  localStorage.setItem(STORE_KEY, on ? 'on' : 'off')
}

const canvas = ref<HTMLCanvasElement | null>(null)
const readText = ref<string | null>(null)
/** 滚动实时分（Worker 节流 ≤4Hz 回传；null = 参考不足/未出声，UI 显示「—」） */
const scoreInfo = ref<LiveScoreRead | null>(null)
const MAX_FRAMES = 4000 // 180s @ 60ms ≈ 3000 帧（防长歌内存）

/** 用户帧环形缓冲（非响应式：绘制热路径不经过 Vue 代理） */
const ring = createFrameRing(MAX_FRAMES)
/** 数据版本号：仅在有新帧时自增（动效档 off 时据此判断是否需要重画） */
let dataVersion = 0
/** 最近一帧（有声帧）的墙钟时间；0 = 本次尚未收到帧 */
let lastFrameWall = 0

const { tier } = useMotionTier()

const live = createLivePitch(
  (f) => {
    ring.push(f.tMs, f.f0)
    dataVersion += 1
    lastFrameWall = performance.now()
    const c = f.cent
    readText.value = `${f.note} ${Math.abs(c) < 1 ? '±0' : c > 0 ? `+${Math.round(c)}` : `−${Math.abs(Math.round(c))}`} cent`
  },
  60,
  (s) => {
    scoreInfo.value = s
  },
)

/** 实时分读数（0~100；null → 「—」） */
const scoreText = computed(() => scoreInfo.value?.score ?? null)
/** 副读数（在调率/出声率）走 title：主栏宽度有限，避免挤压读数与开关 */
const scoreTitle = computed(() => {
  const s = scoreInfo.value
  const tail = '练习参考（近 5 秒），最终评分以离线分析为准'
  if (!s || s.score == null) return `实时分：${tail}`
  return `近 5 秒：在调率 ${Math.round(s.hitRate * 100)}% · 出声率 ${Math.round(s.sungRate * 100)}% · ${tail}`
})

watch(
  () => [props.active, props.stream, enabled.value] as const,
  ([active, stream, on]) => {
    if (active && on && stream) {
      ring.clear()
      dataVersion = 0
      drawnVersion = -1
      lastFrameWall = 0
      readText.value = null
      scoreInfo.value = null
      live.start(stream, { refF0s })
    } else {
      live.stop()
      readText.value = null
      scoreInfo.value = null
    }
  },
)
watch(
  () => props.detail,
  () => {
    refF0s = flattenRefF0s(props.detail)
    ring.clear()
    dataVersion = 0
    drawnVersion = -1
    lastFrameWall = 0
    readText.value = null
    scoreInfo.value = null
  },
)

// —— 绘制编排（rAF 仅在 enabled && active 时跑；停止即零开销）——
/** 检测停摆阈值（worker/定时器死亡）→ 冻结视口；与「用户没出声」严格区分 */
const DEAD_MS = 1000
/** 静音淡出：有声帧缺失 >SILENT_MS 后开始淡出末尾点，历时 FADE_MS */
const SILENT_MS = 300
const FADE_MS = 1200
let raf = 0
let drawnVersion = -1

/** 参考旋律压平（detail 变化时重建；180s 歌 ≈ 5625 项 ≈ 22KB） */
let refF0s = flattenRefF0s(props.detail)

/** canvas 上下文与尺寸缓存（旧实现每帧 getContext + dpr/clientSize 比较） */
let ctx2d: CanvasRenderingContext2D | null = null
let cw = 0
let ch = 0
let cdpr = 0

function ensureCtx(el: HTMLCanvasElement): CanvasRenderingContext2D | null {
  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight
  if (!w || !h) return null
  const pw = Math.round(w * dpr)
  const ph = Math.round(h * dpr)
  if (el.width !== pw || el.height !== ph) {
    el.width = pw
    el.height = ph
  }
  const g = ctx2d ?? (ctx2d = el.getContext('2d'))
  if (!g) return null
  if (w !== cw || h !== ch || dpr !== cdpr) {
    // 尺寸/DPR 变化（或 canvas 重建导致状态复位）才重设变换
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    cw = w
    ch = h
    cdpr = dpr
  }
  return g
}

function draw() {
  const el = canvas.value
  if (!el) return
  const g = ensureCtx(el)
  if (!g) return
  g.clearRect(0, 0, cw, ch)

  const n = ring.length()
  const lastT = n ? ring.tAt(n - 1) : 0
  const now = performance.now()
  const headAlpha =
    lastFrameWall > 0 && now - lastFrameWall > SILENT_MS
      ? Math.max(0.15, 1 - (now - lastFrameWall - SILENT_MS) / FADE_MS)
      : 1
  // 时间基平滑推进；检测停摆（tick 也停了）或降级档 → 冻结/数据驱动
  const tickAt = live.lastTickAt
  const startedAt = live.startedAt
  const alive = tickAt != null && now - tickAt <= DEAD_MS
  const anchor = tier.value !== 'off' && alive && startedAt != null ? now - startedAt : lastT

  renderChart(g, {
    w: cw,
    h: ch,
    x1: anchor + LOOKAHEAD_MS,
    playheadT: anchor,
    headAlpha,
    refF0s,
    ring,
  })
}

function loop() {
  raf = requestAnimationFrame(loop)
  if (document.hidden) return // 隐藏页 rAF 本就不跑；恢复瞬间也不补画整帧
  if (tier.value === 'off' && dataVersion === drawnVersion) return // 降级档：只在新数据时重画
  drawnVersion = dataVersion
  draw()
}

watch(
  () => enabled.value && props.active,
  (on) => {
    cancelAnimationFrame(raf)
    if (on) loop()
  },
  { immediate: true },
)

onUnmounted(() => {
  live.stop()
  cancelAnimationFrame(raf)
})
</script>

<template>
  <div class="live-pitch" :class="{ 'live-pitch--off': !enabled }">
    <div class="live-pitch__bar">
      <span class="live-pitch__read" :class="{ 'live-pitch__read--muted': !readText }">
        {{ readText ?? '—' }}
      </span>
      <span
        class="live-pitch__score"
        :class="{ 'live-pitch__score--muted': scoreText == null }"
        :title="scoreTitle"
      >
        实时分 <b>{{ scoreText ?? '—' }}</b>
      </span>
      <label class="live-pitch__toggle">
        <input type="checkbox" :checked="enabled" @change="toggle(($event.target as HTMLInputElement).checked)">
        实时音准线
      </label>
    </div>
    <p class="live-pitch__hint">实时参考线 · 评分以离线分析为准</p>
    <canvas ref="canvas" class="live-pitch__canvas" />
  </div>
</template>

<style scoped>
.live-pitch {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: #f7f6f3;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  padding: 8px;
}
.live-pitch--off .live-pitch__canvas {
  display: none;
}
.live-pitch__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: #5c6160;
}
.live-pitch__read {
  min-width: 92px;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  font-size: 13px;
  color: #1f7a4d;
}
.live-pitch__read--muted {
  color: #999;
  font-weight: 400;
}
.live-pitch__score {
  font-variant-numeric: tabular-nums;
  color: #5c6160;
  white-space: nowrap;
}
.live-pitch__score b {
  font-size: 13px;
  color: #1f7a4d;
}
.live-pitch__score--muted b {
  font-size: inherit;
  font-weight: 400;
  color: #999;
}
.live-pitch__hint {
  margin: 0;
  font-size: 11px;
  color: #8a8f8e;
}
.live-pitch__toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  cursor: pointer;
  user-select: none;
}
.live-pitch__canvas {
  width: 100%;
  height: 120px;
  display: block;
}
</style>