/**
 * 阅读器 · 词切分/批注坐标纯函数（docs/45 §3：章节内 char offset · 服务端权威坐标系）。
 */
import { describe, expect, it } from 'vitest'

import {
  annotationsOfSentence,
  buildSentenceSegments,
  intersectSentence,
  pieceAt,
  sentenceHasAnnotation,
  splitPieceWords,
  vocabWordSet,
} from '../reader-words'
import type { AnnotationRange } from '../reader-words'

describe('splitPieceWords', () => {
  it('切分并保留偏移连续性（撇号/连字符整词）', () => {
    const pieces = splitPieceWords("Alice's dream, \"wow!\"")
    const words = pieces.filter((p) => p.word)
    expect(words.map((w) => w.word)).toEqual(["Alice's", 'dream', 'wow'])
    // 偏移与原文切片一致
    const text = "Alice's dream, \"wow!\""
    for (const p of pieces) {
      expect(text.slice(p.start, p.end)).toBe(p.text)
    }
    // 拼接重建原文
    expect(pieces.map((p) => p.text).join('')).toBe(text)
  })

  it('连字符词不拆', () => {
    const pieces = splitPieceWords('Well-known o\u2019clock')
    expect(pieces.filter((p) => p.word).map((w) => w.word)).toEqual(['Well-known', 'o\u2019clock'])
  })

  it('空文本 → 空块', () => {
    expect(splitPieceWords('')).toEqual([])
  })

  it('pieceAt 命中词块', () => {
    const pieces = splitPieceWords('Hello world')
    expect(pieceAt(pieces, 1)?.word).toBe('Hello')
    expect(pieceAt(pieces, 6)?.word).toBe('world')
    expect(pieceAt(pieces, 5)).toBeNull()
  })
})

describe('intersectSentence', () => {
  it('句内选区转绝对坐标', () => {
    expect(intersectSentence(2, 5, 100, 20)).toEqual([102, 105])
  })
  it('越界/倒置 → null', () => {
    expect(intersectSentence(5, 2, 0, 10)).toBeNull()
    expect(intersectSentence(0, 30, 0, 10)).toBeNull()
  })
})

describe('vocabWordSet', () => {
  it('小写归一 + 词形共集', () => {
    const set = vocabWordSet([{ word: 'Dream' }, { word: 'invention' }])
    expect(set.has('dream')).toBe(true)
    expect(set.has('invention')).toBe(true)
  })
})

/* ---------------------------------------------------------------- 批注渲染分段
 * 2026-09-10 组长实测 bug2：批注只在句子上下划线（且 note 类连下划线都没有）、
 * 跳过去看不到内容。以下用例锁住「批注 → 可上色分段 + 角标」的渲染契约。 */
describe('buildSentenceSegments', () => {
  const TEXT = 'Alice was here.'
  const START = 100 // 句子在章内的绝对起点

  function ann(partial: Partial<AnnotationRange> & Pick<AnnotationRange, 'start_offset' | 'end_offset'>): AnnotationRange {
    return { id: 1, kind: 'highlight', color: '#fde68a', note: null, ...partial }
  }

  it('无批注：与词块一致，拼接等于原文', () => {
    const segs = buildSentenceSegments(TEXT, START, [])
    expect(segs.map((s) => s.text).join('')).toBe(TEXT)
    expect(segs.filter((s) => s.word).map((s) => s.word)).toEqual(['Alice', 'was', 'here'])
    expect(segs.every((s) => s.ann === null)).toBe(true)
  })

  it('整词批注：该词段带批注色，其余段无批注，拼接仍等于原文', () => {
    const segs = buildSentenceSegments(TEXT, START, [
      ann({ start_offset: START, end_offset: START + 5, color: '#bbf7d0' }),
    ])
    expect(segs.map((s) => s.text).join('')).toBe(TEXT)
    const alice = segs.find((s) => s.text === 'Alice')
    expect(alice?.ann?.color).toBe('#bbf7d0')
    expect(alice?.word).toBe('Alice') // 批注不破坏点词查义
    expect(segs.find((s) => s.text === 'was')?.ann).toBeNull()
  })

  it('跨词批注：按边界切段，词部分仍带 word（点任一部分可查整词）', () => {
    // [START+3, START+9) = "ce was"
    const segs = buildSentenceSegments(TEXT, START, [
      ann({ start_offset: START + 3, end_offset: START + 9 }),
    ])
    expect(segs.map((s) => s.text).join('')).toBe(TEXT)
    const annotated = segs.filter((s) => s.ann)
    expect(annotated.map((s) => s.text).join('')).toBe('ce was')
    expect(segs.find((s) => s.text === 'ce')?.word).toBe('Alice')
    expect(segs.find((s) => s.text === 'was')?.word).toBe('was')
    expect(segs.find((s) => s.text === ' ')?.word).toBeNull()
  })

  it('笔记批注：句内最后一段打角标（noteMarker）', () => {
    const segs = buildSentenceSegments(TEXT, START, [
      ann({ id: 7, kind: 'note', note: '这里用了过去时', start_offset: START + 6, end_offset: START + 14 }),
    ])
    const marked = segs.filter((s) => s.noteMarker)
    expect(marked).toHaveLength(1)
    expect(marked[0].ann?.id).toBe(7)
    // 角标落在该批注覆盖范围内的最后一段
    expect(segs[segs.length - 1].noteMarker).not.toBe(true)
  })

  it('跨句批注：本句只取交集部分', () => {
    const segs = buildSentenceSegments(TEXT, START, [
      ann({ start_offset: START - 20, end_offset: START + 5 }),
    ])
    expect(segs.filter((s) => s.ann).map((s) => s.text).join('')).toBe('Alice')
  })

  it('重叠批注：优先展示带笔记的那条', () => {
    const segs = buildSentenceSegments(TEXT, START, [
      ann({ id: 1, kind: 'highlight', start_offset: START, end_offset: START + 5 }),
      ann({ id: 2, kind: 'note', note: 'x', start_offset: START, end_offset: START + 5 }),
    ])
    expect(segs.find((s) => s.text === 'Alice')?.ann?.id).toBe(2)
  })
})

describe('sentenceHasAnnotation / annotationsOfSentence', () => {
  it('笔记批注也算「有批注」（修复前只认 highlight → 笔记批注在正文里完全不可见）', () => {
    const list: AnnotationRange[] = [
      { id: 1, kind: 'note', note: 'x', start_offset: 10, end_offset: 20 },
    ]
    expect(sentenceHasAnnotation(list, 5, 15)).toBe(true)
    expect(sentenceHasAnnotation(list, 25, 30)).toBe(false)
  })

  it('按句取批注并按起点排序', () => {
    const list: AnnotationRange[] = [
      { id: 2, kind: 'highlight', start_offset: 14, end_offset: 18 },
      { id: 1, kind: 'note', note: 'x', start_offset: 10, end_offset: 12 },
    ]
    expect(annotationsOfSentence(list, 9, 20).map((a) => a.id)).toEqual([1, 2])
  })
})
