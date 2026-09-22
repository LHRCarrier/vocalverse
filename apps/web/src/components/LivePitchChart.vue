<script setup lang="ts">
/**
 * 音准引导条（2026-09-22 深色录唱页重做：对齐参考图的「橙色横条 + 走针」）。
 *
 * 历史：本组件原先是「滚动实时音准曲线」（参考线 + 用户曲线 + 静音灰线）。参考图要的是
 * **目标音符块**那条带，故渲染层换成 `lib/sing-note-lane.ts`；**检测层一字未动**——
 * 同一麦克风流（`MediaRecorder` 共用，不二次申请）→ Worker 内 YIN → 环形缓冲，
 * 只是把点画成「音符块 + 用户轨迹 + 走针」。
 *
 * 职责边界（沿用旧注释的口径）：
 * - 参考块来自离线 pyin 提取的 `pitch_ref.midi`（与评分同源），**不是**实时算出来的；
 * - 实时曲线 ≠ 评分线（评分 = 离线 librosa.pyin + DTW），此条仅为**练习辅助**；
 * - `enabled`（视图的「实时曲线」开关）**只管是否画用户轨迹**：检测照常跑，
 *   因为歌词滚动的「首帧人声锚点」依赖 `firstVoice`；
 * - `paused`（录音暂停）→ 走针冻结、整带降亮（暂停段不入音频，游标也不该前进）；
 * - 实时分经 `score` 事件上报给顶栏评级条（≤4Hz；旧实现把读数画在组件内）。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import type { SongDetail } from '@/api/sing'
import { createLivePitch } from '@/composables/useLivePitch'
import { useMotionTier } from '@/composables/useMotionTier'
import { createFrameRing, flattenRefF0s, LOOKAHEAD_MS } from '@/lib/live-chart'
import { flattenRefMidi, midiSegments, renderNoteLane } from '@/lib/sing-note-lane'
import type { LiveScoreRead } from '@/lib/live-score'

const props = withDefaults(
  defineProps<{
    detail: SongDetail
    stream: MediaStream | null
    active: boolean
    /** 是否画**用户轨迹**（开关见 `useLivePitchPref`）；检测不受它影响 */
    enabled?: boolean
    /** 录音暂停中：走针冻结、整带降亮 */
    paused?: boolean
    /**
     * 当前**有效录音时刻**（ms，已扣掉暂停；由 `useSingLyricClock.recMs` 提供）。
     * 录音中必须传：引导条与歌词共用同一条时间轴，暂停才不会错位。
     */
    clockMs?: number | null
  }>(),
  { enabled: true, paused: false, clockMs: null },
)

const emit = defineEmits<{
  (e: 'firstVoice', tMs: number): void
  /** 实时分（近 5 秒在调率×出声率，练习参考口径）；null = 参考不足/未出声 */
  (e: 'score', score: number | null): void
}>()

/** 显示开关（只管用户轨迹，不参与检测起停） */
const enabled = computed(() => props.enabled !== false)

const canvas = ref<HTMLCanvasElement | null>(null)
const readText = ref<string | null>(null)
const scoreInfo = ref<LiveScoreRead | null>(null)
/**
 * 引导条当前时间基（ms，= 走针位置）。**低频更新（≤4Hz）**：只用于无障碍名与联调探针读值，
 * 不进绘制热路径（绘制仍走 rAF 本地变量）——暂停诊断就是靠它把「曲线跳回上一次暂停位置」量出来的。
 */
const anchorShown = ref(0)
let lastAnchorEmit = -1e9
const MAX_FRAMES = 4000 // 180s @ 60ms ≈ 3000 帧（防长歌内存）

/** 用户帧环形缓冲（非响应式：绘制热路径不经过 Vue 代理） */
const ring = createFrameRing(MAX_FRAMES)
/** 数据版本号：仅在有新帧时自增（动效档 off 时据此判断是否需要重画） */
let dataVersion = 0
let lastFrameWall = 0
let voiceReported = false
let lastScoreEmit = -1e9

