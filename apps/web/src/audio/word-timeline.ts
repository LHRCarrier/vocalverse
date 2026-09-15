/**
 * 词级时间轴纯函数（B4，2026-09-09）：ASR 词时间戳 → 逐词高亮/回放对轴。
 *
 * 输入与后端 SSE `turn_end.words` 同构：[{word, start, end, ...}]（秒，whisper
 * word_timestamps）；本模块零副作用、零 DOM——组件层只做渲染，对轴逻辑全在此。
 * 容忍口径与后端 fluency.py 一致（坏条目/坏时间戳过滤，不抛异常）。
 */

export interface WordSpan {
  word: string
  start: number
  end: number
}

type RawWord = Partial<WordSpan> | null | undefined

/** 归一化：过滤无词/非数值/负跨度条目，按 start 升序（返回新数组，不改输入） */
export function normalizeTimeline(words: RawWord[] | null | undefined): WordSpan[] {
  return (words ?? [])
    .filter(
      (w): w is WordSpan =>
        !!w &&
        typeof w.word === 'string' &&
        w.word.length > 0 &&
        typeof w.start === 'number' &&
        Number.isFinite(w.start) &&
        typeof w.end === 'number' &&
        Number.isFinite(w.end) &&
        w.end > w.start,
    )
    .map((w) => ({ word: w.word, start: w.start, end: w.end }))
    .sort((a, b) => a.start - b.start)
}

/** 逐词高亮下标 = 最新已开始（start <= t）的词；t 早于首词 → -1；晚于末词 → 末词下标 */
export function startedWordIndex(timeline: WordSpan[], t: number): number {
  const words = normalizeTimeline(timeline)
  let idx = -1
  for (let i = 0; i < words.length; i++) {
    if (words[i].start <= t) idx = i
    else break
  }
  return idx
}

/** 回放进度 0..1（首词 start → 末词 end 线性映射；空/退化时间轴 → 0；越界 clamp） */
export function timelineProgress(timeline: WordSpan[], t: number): number {
  const words = normalizeTimeline(timeline)
  if (words.length === 0) return 0
  const first = words[0].start
  const last = words[words.length - 1].end
  if (last <= first) return 0
  return Math.min(1, Math.max(0, (t - first) / (last - first)))
}
