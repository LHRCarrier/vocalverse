/**
 * 阅读器 · 词切分与批注坐标纯函数（docs/45 §3：章节内 char offset 坐标系 · 服务端权威）。
 *
 * 渲染：句子 text（服务端归一）→ 词片段（[word] + 分隔文本）；批注偏移与
 * split_chapter 的 sentence.start/end 同坐标系（docs/46 V-20）。
 * 划词批注 v1 仅限**句内**（跨句选择忽略——输出按句取交集，docs/45 §6 登记）。
 */

export interface WordPiece {
  word: string
  start: number
  end: number
}

export interface TextPiece {
  text: string
  start: number
  end: number
  word: string | null
}

const WORD_RE = /[A-Za-z][A-Za-z'’-]*/g

/** 句文本 → 词块 + 分隔文本块（保留原文空白/标点，偏移连续） */
export function splitPieceWords(sentenceText: string): TextPiece[] {
  const pieces: TextPiece[] = []
  let cursor = 0
  for (const m of sentenceText.matchAll(WORD_RE)) {
    const word = m[0]
    const start = m.index ?? 0
    const end = start + word.length
    if (start > cursor) {
      pieces.push({ text: sentenceText.slice(cursor, start), start: cursor, end: start, word: null })
    }
    pieces.push({ text: word, start, end, word })
    cursor = end
  }
  if (cursor < sentenceText.length) {
    pieces.push({ text: sentenceText.slice(cursor), start: cursor, end: sentenceText.length, word: null })
  }
  return pieces
}

/**
 * 划选坐标：给定句内相对偏移（DOM Range 相对句首）与句子绝对 start，
 * 返回句内 [start,end]（跨句/越界/倒置 → null，v1 只做句内批注）。
 */
export function intersectSentence(relStart: number, relEnd: number, sentenceStart: number, sentenceLen: number): [number, number] | null {
  if (relEnd <= relStart || relStart < 0 || relEnd > sentenceLen) return null
  return [sentenceStart + relStart, sentenceStart + relEnd]
}

/** 生词标记集合：小写词形并入（词典头词 + 词形均可标出） */
export function vocabWordSet(entries: Array<{ word: string }>): Set<string> {
  return new Set(entries.map((e) => e.word.toLowerCase()))
}

/* ---------------------------------------------------------------- 批注渲染分段
 * 2026-09-10 修复「批注跳过去看不到、被批注的文本无颜色」（组长手机实测）：
 * 渲染层原先把批注只映射成句子级 .is-annotated 下划线，且只认 kind==='highlight'
 * （kind==='note' 的笔记批注连下划线都没有）→ 页面上完全看不出批注。
 * 这里把「词块」与「批注区间」求交，切成可直接上色的渲染段：
 *   · 段文本仍是句子内的连续切片（拼接后与原文逐字相等）；
 *   · 段保留 word（用于点词查义）——词被批注边界切开的子段仍带同一个 word，
 *     这样点任一部分都能查到整词；
 *   · 段带 ann（该段覆盖的批注：优先带笔记的那条，其次最早的一条）。
 *
 * 2026-09-09 二次改版（组长手机实测：「句首那根竖条很奇怪、不明显」）：
 * 标记从「句首竖条 + 段尾竖条」改为**句尾上标编号标签**（[1] [2]…，按句内序号、按批注色区分），
 * 因此 `SentenceSegment.noteMarker` 与段尾角标一并下线（见 MobileReaderView 模板）。
 */

/** 渲染段（句子内连续切片） */
export interface SentenceSegment {
  text: string
  /** 该段所属词（整词，用于查词；非词段为 null） */
  word: string | null
  /** 覆盖该段的批注（无批注为 null） */
  ann: AnnotationRange | null
}

/** 批注渲染所需的最小字段（与 api/reading.AnnotationItem 结构兼容） */
export interface AnnotationRange {
  id: number
  start_offset: number
  end_offset: number
  kind: 'highlight' | 'note'
  color?: string | null
  note?: string | null
  text_snippet?: string | null
}

/**
 * 句子 → 渲染段（词块 × 批注区间求交）。
 * @param sentenceText 句子原文（服务端归一）
 * @param sentenceStart 句子在章内的绝对起始 offset
 * @param annotations 本章批注（绝对 offset 坐标系）
 */
export function buildSentenceSegments(
  sentenceText: string,
  sentenceStart: number,
  annotations: ReadonlyArray<AnnotationRange>,
): SentenceSegment[] {
  const pieces = splitPieceWords(sentenceText)
  const relevant = annotations.filter(
    (a) => a.end_offset > sentenceStart && a.start_offset < sentenceStart + sentenceText.length,
  )
  const segments: SentenceSegment[] = []

  for (const piece of pieces) {
    const absStart = sentenceStart + piece.start
    const absEnd = sentenceStart + piece.end
    const hits = relevant.filter((a) => a.end_offset > absStart && a.start_offset < absEnd)
    if (hits.length === 0) {
      segments.push({ text: piece.text, word: piece.word, ann: null })
      continue
    }
    const cuts = new Set<number>([absStart, absEnd])
    for (const a of hits) {
      cuts.add(Math.max(absStart, a.start_offset))
      cuts.add(Math.min(absEnd, a.end_offset))
    }
    const sorted = [...cuts].filter((c) => c >= absStart && c <= absEnd).sort((x, y) => x - y)
    for (let i = 0; i < sorted.length - 1; i += 1) {
      const s = sorted[i]
      const e = sorted[i + 1]
      if (e <= s) continue
      const covering = hits
        .filter((a) => a.start_offset <= s && a.end_offset >= e)
        .sort((a, b) => Number(b.kind === 'note') - Number(a.kind === 'note') || a.start_offset - b.start_offset)
      segments.push({
        text: sentenceText.slice(s - sentenceStart, e - sentenceStart),
        word: piece.word,
        ann: covering[0] ?? null,
      })
    }
  }

  // 句尾编号标签在视图层按「该句批注按起点排序」直接渲染（见 annotationsOfSentence）
  return segments
}

/** 句子是否有批注（含笔记类——渲染判断用，修复前只认 highlight） */
export function sentenceHasAnnotation(
  annotations: ReadonlyArray<AnnotationRange>,
  sentenceStart: number,
  sentenceEnd: number,
): boolean {
  return annotations.some((a) => a.start_offset < sentenceEnd && a.end_offset > sentenceStart)
}

/** 该句的全部批注（按起点排序，供「本句批注」气泡） */
export function annotationsOfSentence(
  annotations: ReadonlyArray<AnnotationRange>,
  sentenceStart: number,
  sentenceEnd: number,
): AnnotationRange[] {
  return annotations
    .filter((a) => a.start_offset < sentenceEnd && a.end_offset > sentenceStart)
    .slice()
    .sort((a, b) => a.start_offset - b.start_offset)
}

/* ---------------------------------------------------------------- 批注配色安全
 * 2026-09-09 修复「暗黑模式下批注为粉色看不清」（组长手机实测）：
 * 渲染层原先把批注色**直接**写成 background（浅粉 #fbcfe8），而 night 主题正文墨色是
 * 浅灰 #d6d3cc → 浅底浅字，对比度 ≈1.08，等于不可读。
 * 修正（见 reader-uic.css 的 --ur-ann-mix 与 audio/annotation-colors.ts）：
 *   ① 颜色只作 CSS 自定义属性 --ur-ann-color 传入，由 CSS 按主题与纸面底色 color-mix 出
 *      「同色系但足够对比」的底色，文字色统一 var(--ur-theme-ink)；
 *   ② 颜色是不可信输入 → 只放行色板内的值（safeAnnColor 见 annotation-colors.ts）。
 */
export { ANN_FALLBACK_COLOR, safeAnnColor } from './annotation-colors'

/** 词点击命中的原文（剥离首尾标点由 normalize 负责——这里只取词形） */
export function pieceAt(pieces: TextPiece[], relOffset: number): TextPiece | null {
  let acc = 0
  for (const p of pieces) {
    if (relOffset >= acc && relOffset < acc + Math.max(1, p.text.length)) {
      return p.word ? p : null
    }
    acc += p.text.length
  }
  return null
}
