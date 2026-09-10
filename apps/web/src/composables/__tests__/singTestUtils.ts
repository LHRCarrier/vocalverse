/**
 * `useSingPlay` 测试共享脚手架（**非测试文件**：不以 .test.ts 结尾，vitest 不收集）。
 *
 * 抽出的背景（2026-09-10）：组合式用例已按关注点拆成
 * `sing.test.ts`（状态机）/ `sing-polling.test.ts`（录音 + 轮询世代号）/ `sing-favorites.test.ts`（收藏），
 * 三个文件都需要同一套「录音器伪实现 + API 模块替换」；复制三份必然漂移，
 * 且各文件都逼近 eslint `max-lines 350` 门禁。
 *
 * 关键约定（勿改，见文件内注释）：
 * - 录音器伪实现按**真实契约**实现（`start` 同态守卫 / `stop` 先发 stopped 再 onStop /
 *   `cancel` 只发 idle 不触发 onStop）——2026-09-10 两次 BUG 都出在这些语义上；
 * - `installMock` 内部 `vi.resetModules()` 后重装两个 mock，故映射函数用 `importActual`
 *   拿真实实现（纯函数），网络函数被替换。
 */
import { vi } from 'vitest'

import type { SingAttemptResult, SongDetail } from '@/api/sing'

export const detail = (status: string): SongDetail => ({
  id: 1,
  title: 'Twinkle',
  level: 1,
  pitch_ref_status: status as SongDetail['pitch_ref_status'],
  expected_lines: 2,
  favorited: false,
  lines: [],
})

export const fullResult: SingAttemptResult = {
  id: 9,
  song_id: 1,
  duration_s: 10,
  overall: 91.1,
  pitch: 95,
  rhythm: 95,
  pron: 82,
  is_complete: true,
  expected_lines: 2,
  scoring_version: 'v5',
  ref_version: 'pyin-v2',
  lines: [],
  alignment: { offset_ms: 0, method: 'dtw-local-sakoe-chiba-v3' },
}

export interface ApiMock {
  fetchSongDetail?: ReturnType<typeof vi.fn>
  fetchSongs?: ReturnType<typeof vi.fn>
  createSingSession?: ReturnType<typeof vi.fn>
  uploadSingAudio?: ReturnType<typeof vi.fn>
  fetchSingStatus?: ReturnType<typeof vi.fn>
  fetchSingResult?: ReturnType<typeof vi.fn>
  setSongFavorite?: ReturnType<typeof vi.fn>
}

/** 录音器伪实现实例句柄（测试里驱动状态/断言 recorder 状态用）。
 *
 * 注意：这里**不能**用 `vi.hoisted`（跨模块导出会报 "Cannot export hoisted variable"）；
 * 也不需要——`installRecorderMock()` 是在测试运行时调用 `vi.doMock`，工厂闭包捕获本对象即可。
 */
export const rec: {
  instance: null | {
    state: string
    onStateChange?: (s: string) => void
    onStop?: (b: Blob) => void
  }
} = { instance: null }

export function installRecorderMock() {
  vi.doMock('@/audio/recorder', () => ({
    MIN_RECORD_MS: 800,
    micErrorMessage: (e: unknown) => String(e),
    VoiceRecorder: class {
      state = 'idle'
      liveStream: MediaStream | null = null
      onStateChange?: (s: string) => void
      onStop?: (b: Blob) => void
      constructor() {
        rec.instance = this as never
      }
      async start() {
        if (this.state === 'recording') return // 与真实实现同款守卫：同态重复 start 静默早退
        this.state = 'recording'
        this.liveStream = {} as MediaStream
        this.onStateChange?.('recording')
      }
      /** 正常停止：stopped → onStop（真实实现同序） */
      stop() {
        if (this.state !== 'recording') return
        this.state = 'stopped'
        this.liveStream = null
        this.onStateChange?.('stopped')
        this.onStop?.(new Blob(['x']))
      }
      /** 放弃：cancelled=true → onstop → setState('idle')，且**不**触发 onStop */
      cancel() {
        this.state = 'idle'
        this.liveStream = null
        this.onStateChange?.('idle')
      }
    },
  }))
}

export async function installMock(overrides: ApiMock = {}) {
  vi.resetModules()
  installRecorderMock() // 录音器伪实现（每次 resetModules 后需重装）
  const { ApiError: ClientApiError } = await import('@/api/client')
  // 「真实实现」图（importActual）与上面 import 的图不是同一个模块实例表：
  // 被测映射函数内部做 instanceof ApiError，故测试要用同一图里的 ApiError 造错（否则回落通用文案）
  const { ApiError: ActualApiError } = await vi.importActual<typeof import('@/api/client')>(
    '@/api/client',
  )
  const actual = await vi.importActual<typeof import('@/api/sing')>('@/api/sing')
  vi.doMock('@/api/sing', () => ({
    // 纯映射函数（favoriteErrorMessage/singErrorMessage/singFailureMessage）走真实实现
    ...actual,
    fetchSongDetail: overrides.fetchSongDetail ?? vi.fn(async () => detail('ready')),
    fetchSongs:
      overrides.fetchSongs ??
      vi.fn(async () => [
        { id: 1, title: 'T', level: 1, pitch_ref_status: 'ready', expected_lines: 2, favorited: false },
      ]),
    createSingSession:
      overrides.createSingSession ??
      vi.fn(async () => ({ id: 5, kind: 'sing', song_id: 1, assigned_turns: 2 })),
    uploadSingAudio:
      overrides.uploadSingAudio ??
      vi.fn(async () => ({
        attempt_id: 9,
        status: 'queued',
        progress: { done_lines: 0, total: 2 },
      })),
    fetchSingStatus:
      overrides.fetchSingStatus ??
      vi.fn(async () => ({
        attempt_id: 9,
        status: 'done',
        progress: { done_lines: 2, total: 2 },
      })),
    fetchSingResult: overrides.fetchSingResult ?? vi.fn(async () => fullResult),
    setSongFavorite:
      overrides.setSongFavorite ??
      vi.fn(async (songId: number, favorited: boolean) => ({ song_id: songId, favorited })),
    ApiError: ClientApiError,
  }))
  const { useSingPlay } = await import('@/composables/sing')
  return { useSingPlay, ApiError: ActualApiError }
}
