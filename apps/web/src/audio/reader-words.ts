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
