/**
 * 跟唱面板歌词时钟（2026-09-21）：把「参考音频位置」与「录音已用时长」解成**同一条
 * LRC 时间轴**上的游标，供歌词滚动使用（口径见 lib/sing-lyrics.ts 头注释）。
 *
 * 为什么用 rAF 而不是 `audio.ontimeupdate`：`timeupdate` 只有 ~4Hz，句内进度线会一格一格跳、
 * 逐句吸附滚动也会滞后；rAF（≈60Hz）读 `audio.currentTime` 才能得到连续推进。
 * 循环**仅在播放或录音时运行**，空闲零开销；`document.hidden` 时跳过采样（隐藏页 rAF 本就不跑）。
 */
import { onUnmounted, ref, watch, type Ref } from 'vue'

import { resolveLyricTimeMs } from '@/lib/sing-lyrics'

export interface SingLyricClockOptions {
  /** 参考旋律是否在播（`useReferenceAudio().playing`） */
  playing: Ref<boolean>
  /** 是否正在跟唱录音（**暂停中也保持 true**：会话未结束） */
  recording: Ref<boolean>
  /** 录音是否暂停中（2026-09-22 深色录唱页新增）：暂停段不计入游标与已录时长 */
  paused?: Ref<boolean>
  /** 参考音频当前位置（ms）——`useReferenceAudio().currentMs` */
  audioMs: () => number
  /** 本次录音中「首次检出人声」的相对时刻（ms）——由 `LivePitchChart` 的 `firstVoice` 事件给出 */
  voiceAtMs: Ref<number | null>
  /** 首句 `startMs`（跟唱锚点：开口那一刻回到第一句） */
  firstLineMs: () => number
}

export interface SingLyricClock {
  /** 当前歌词时间轴位置（ms）；无有效来源 → null（歌词回顶部、无高亮） */
  timeMs: Ref<number | null>
  /**
   * 本次录音**已用时长**（ms，**整秒量化**）；未在录音 → null。
   *
   * 与 `timeMs` 的区别：`timeMs` 是「首帧人声锚点 + 已开口时长」的**歌词轴**位置（跟唱时约等于
   * 「唱到第几秒」，开口前是 null）；本值是从按下「开始跟唱」起算的**录音轴**时长，
   * 供面板头部的计时/进度线使用（2026-09-22 排版优化：录音上限 3 分钟此前只写在底部一行小字里）。
   * 量化到秒是因为计时只需 1Hz —— 不量化就会跟着 rAF 每帧触发一次响应式更新。
   */
  elapsedMs: Ref<number | null>
  /**
   * 原始**有效录音时刻**（ms，未量化、已扣暂停）；未在录音 → null。
   * 用途：给音准引导条当**唯一时间基**——引导条与歌词必须共用同一条轴，
   * 否则引导条用「检测起点 + 真实墙钟」会含暂停时长，暂停后整体错位（2026-09-22 实测 bug）。
   */
  recMs: Ref<number | null>
}

export function useSingLyricClock(opts: SingLyricClockOptions): SingLyricClock {
  const timeMs = ref<number | null>(null)
  const elapsedMs = ref<number | null>(null)
  const recMs = ref<number | null>(null)
  /** 本次录音起点（`performance.now()`）：`recording` 上升沿记录，下降沿清空 */
  let recStartAt: number | null = null
  /**
   * 暂停累计（ms）与当前暂停段起点（2026-09-22）：
   * `MediaRecorder.pause()` 期间音频不增长，歌词游标与已录时长也必须**冻结**——
   * 做法是把「当前时刻」折算成**有效录音时刻**（`now - 已暂停累计 - 本段已暂停`），
   * 于是 `resolveLyricTimeMs` 与 `elapsedMs` 都天然不含暂停段，无需改纯函数口径。
   */
  let pausedAccum = 0
  let pausedAt: number | null = null
  let raf = 0

  /** 折算到「有效录音时刻」（`performance.now()` 同域，只是扣掉暂停） */
  function effectiveNow(): number {
    const now = performance.now()
    const segment = pausedAt != null ? now - pausedAt : 0
    return now - pausedAccum - segment
  }

  function sample() {
    const now = effectiveNow()
    timeMs.value = resolveLyricTimeMs({
      playing: opts.playing.value,
      audioMs: opts.audioMs(),
      recording: opts.recording.value,
      recStartAt,
      voiceAtMs: opts.voiceAtMs.value,
      firstLineMs: opts.firstLineMs(),
      now,
    })
    elapsedMs.value =
      opts.recording.value && recStartAt != null
        ? Math.floor(Math.max(0, now - recStartAt) / 1000) * 1000
        : null
    recMs.value = opts.recording.value && recStartAt != null ? Math.max(0, now - recStartAt) : null
  }

  function loop() {
    raf = requestAnimationFrame(loop)
    if (document.hidden) return
    sample()
  }

  const active = () => opts.playing.value || opts.recording.value

  watch(
    opts.recording,
    (on) => {
      recStartAt = on ? performance.now() : null
      if (!on) {
        pausedAccum = 0
        pausedAt = null
      }
    },
    { immediate: true },
  )

  /** 暂停/继续：记录暂停段并把游标按「有效录音时刻」重算（rAF 继续跑，只是时间不再前进） */
  if (opts.paused) {
    watch(opts.paused, (isPaused) => {
      if (isPaused) {
        pausedAt = performance.now()
        return
      }
      if (pausedAt != null) {
        pausedAccum += performance.now() - pausedAt
        pausedAt = null
      }
      sample()
    })
  }

  watch(
    active,
    (on) => {
      cancelAnimationFrame(raf)
      if (on) loop()
      // 停止播放/录音：游标清空（再次播放是从头播，歌词回顶部与之一致）
      else sample()
    },
    { immediate: true },
  )

  onUnmounted(() => cancelAnimationFrame(raf))

  return { timeMs, elapsedMs, recMs }
}
