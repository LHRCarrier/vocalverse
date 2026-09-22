/**
 * 跟唱伴奏（2026-09-22 用户口径「原唱是听的，伴奏是唱的时候放的」）——从 `MobileSingView`
 * 抽出（视图守 eslint `max-lines 350` 门禁；与 `useReferenceAudio` 的抽取同因）。
 *
 * 与「原唱（参考音）」的分工：
 * - **原唱**（`songs.audio_url`）= 试听/学习，走 `useReferenceAudio` 的 `toggle`；
 * - **伴奏**（`songs.instrumental_url`，Demucs 分离的 no_vocals）= 录音期间播放，
 *   本组合式负责；无伴奏轨的老曲**回退 audio_url**（示例曲的 audio_url 本就是纯旋律）。
 *
 * 播放器复用 `useReferenceAudio`（同一套 blob 加载/回收/重入守卫），只是换素材名与
 * 起播语义（`play()` = 从头播）。**注意**：伴奏经外放会被麦克风一起录进去 → 建议戴耳机，
 * 否则评分受外放影响（这是「录音期间要有伴奏」的必然代价，用户已明确要伴奏）。
 */
import { ref } from 'vue'
import type { Ref } from 'vue'

import { useReferenceAudio } from './useReferenceAudio'

export interface SingAccompaniment {
  /** 开关（默认开；关掉即清唱） */
  on: Ref<boolean>
  /** 是否正在播放（歌词时钟「跟随音频」判据之一） */
  playing: Ref<boolean>
  /** 开关切换（面板「伴奏」键） */
  toggle: () => void
  /** 录音开始：开关开着 → 从头起播并等就位（返回是否真的开播；视图据此对齐两轴） */
  start: () => Promise<boolean>
  /** 暂停/继续（与录音同步，否则音乐在走、录音停了） */
  pause: () => void
  resume: () => void
  /** 停止并回收（换歌/关面板/完成/重录都要调） */
  stop: () => void
  /** 当前位置（ms；未播放 → 0） */
  currentMs: () => number
}

export function useSingAccompaniment(
  urls: () => { instrumental?: string | null; audio?: string | null },
  onError: (message: string) => void,
): SingAccompaniment {
  const on = ref(true)
  /** 伴奏轨路径：优先 instrumental_url，缺省回退 audio_url（basename 走 /api/v1/audio/{name}） */
  const path = () => {
    const { instrumental, audio } = urls()
    const url = instrumental ?? audio
    return url ? `/api/v1/audio/${url.split('/').pop()}` : null
  }
  const player = useReferenceAudio(path, onError, '伴奏')

  return {
    on,
    playing: player.playing,
    toggle: () => {
      on.value = !on.value
    },
    start: async () => {
      if (!on.value) return false
      await player.play()
      return player.playing.value
    },
    pause: player.pause,
    resume: player.resume,
    stop: player.stop,
    currentMs: player.currentMs,
  }
}
