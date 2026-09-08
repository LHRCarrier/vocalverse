/**
 * 阅读器 · 词切分/批注坐标纯函数（docs/45 §3：章节内 char offset · 服务端权威坐标系）。
 */
import { describe, expect, it } from 'vitest'

import { intersectSentence, pieceAt, splitPieceWords, vocabWordSet } from '../reader-words'

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