const { tier } = useMotionTier()
/** Hz → MIDI（引导条的 y 轴单位；与 `pitch.py` 的 midi 同定义） */
const hzToMidi = (f: number) => 69 + 12 * Math.log2(f / 440)

const live = createLivePitch(
  (f) => {
    ring.push(f.tMs, f.f0)
    dataVersion += 1
    lastFrameWall = performance.now()
    if (!voiceReported) {
      voiceReported = true
      emit('firstVoice', f.tMs)
    }
    const c = f.cent
    readText.value = `${f.note} ${Math.abs(c) < 1 ? '±0' : c > 0 ? `+${Math.round(c)}` : `−${Math.abs(Math.round(c))}`} cent`
  },
  60,
  (s) => {
    scoreInfo.value = s
    // 顶栏评级条只要 ~4Hz：Worker 已节流 ≤4Hz，这里再按 250ms 去抖，避免抖动放大
    const now = performance.now()
    if (now - lastScoreEmit >= 250) {
      lastScoreEmit = now
      emit('score', s.score)
    }
  },
)

function resetState() {
  ring.clear()
  dataVersion = 0
  drawnVersion = -1
  lastFrameWall = 0
  voiceReported = false
  readText.value = null
  scoreInfo.value = null
}

/** 参考音符块（detail 变化时重建一次；整曲几百块，逐帧重算会白耗） */
let refMidi = flattenRefMidi(props.detail)
let segments = midiSegments(refMidi)
let refF0s = flattenRefF0s(props.detail)

watch(
  () => [props.active, props.stream] as const,
  ([active, stream]) => {
    if (active && stream) {
      resetState()
      live.start(stream, { refF0s })
    } else {
      live.stop()
      resetState()
    }
  },
)
watch(
  () => props.detail,
  () => {
    refMidi = flattenRefMidi(props.detail)
    segments = midiSegments(refMidi)
    refF0s = flattenRefF0s(props.detail)
    resetState()
  },
)

// —— 绘制编排（rAF 仅在 enabled/active 时跑；停止即零开销）——
/** 检测停摆阈值（worker/定时器死亡）→ 冻结视口；与「用户没出声」严格区分 */
const DEAD_MS = 1000
/** 静音淡出 */
const SILENT_MS = 300
const FADE_MS = 1200
/** 引导带视口宽度（ms）：参考图是「一段可读的乐句」，8 秒正好 1~2 句 */
const LANE_WINDOW_MS = 8000
let raf = 0
let drawnVersion = -1

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
    g.setTransform(dpr, 0, 0, dpr, 0, 0)
    cw = w
    ch = h
    cdpr = dpr
  }
  return g
}

/** 用户轨迹点（Hz → MIDI）；只取可见窗内，避免长歌逐帧遍历整环 */
function userPoints(windowFrom: number, windowTo: number): { t: number; midi: number }[] {
  const out: { t: number; midi: number }[] = []
  const n = ring.length()
  if (!n) return out
  for (let i = 0; i < n; i += 1) {
    const t = ring.tAt(i)
    if (t < windowFrom - 100) continue
    if (t > windowTo) break
    const f = ring.fAt(i)
    if (!f || f <= 0) continue
    out.push({ t, midi: hzToMidi(f) })
  }
  return out
}

