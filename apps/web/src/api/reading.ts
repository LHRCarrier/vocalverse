/**
 * 读书域 API（docs/45 §4）：书架 / 书详情 / 章节 / 查词 / 生词本 / 批注 / 进度 / 听书。
 * - 常规请求走 request()（Envelope）；音频端点裸 audio/mpeg（loadAudioBlob 管道）；
 * - 整章预合成为 SSE 流（openSseFetch + FormData；事件类型见 ReadingStreamEvent）。
 */
import { openSseFetch } from '@/audio/sse'
import { loadAudioBlob, request } from '@/api/client'

export interface ReadingProgress {
  chapter_id: number
  char_offset: number
  content_version: number
  updated_at?: string | null
}

export interface ReadingBook {
  id: number
  title: string
  author: string
  description?: string | null
  level: string
  cover_color?: string | null
  cover_emoji?: string | null
  word_count: number
  chapter_count: number
  progress?: ReadingProgress | null
}

export interface ReadingChapterMeta {
  id: number
  chapter_no: number
  title: string
  word_count: number
  char_count: number
  current: boolean
}

export interface ReadingBookDetail extends ReadingBook {
  chapters: ReadingChapterMeta[]
}

export interface ReadingSentence {
  idx: number
  text: string
  para_idx: number
  start: number
  end: number
}

export interface ReadingChapter {
  id: number
  book_id: number
  chapter_no: number
  title: string
  content_version: number
  content: string
  paragraphs: string[]
  sentences: ReadingSentence[]
  word_count: number
  char_count: number
}

export interface WordLookupResult {
  word: string
  matched: string
  phonetic?: string | null
  translation?: string | null
  definition?: string | null
  pos?: string | null
  exchange?: Record<string, string> | null
  frequency?: number | null
  in_vocab: boolean
  vocab_id?: number | null
}

export interface VocabItem {
  id: number
  word: string
  status: 'new' | 'learning' | 'known'
  scene: string
  book_id?: number | null
  chapter_id?: number | null
  context_snippet?: string | null
  note?: string | null
  created_at?: string | null
  phonetic?: string | null
  translation?: string | null
  frequency?: number | null
}

export interface AnnotationItem {
  id: number
  kind: 'highlight' | 'note'
  start_offset: number
  end_offset: number
  content_version: number
  sentence_idx?: number | null
  text_snippet?: string | null
  note?: string | null
  color?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ReadingVoice {
  id: string
  label: string
  engine: 'edge' | 'kitten'
  langs: string[]
}

/** 听书任务 SSE 事件（docs/45 §4；与 practice turn SSE 独立协议） */
export type ReadingStreamEvent =
  | { type: 'task_start'; task_id: number; chapter_id: number; total: number; voice: string; provider: string }
  | { type: 'sentence_progress'; task_id: number; idx: number; status: 'done' | 'cached' | 'failed'; done: number; total: number }
  | { type: 'task_done'; task_id: number; status: 'done' | 'failed' | 'cancelled'; done: number; failed: number; total: number }
  | { type: 'error'; code: string; message: string; recoverable: boolean }

export interface TtsTaskSnapshot {
  id: number
  chapter_id: number
  voice: string
  provider: string
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  total: number
  done: number
  failed: number
  error?: Record<string, unknown> | null
  finished_at?: string | null
}

// ---------------------------------------------------------------- 书籍/章节

export async function fetchBooks(cursor?: number | null) {
  const q = cursor ? `?cursor=${cursor}` : ''
  const res = await request<{ items: ReadingBook[]; next_cursor: number | null; has_more: boolean }>(
    `/api/v1/reading/books${q}`,
  )
  return res.data
}

export async function fetchBookDetail(bookId: number): Promise<ReadingBookDetail> {
  const res = await request<ReadingBookDetail>(`/api/v1/reading/books/${bookId}`)
  return res.data
}

export async function fetchChapter(chapterId: number): Promise<ReadingChapter> {
  const res = await request<ReadingChapter>(`/api/v1/reading/chapters/${chapterId}`)
  return res.data
}

// ---------------------------------------------------------------- 查词/生词

export async function lookupWord(word: string): Promise<WordLookupResult> {
  const res = await request<WordLookupResult>('/api/v1/reading/lookup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ word }),
  })
  return res.data
}

export async function addVocab(
  word: string,
  ctx?: { book_id?: number; chapter_id?: number; context?: string },
): Promise<{ added: boolean; vocab: VocabItem }> {
  const res = await request<{ added: boolean; vocab: VocabItem }>('/api/v1/reading/vocab', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ word, ...(ctx ?? {}) }),
  })
  return res.data
}

