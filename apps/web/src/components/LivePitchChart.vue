<script setup lang="ts">
/**
 * 实时音准线（docs/06 §9.4 注记：练习辅助——"看得见的修正"）。
 *
 * 自包含：props 只给 detail（参考旋律 f0s）+ stream + active；
 * 内部 createLivePitch（useLivePitch）挂同一录音流 → YIN → 绘制；
 * 开关默认开、localStorage 记忆（vv_sing_live_pitch）；关闭即停检测（零 CPU）。
 * 参考线 t0 = 录音开始（不做整首对齐——那是离线评分的事，实时阶段正该暴露起唱偏移）。
 */
import { onUnmounted, ref, watch } from 'vue'

import type { SongDetail } from '@/api/sing'
import { createLivePitch, type LivePitchFrame } from '@/composables/useLivePitch'

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
const frames = ref<LivePitchFrame[]>([])
const readText = ref<string | null>(null)
const MAX_FRAMES = 4000 // 180s @ 60ms ≈ 3000 帧（防长歌内存）

const live = createLivePitch((f) => {
  frames.value = frames.value.length >= MAX_FRAMES ? [...frames.value.slice(1), f] : [...frames.value, f]
  const c = f.cent
  readText.value = `${f.note} ${Math.abs(c) < 1 ? '±0' : c > 0 ? `+${Math.round(c)}` : `−${Math.abs(Math.round(c))}`} cent`
})

watch(
  () => [props.active, props.stream, enabled.value] as const,
  ([active, stream, on]) => {
    if (active && on && stream) {
      frames.value = []
      readText.value = null
      live.start(stream)
    } else {
      live.stop()
      readText.value = null
    }
  },
)
watch(
  () => props.detail,
  () => {
    frames.value = []
    readText.value = null
  },
)

// —— 绘制（rAF 仅在 enabled && active 时跑；停止即零开销）——
const HOP_MS = 32 // 参考提取同 hop（docs/06 §9.4：hop 512 @16k = 32ms）
const WIN_MS = 8000
const FMIN = 65
const FMAX = 800
let raf = 0
const NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function drawGrid(g: CanvasRenderingContext2D, w: number, y2f: (f: number) => number) {
  g.font = '9px sans-serif'
  g.strokeStyle = 'rgba(0,0,0,.08)'
  g.fillStyle = '#6b6f6e'
  for (let midi = 48; midi <= 84; midi += 12) {
    const y = y2f(440 * 2 ** ((midi - 69) / 12))
    g.beginPath()
    g.moveTo(4, y)
    g.lineTo(w - 4, y)
    g.stroke()
    g.fillText(`${NAMES[midi % 12]}${Math.floor(midi / 12) - 1}`, 6, y - 2)
  }
}

function drawRefLine(
  g: CanvasRenderingContext2D,
  w: number,
  x2p: (t: number) => number,
  y2f: (f: number) => number,
) {
  g.strokeStyle = '#3a8fb7'
  g.lineWidth = 1.6
  g.globalAlpha = 0.9
  for (const line of props.detail.lines) {
    const f0s = line.pitch_ref?.f0s ?? []
    if (!f0s.length) continue
    g.beginPath()
    let started = false
    for (let i = 0; i < f0s.length; i += 1) {
      const f = f0s[i]
      if (f <= 0) {
        started = false
        continue
      }
      const px = x2p((line.start_ms ?? 0) + i * HOP_MS)
      if (px < 4 || px > w - 4) continue
      if (!started) {
        g.moveTo(px, y2f(f))
        started = true
      } else {
        g.lineTo(px, y2f(f))
      }
    }
    g.stroke()
  }
  g.globalAlpha = 1
}

function drawUserTrace(
  g: CanvasRenderingContext2D,
  x0: number,
  x1: number,
  x2p: (t: number) => number,
  y2f: (f: number) => number,
) {
  g.strokeStyle = '#e07a3f'
  g.lineWidth = 1.8
  g.beginPath()
  let started = false
  for (const f of frames.value) {
    if (f.tMs < x0 || f.tMs > x1) {
      started = false
      continue
    }
    const px = x2p(f.tMs)
    const py = y2f(f.f0)
    if (!started) {
      g.moveTo(px, py)
      started = true
    } else {
      g.lineTo(px, py)
    }
  }
  g.stroke()
  const last = frames.value[frames.value.length - 1]
  if (last && readText.value && last.tMs >= x0 && last.tMs <= x1) {
    g.fillStyle = '#e07a3f'
    g.beginPath()
    g.arc(x2p(last.tMs), y2f(last.f0), 3, 0, Math.PI * 2)
    g.fill()
  }
}

function draw() {
  const el = canvas.value
  if (!el) return
  const dpr = window.devicePixelRatio || 1
  const w = el.clientWidth
  const h = el.clientHeight
  if (!w || !h) return
  if (el.width !== Math.round(w * dpr) || el.height !== Math.round(h * dpr)) {
    el.width = Math.round(w * dpr)
    el.height = Math.round(h * dpr)
  }
  const g = el.getContext('2d')
  if (!g) return
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, w, h)

  const last = frames.value[frames.value.length - 1]
  const now = last?.tMs ?? 0
  const x1 = now + 500
  const x0 = x1 - WIN_MS
  const x2p = (t: number) => 4 + ((t - x0) / WIN_MS) * (w - 8)
  const logFmin = Math.log2(FMIN)
  const y2f = (f: number) => 6 + (1 - (Math.log2(f) - logFmin) / (Math.log2(FMAX) - logFmin)) * (h - 24)

  drawGrid(g, w, y2f)
  drawRefLine(g, w, x2p, y2f)
  drawUserTrace(g, x0, x1, x2p, y2f)

  // 进度竖线
  g.strokeStyle = 'rgba(0,0,0,.25)'
  g.lineWidth = 1
  const px = x2p(Math.min(now, x1))
  g.beginPath()
  g.moveTo(px, 6)
  g.lineTo(px, h - 14)
  g.stroke()
}

function loop() {
  draw()
  raf = requestAnimationFrame(loop)
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
      <span class="live-pitch__hint">实时参考线 · 评分以离线分析为准</span>
      <label class="live-pitch__toggle">
        <input type="checkbox" :checked="enabled" @change="toggle(($event.target as HTMLInputElement).checked)">
        实时音准线
      </label>
    </div>
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
.live-pitch__hint {
  flex: 1;
}
.live-pitch__toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
}
.live-pitch__canvas {
  width: 100%;
  height: 120px;
  display: block;
}
</style>