function draw() {
  const el = canvas.value
  if (!el) return
  const g = ensureCtx(el)
  if (!g) return
  const n = ring.length()
  const lastT = n ? ring.tAt(n - 1) : 0
  const now = performance.now()
  const headAlpha =
    lastFrameWall > 0 && now - lastFrameWall > SILENT_MS
      ? Math.max(0, 1 - (now - lastFrameWall - SILENT_MS) / FADE_MS)
      : 1
  const tickAt = live.lastTickAt
  const startedAt = live.startedAt
  const alive = tickAt != null && now - tickAt <= DEAD_MS
  // 时间基：**单一时基** —— 录音中一律用视图传进来的「有效录音时刻」（已扣暂停），
  // 不再用 `now - startedAt`（那是检测起点，**含暂停时长** → 暂停后曲线会整体前跳/错位：
  // 2026-09-22 用户实测「曲线跳回上一次暂停的位置」的根因）。
  // 没有外部时基（未录音/未给）时退回检测起点或最后一帧。
  const anchor =
    props.clockMs != null
      ? props.clockMs
      : props.paused || tier.value === 'off' || !alive || startedAt == null
        ? lastT
        : now - startedAt
  if (now - lastAnchorEmit >= 250) {
    lastAnchorEmit = now
    anchorShown.value = Math.round(anchor)
  }

  renderNoteLane(g, {
    w: cw,
    h: ch,
    x1: anchor + LOOKAHEAD_MS,
    playheadT: anchor,
    windowMs: LANE_WINDOW_MS,
    refMidi,
    segments,
    // 开关关掉 → 不画用户轨迹（检测照常跑：锚点依赖它）
    userPoints: enabled.value ? userPoints(anchor - LANE_WINDOW_MS, anchor + LOOKAHEAD_MS) : [],
    headAlpha: enabled.value ? headAlpha : 0,
    paused: props.paused,
  })
}

function loop() {
  raf = requestAnimationFrame(loop)
  if (document.hidden) return
  const now = performance.now()
  if (readText.value && lastFrameWall > 0 && now - lastFrameWall > SILENT_MS) readText.value = null
  if (tier.value === 'off') {
    // 降级档：无连续插值，只在新数据时重画（docs/31 规则 4）
    if (dataVersion !== drawnVersion) {
      drawnVersion = dataVersion
      draw()
    }
    return
  }
  drawnVersion = dataVersion
  draw()
}

watch(
  // 2026-09-22 深色录唱页修正：rAF **只跟 `active`**——引导条本身（目标音符 + 走针）要一直走，
  // 「曲线」开关只管**用户轨迹**是否绘制。旧写法把开关也算进循环条件，关掉开关后引导条
  // 只剩挂载那**一帧**（真机实测：走针停在 0s，整条只剩最右边一个音符块）。
  () => props.active,
  (on) => {
    cancelAnimationFrame(raf)
    if (on) loop()
    else draw() // 停止录音：画一帧静态引导条（不残留用户轨迹）
  },
  { immediate: true },
)

/** 开关/暂停变化时补画一帧（未在录音时没有 rAF 循环，必须手动重画才看得到变化）；
 *  挂载后也补一帧：上面的 watch 在 setup 期跑，那时 `canvas` 还是 null（早退）。 */
watch(() => [enabled.value, props.paused] as const, () => {
  if (!props.active) draw()
})
onMounted(draw)

onUnmounted(() => {
  live.stop()
  cancelAnimationFrame(raf)
})
</script>

<template>
  <div
    class="sing-lane"
    :class="{ 'is-off': !enabled, 'is-paused': paused }"
    role="img"
    :aria-label="`音准引导条，当前 ${(anchorShown / 1000).toFixed(1)} 秒${paused ? '（已暂停）' : ''}`"
    :aria-valuenow="anchorShown"
  >
    <!-- 读数：音名 ±cent（静音回占位「—」）；实时分走顶栏评级条（`score` 事件） -->
    <span class="sing-lane__read" :class="{ 'is-muted': !readText }">{{ readText ?? '—' }}</span>
    <span class="sing-lane__note">{{ paused ? '已暂停' : enabled ? '实时音准' : '实时曲线已关' }}</span>
    <canvas ref="canvas" class="sing-lane__canvas" />
  </div>
</template>

<style scoped>
/* 音准引导带（深色）：底由 canvas 画，这里只管外框与读数覆盖层 */
.sing-lane {
  position: relative;
  height: 96px;
  border-radius: 14px;
  overflow: hidden;
  background: #131b20;
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.sing-lane__canvas {
  display: block;
  width: 100%;
  height: 100%;
}
.sing-lane__read {
  position: absolute;
  left: 10px;
  top: 8px;
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: #5ad2c0;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.6);
  pointer-events: none;
}
.sing-lane__read.is-muted {
  color: rgba(255, 255, 255, 0.35);
  font-weight: 400;
}
.sing-lane__note {
  position: absolute;
  right: 10px;
  top: 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.4);
  pointer-events: none;
}
</style>
