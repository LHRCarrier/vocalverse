/**
 * 唱吧全链路（M3 唱歌 P0）：
 * loadSongs（选歌）→ openSong（详情 + 40905 门禁）→ startRecording（≤180s）→
 * createSingSession → uploadSingAudio → 轮询 status（退避 + onUnmounted 中止）→
 * 结果（逐句 + D3 图数据）。
 *
 * 本轮询为组件无关组合式：MobileSingView（真形态）与 SingingPreview（联调页）共用同一逻辑，
 * UI 侧只订阅 phase/result 状态。中止纪律：组件卸载必须调 stop()（防泄漏定时器）。
 */
import { computed, onUnmounted, ref } from 'vue'
import type { Ref } from 'vue'

import { VoiceRecorder, micErrorMessage } from '@/audio/recorder'
import {
  createSingSession,
  fetchSingResult,
  fetchSingStatus,
  fetchSongDetail,
  fetchSongs,
  singErrorMessage,
  uploadSingAudio,
} from '@/api/sing'
import type {
  SingAttemptResult,
  SingAttemptStatus,
  SongDetail,
  SongSummary,
} from '@/api/sing'

export type SingPhase =
  | 'pick'
  | 'loading'
  | 'idle'
  | 'recording'
  | 'uploading'
  | 'processing'
  | 'done'
  | 'failed'

export interface SingPlay {
  songs: Ref<SongSummary[]>
  detail: Ref<SongDetail | null>
  phase: Ref<SingPhase>
  error: Ref<string | null>
  status: Ref<SingAttemptStatus | null>
  result: Ref<SingAttemptResult | null>
  progressPct: import('vue').ComputedRef<number>
  loadSongs: () => Promise<void>
  openSong: (songId: number) => Promise<boolean>
  /** 提交整首音频（自动建会话 + 上传 + 轮询；recorder onStop 与外部上传共用） */
  submitAudio: (blob: Blob) => Promise<void>
  startRecording: () => void
  stopRecording: () => void
  cancelRecording: () => void
  retry: () => void
  reset: () => void
  stop: () => void
}

export function useSingPlay(): SingPlay {
  const songs = ref<SongSummary[]>([])
  const detail = ref<SongDetail | null>(null)
  const phase = ref<SingPhase>('pick')
  const error = ref<string | null>(null)
  const status = ref<SingAttemptStatus | null>(null)
  const result = ref<SingAttemptResult | null>(null)

  const recorder = new VoiceRecorder()
  recorder.onStateChange = (s) => {
    if (s === 'error') phase.value = 'failed'
    if (s === 'recording') phase.value = 'recording'
  }
  recorder.onStop = (blob) => {
    void submitAudio(blob)
  }

  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let sessionId = 0
  let attemptId = 0

  const progressPct = computed(() => {
    const p = status.value?.progress
    if (!p || !p.total) return 0
    return Math.round((p.done_lines / p.total) * 100)
  })

  function stop() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
  }

  async function loadSongs() {
    phase.value = 'loading'
    error.value = null
    try {
      songs.value = await fetchSongs()
      phase.value = 'idle'
    } catch (e) {
      phase.value = 'failed'
      error.value = singErrorMessage(e)
    }
  }

  /** 选歌：详情 + 就绪门禁（40905 语义前置提示，不进入跟唱） */
  async function openSong(songId: number): Promise<boolean> {
    error.value = null
    try {
      detail.value = await fetchSongDetail(songId)
    } catch (e) {
      error.value = singErrorMessage(e)
      return false
    }
    if (detail.value.pitch_ref_status !== 'ready') {
      error.value = '参考旋律生成中或缺失（暂时不能跟唱）：等提取完成后刷新即可'
      return false
    }
    phase.value = 'idle'
    return true
  }

  function startRecording() {
    error.value = null
    void recorder.start(180_000).catch((e) => {
      phase.value = 'failed'
      error.value = micErrorMessage(e)
    })
  }

  function stopRecording() {
    recorder.stop()
  }

  function cancelRecording() {
    recorder.cancel()
  }

  async function submitAudio(blob: Blob) {
    if (!detail.value) return
    phase.value = 'uploading'
    try {
      const sess = await createSingSession(detail.value.id)
      sessionId = sess.id
      const submitted = await uploadSingAudio(sessionId, blob)
      attemptId = submitted.attempt_id
      status.value = submitted
      phase.value = 'processing'
      poll()
    } catch (e) {
      phase.value = 'failed'
      error.value = singErrorMessage(e)
    }
  }

  function poll() {
    stop()
    pollTimer = setTimeout(async () => {
      try {
        const s = await fetchSingStatus(attemptId)
        status.value = s
        if (s.status === 'done') {
          result.value = await fetchSingResult(attemptId)
          phase.value = 'done'
          return
        }
        if (s.status === 'failed') {
          phase.value = 'failed'
          error.value = s.error || '评分失败，请重试'
          return
        }
        poll()
      } catch (e) {
        phase.value = 'failed'
        error.value = singErrorMessage(e)
      }
    }, 1500)
  }

  function reset() {
    stop()
    detail.value = null
    status.value = null
    result.value = null
    error.value = null
    phase.value = 'idle'
  }

  function retry() {
    stop()
    error.value = null
    phase.value = 'idle'
  }

  onUnmounted(() => {
    stop()
    recorder.cancel()
  })

  return {
    songs,
    detail,
    phase,
    error,
    status,
    result,
    progressPct,
    loadSongs,
    openSong,
    submitAudio,
    startRecording,
    stopRecording,
    cancelRecording,
    retry,
    reset,
    stop,
  }
}

/** 60s 内无任务进展的友好提示文案（轮询超时场景，前端兜底） */
export const SING_POLL_HINT = '评分计算中...（约 10~30 秒，长歌约 1 分钟）'