export async function fetchVocab(status?: string, cursor?: string | null) {
  const q: string[] = []
  if (status) q.push(`status=${status}`)
  if (cursor) q.push(`cursor=${encodeURIComponent(cursor)}`)
  const res = await request<{ items: VocabItem[]; next_cursor: string | null; has_more: boolean }>(
    `/api/v1/reading/vocab${q.length ? `?${q.join('&')}` : ''}`,
  )
  return res.data
}

export async function patchVocab(id: number, patch: { status?: string; note?: string }): Promise<VocabItem> {
  const res = await request<VocabItem>(`/api/v1/reading/vocab/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return res.data
}

export async function deleteVocab(id: number): Promise<void> {
  await request(`/api/v1/reading/vocab/${id}`, { method: 'DELETE' })
}

/** 查词词卡「读词音」（缓存命中 0 扣；返回音频 blob） */
export function wordAudioUrl(word: string, voice = 'en-US-JennyNeural'): string {
  return `/api/v1/reading/tts/word/${encodeURIComponent(word)}?voice=${voice}`
}

// ---------------------------------------------------------------- 批注

export async function fetchAnnotations(chapterId: number): Promise<AnnotationItem[]> {
  const res = await request<{ items: AnnotationItem[] }>(
    `/api/v1/reading/annotations?chapter_id=${chapterId}`,
  )
  return res.data.items
}

export interface NewAnnotation {
  kind: 'highlight' | 'note'
  chapter_id: number
  start_offset: number
  end_offset: number
  text?: string
  note?: string
  color?: string
  sentence_idx?: number
}

export async function createAnnotation(input: NewAnnotation): Promise<AnnotationItem> {
  const res = await request<AnnotationItem>('/api/v1/reading/annotations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  return res.data
}

export async function patchAnnotation(
  id: number,
  patch: { note?: string; color?: string; kind?: 'highlight' | 'note' },
): Promise<AnnotationItem> {
  const res = await request<AnnotationItem>(`/api/v1/reading/annotations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return res.data
}

export async function deleteAnnotation(id: number): Promise<void> {
  await request(`/api/v1/reading/annotations/${id}`, { method: 'DELETE' })
}

// ---------------------------------------------------------------- 进度/音色

export async function fetchProgress(bookId: number): Promise<ReadingProgress | null> {
  const res = await request<ReadingProgress | null>(`/api/v1/reading/progress/${bookId}`)
  return res.data
}

export async function saveProgress(bookId: number, chapterId: number, charOffset: number): Promise<void> {
  await request(`/api/v1/reading/progress/${bookId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter_id: chapterId, char_offset: charOffset }),
  })
}

export async function fetchVoices(): Promise<ReadingVoice[]> {
  const res = await request<ReadingVoice[]>('/api/v1/reading/voices')
  return res.data
}

// ---------------------------------------------------------------- 听书

/** 单句音频路径（播放即取；命中缓存 0 扣） */
export function segmentAudioUrl(chapterId: number, sentenceIdx: number, voice: string): string {
  return `/api/v1/reading/chapters/${chapterId}/tts/segment/${sentenceIdx}?voice=${encodeURIComponent(voice)}`
}

export async function loadSegmentAudio(
  chapterId: number,
  sentenceIdx: number,
  voice: string,
): Promise<Blob> {
  return await loadAudioBlob(segmentAudioUrl(chapterId, sentenceIdx, voice))
}

/**
 * 整章预合成：SSE 流（FormData POST，复用 openSseFetch）。
 * 事件序列：task_start → sentence_progress* → task_done / error。
 */
export function prepareChapter(
  chapterId: number,
  voice: string,
  handlers: { onEvent: (e: ReadingStreamEvent) => void; onError?: (err: unknown) => void; onClose?: () => void },
  signal?: AbortSignal,
): void {
  const body = new FormData()
  body.append('voice', voice)
  body.append('rate', '+0%')
  openSseFetch(
    `/api/v1/reading/chapters/${chapterId}/tts/prepare`,
    { method: 'POST', body },
    {
      onEvent: (e) => handlers.onEvent(e as ReadingStreamEvent),
      onError: handlers.onError,
      onClose: handlers.onClose,
    },
    signal,
  )
}

export async function fetchTtsTask(taskId: number): Promise<TtsTaskSnapshot> {
  const res = await request<TtsTaskSnapshot>(`/api/v1/reading/tts/tasks/${taskId}`)
  return res.data
}

export async function cancelTtsTask(taskId: number): Promise<void> {
  await request(`/api/v1/reading/tts/tasks/${taskId}`, { method: 'DELETE' })
}
