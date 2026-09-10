/**
 * 听书 · 章节播放器 composable（docs/45 §6）：单元素顺序播放 + 句级高亮 + 预取。
 *
 * - 播放主线「播放即取」：loadSegmentAudio(idx) → objectURL → audio 顺序播放；
 * - 倍速 = playbackRate（免多档重合成，docs/45 §5 拍板）；
 * - 预取 N=3（useBlobAudio 有界 LRU ≤12 防泄漏，UI 拷问 U-18）；
 * - 结束自动进下一句；失败跳句；长按划选互斥由视图调用 pause()。
 */
import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
import { loadSegmentAudio } from '@/api/reading'
import { useBlobAudio } from '@/composables/useBlobAudio'
import { RATES } from '@/audio/tts-player'
import type { ReadingSentence } from '@/api/reading'

export function useChapterTts(chapterId: number, getSentences: () => ReadonlyArray<ReadingSentence>) {
  const state = ref<'idle' | 'loading' | 'playing' | 'paused' | 'ended'>('idle')
  const currentIdx = ref(-1)
  const rate = ref<number>(1)
  const errorText = ref('')
  /** 单句听读模式（「听这句」）：本句播完即止，不自动连播下一句（2026-09-10 组长实测反馈） */
  const singleShot = ref(false)
  /** 上一次是否为单句：重播（▶）沿用同一模式（2026-09-10 组长要求「重播也是单句」） */
  const lastSingle = ref(false)
  const { createUrl, revokeUrl, releaseAll } = useBlobAudio()
  const audio = shallowRef<HTMLAudioElement | null>(null)

  const sentences = computed(() => getSentences())
  const currentSentence = computed(() =>
    currentIdx.value >= 0 ? (sentences.value[currentIdx.value] ?? null) : null,
  )
  const progress = computed(() => {
    if (sentences.value.length === 0) return 0
    return (currentIdx.value + 1) / sentences.value.length
  })

  function ensureAudio(): HTMLAudioElement {
    if (!audio.value) {
      const el = new Audio()
      el.preload = 'auto'
      el.addEventListener('ended', () => {
        void next(true)
      })
      el.addEventListener('error', () => {
        errorText.value = '音频播放失败，检查网络后重试'
        state.value = 'idle'
      })
      audio.value = el
    }
    return audio.value
  }

  async function playFrom(idx: number, single = false): Promise<void> {
    if (idx < 0 || idx >= sentences.value.length) return
    singleShot.value = single
    lastSingle.value = single
    currentIdx.value = idx
    state.value = 'loading'
    errorText.value = ''
    try {
      const blob = await loadSegmentAudio(chapterId, idx, voice.value)
      const url = createUrl(blob)
      const el = ensureAudio()
      revokeUrl(el.src as string)
      el.src = url
      el.playbackRate = rate.value
      await el.play()
      state.value = 'playing'
      prefetch(idx)
    } catch (err) {
      errorText.value = `本句加载失败（${(err as Error).message ?? ''}）`
      state.value = 'idle'
      if (!singleShot.value && idx < sentences.value.length - 1) await playFrom(idx + 1)
    }
  }

  /** 单句听读入口：playFrom(idx, true)，播完即止 */
  async function playOne(idx: number): Promise<void> {
    await playFrom(idx, true)
  }

  async function next(auto = false): Promise<void> {
    // 单句模式：本句播完即止，不自动连播下一句（结束态交给用户重听/续播）
    if (auto && singleShot.value) {
      singleShot.value = false
      state.value = 'ended'
      return
    }
    singleShot.value = false
    if (currentIdx.value < sentences.value.length - 1) {
      await playFrom(currentIdx.value + 1)
    } else if (auto) {
      state.value = 'ended'
    }
  }

  async function prev(): Promise<void> {
    if (currentIdx.value > 0) await playFrom(currentIdx.value - 1)
  }

  async function toggle(): Promise<void> {
    const el = ensureAudio()
    if (state.value === 'playing') {
      el.pause()
      state.value = 'paused'
    } else if (state.value === 'idle' || state.value === 'paused' || state.value === 'ended') {
      // 重播沿用上一次模式：单句则仍是单句（组长要求），章节则整章；currentIdx<0（新开）走整章
      if (currentIdx.value < 0) await playFrom(0)
      else await playFrom(currentIdx.value, lastSingle.value)
    }
  }

  function pause(): void {
    audio.value?.pause()
    if (state.value === 'playing') state.value = 'paused'
  }

  function changeRate(): void {
    const i = RATES.findIndex((r) => Math.abs(r - rate.value) < 1e-6)
    rate.value = RATES[(i + 1) % RATES.length]
    if (audio.value) audio.value.playbackRate = rate.value
  }

  function prefetch(idx: number): void {
    for (let i = 1; i <= 3 && idx + i < sentences.value.length; i++) {
      void loadSegmentAudio(chapterId, idx + i, voice.value).then((blob) => {
        // LRU 由 useBlobAudio 管理；预取只为缓存命中，不占播放槽
        revokeUrl(createUrl(blob))
      })
    }
  }

  function stop(): void {
    audio.value?.pause()
    audio.value?.removeAttribute('src')
    state.value = 'idle'
    currentIdx.value = -1
  }

  onBeforeUnmount(() => {
    stop()
    releaseAll()
  })

  // 音色在视图层绑定（Mounted 后加载 voices，默认 Jenny）
  const voice = ref('en-US-JennyNeural')
  function setVoice(v: string) {
    voice.value = v
  }

  return {
    state,
    currentIdx,
    currentSentence,
    progress,
    rate,
    errorText,
    voice,
    setVoice,
    playFrom,
    playOne,
    next,
    prev,
    toggle,
    pause,
    changeRate,
    stop,
  }
}
