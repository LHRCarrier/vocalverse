/**
 * 跟唱面板歌词滚动 · 对轴纯函数（2026-09-21）。
 *
 * 时间轴口径（docs/06 §9.4）：`SongLine.start_ms/end_ms` 就是 LRC 的 `offset_ms`
 * （相对**歌曲音频开头**），后端 `pitch_ref` 也按同一组 offset 从音轨切出，
 * 前端播放的也是同一条 `audio_url` → **LRC 时间轴 = 参考旋律时间轴 = 音频时间轴**。
 * 因此「听参考旋律」用 `audio.currentTime`、「跟唱」用「录音已用时长」作同一游标，
 * 两种模式的滚动频率天然一致（见 {@link resolveLyricTimeMs}）。
 *
 * 为什么另起模块而不复用 `audio/word-timeline.ts`：那是 ASR **词级**、`{word,start,end}`
 * 且单位是**秒**；这里是 LRC **句级**、`{seq,startMs,endMs,text}` 且单位是**毫秒**——
 * 强行映射要来回换单位。语义保持一致（空隙保持上一句、早于首句返回 -1），便于对照阅读。
 *
 * 纯函数、零 DOM、零副作用（组件层只渲染）——与仓库「对轴逻辑放纯函数」约定一致。
 */

/** 归一后的歌词行（毫秒；`endMs` 已推断，必定 > startMs） */
export interface LyricLine {
  seq: number
  startMs: number
  endMs: number
  text: string
}

/** 末句缺 `end_ms` 且无下一句可推断时的兜底句长（ms） */
const FALLBACK_LINE_MS = 2000

/** 后端下发的原始行（`end_ms`/`text` 可选；容忍 null/undefined 字段与 null 元素） */
export interface RawLyricLine {
  seq?: number | null
  start_ms?: number | null
  end_ms?: number | null
  text?: string | null
}

/** 容错入参（与 audio/word-timeline.ts 的 `RawWord[] | null | undefined` 同口径） */
export type RawLyricLines = (RawLyricLine | null | undefined)[] | null | undefined

/**
 * 归一：过滤坏条目（无/非法/负 `start_ms`），按 `startMs` 升序，
 * `endMs` 三级推断 = 显式 `end_ms` → 下一句 `start_ms` → `startMs + FALLBACK_LINE_MS`。
 * 非数值/倒序的显式 `end_ms` 一律走下一级（不抛异常）。
 */
export function toLyricLines(lines: RawLyricLines): LyricLine[] {
  const ok = (lines ?? [])
    .filter(
      (l): l is RawLyricLine & { start_ms: number } =>
        !!l && typeof l.start_ms === 'number' && Number.isFinite(l.start_ms) && l.start_ms >= 0,
    )
    .slice()
    .sort((a, b) => a.start_ms - b.start_ms)

  return ok.map((l, i) => {
    const startMs = l.start_ms
    const explicit = typeof l.end_ms === 'number' && Number.isFinite(l.end_ms) ? l.end_ms : null
    const nextStart = ok[i + 1]?.start_ms ?? null
    let endMs = explicit != null && explicit > startMs ? explicit : (nextStart ?? startMs + FALLBACK_LINE_MS)
    if (endMs <= startMs) endMs = startMs + FALLBACK_LINE_MS // 末句与下一句同刻的退化保护
    return { seq: l.seq ?? i + 1, startMs, endMs, text: l.text ?? '' }
  })
}

/**
 * 当前句下标 = 最新「已开始」（`startMs <= tMs`）的句；早于首句 → -1。
 * 句间空隙**保持上一句**（K 歌语义：换气时不回退到"无当前句"）。
 */
export function activeLineIndex(lines: LyricLine[], tMs: number): number {
  let idx = -1
  for (let i = 0; i < lines.length; i += 1) {
    if (lines[i].startMs <= tMs) idx = i
    else break
  }
  return idx
}

/** 句内进度 0..1（`startMs`→`endMs` 线性映射，越界 clamp；退化区间 → 0） */
export function lineProgress(lines: LyricLine[], index: number, tMs: number): number {
  const line = lines[index]
  if (!line) return 0
  const span = line.endMs - line.startMs
  if (span <= 0) return 0
  return Math.min(1, Math.max(0, (tMs - line.startMs) / span))
}

