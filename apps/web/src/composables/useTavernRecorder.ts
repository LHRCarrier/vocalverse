/**
 * 酒馆 · 语音输入（从 useTavernSession 拆出以守 fe-08 行数）：
 * 录音状态机 + 最短时长校验 + 音频回调；ASR/TTS 链路不变（录音 → multipart 回合）。
 */
import { ref, type Ref } from 'vue'

import { MIN_RECORD_MS, VoiceRecorder, micErrorMessage } from '@/audio/recorder'

export interface TavernRecorderDeps {
  sending: Ref<boolean>
  setError: (message: string | null) => void
  /** 收到有效录音（调用方组装 multipart 并发回合） */
  sendAudio: (blob: Blob) => void
}

export function useTavernRecorder(deps: TavernRecorderDeps) {
  const recording = ref(false)
  const recorder = new VoiceRecorder()

  recorder.onStateChange = (s) => {
    if (s !== 'recording') recording.value = false
  }
  recorder.onStop = (blob, _mime, durationMs) => {
    if (durationMs < MIN_RECORD_MS) {
      deps.setError(
        `录音太短（${(durationMs / 1000).toFixed(1)}s），请说满约 ${MIN_RECORD_MS / 1000} 秒后再点 ■ 停止`,
      )
      return
    }
    deps.sendAudio(blob)
  }

  function toggleMic() {
    if (deps.sending.value) return
    if (recording.value) {
      if (recorder.state === 'recording') recorder.stop()
      else recorder.cancel()
      return
    }
    deps.setError(null)
    recording.value = true
    void recorder.start(30_000).catch((e) => {
      recording.value = false
      deps.setError(micErrorMessage(e))
    })
  }

  return { recording, toggleMic }
}