/** 歌词游标所需的时钟输入 */
export interface LyricClockInput {
  /** 参考旋律是否在播 */
  playing: boolean
  /** 参考音频当前位置（ms；非播放态无意义） */
  audioMs: number
  /** 是否正在跟唱录音 */
  recording: boolean
  /** 本次录音起点（`performance.now()`；未在录音 → null） */
  recStartAt: number | null
  /**
   * 本次录音中「**首次检出人声**」的相对时刻（ms，相对 `recStartAt`）；null = 尚未开口。
   * 跟唱游标以它为锚点（2026-09-21 用户口径：开口那一刻回到第一句），
   * 之后按与参考旋律相同的速率推进（句间距不变 → 频率一致）。
   */
  voiceAtMs: number | null
  /** 首句 `startMs`（锚点目标：开口时游标 = 首句；无歌词 → 0） */
  firstLineMs: number
  /** 当前时刻（`performance.now()`） */
  now: number
}

/**
 * 解出当前歌词时间轴位置（ms）；无有效来源 → null（歌词回顶部、无高亮）。
 *
 * 两种模式（同一条 LRC 绝对时间轴，只换游标）：
 * - **听参考旋律**：`audio.currentTime`（严格对齐音频）；
 * - **跟唱**：`首句 startMs + (已开口时长)` —— 已开口时长 = `now − recStartAt − voiceAtMs`。
 *   即「开口那一刻」游标落在首句，之后与参考旋律**同速率**推进（相邻句间隔不变）。
 *   尚未开口（`voiceAtMs == null`）→ null（不预跑，等开口）。
 */
export function resolveLyricTimeMs(input: LyricClockInput): number | null {
  if (input.playing) return Math.max(0, input.audioMs)
  if (!input.recording || input.recStartAt == null) return null
  if (input.voiceAtMs == null) return null
  const singingMs = Math.max(0, input.now - input.recStartAt - input.voiceAtMs)
  return Math.max(0, input.firstLineMs + singingMs)
}

/** 播放位置数字显示（`mm:ss`；null → `--:--`）。取代传统时间轴进度条（2026-09-21）。 */
export function formatClock(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '--:--'
  const total = Math.floor(ms / 1000)
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/**
 * 当前句与某句的距离（用于「仅中间三句清晰」的分层：|d| ≤ 1 清晰、2..BLUR_MAX 虚化、更远不处理）。
 * 无当前句（`current < 0`）→ 返回 `Number.POSITIVE_INFINITY`。
 */
export function lineDistance(current: number, index: number): number {
  return current < 0 ? Number.POSITIVE_INFINITY : Math.abs(index - current)
}

/** 动效档位（与 `composables/useMotionTier` 同构；此处只用类型，避免 lib → composable 的运行时依赖） */
export type LyricMotionTier = 'high' | 'low' | 'off'

/**
 * 某句的不透明度级别（2026-09-22 按用户视频模板：**靠透明度渐隐表达远近**，不用模糊）：
 * 0 = 焦点句（最亮/加粗/放大）、1~3 = 越远越淡。CSS 用 `.is-dim-0/1/2/3` 映射到具体值。
 */
export function dimLevel(distance: number): number {
  if (!Number.isFinite(distance)) return 3
  return Math.min(3, Math.max(0, Math.round(distance)))
}

/**
 * 视口中心最近的行下标（**手动翻动时"始终聚焦中心的句子"**，2026-09-22 用户口径）。
 *
 * 行等高（`L`）且内容顶部留白 `padTop`（= (视口高 − L)/2，用于首/末句也能居中）时，
 * 视口中心在内容坐标系里的位置为 `scrollTop + boxH/2`，落在第 `(该值 − padTop) / L` 行上。
 * 纯算术、**不做逐行 getBoundingClientRect**（几十行的歌逐帧读 rect 会触发强制同步布局）。
 */
export function nearestLineIndex(
  scrollTop: number,
  boxHeight: number,
  padTop: number,
  lineHeight: number,
  count: number,
): number {
  if (count <= 0 || lineHeight <= 0) return -1
  const centerInContent = scrollTop + boxHeight / 2
  const idx = Math.round((centerInContent - padTop) / lineHeight - 0.5)
  return Math.min(count - 1, Math.max(0, idx))
}
