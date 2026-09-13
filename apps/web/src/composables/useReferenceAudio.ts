/**
 * 参考旋律播放（跟唱面板「听参考旋律」）——从 `MobileSingView.vue` 抽出的自包含关注点
 * （2026-09-10：视图触发 eslint `max-lines 350` 门禁，且这块本就与页面无关）。
 *
 * 覆盖两条 2026-09-10 修复（拷问报告 A-F9 / G-#7 / A-F3）：
 * - **P1-7 资源回收**：`createObjectURL` 每次都是一整首歌的 blob（3 分钟曲 ≈3~5MB），
 *   原实现 onended/停止/卸载三处都只 `pause()` 不 revoke → 内存随试听次数线性增长
 *   （移动 WebView 易被系统杀）。现在统一在 `stop()` 里 revoke，且 `onended` 也走 `stop()`。
 * - **P1-7 重入守卫**：下载未完成时连点两次会叠出两路 `Audio`，第一路再也停不掉；
 *   现在 `busy` 期间第二次点击直接忽略（并给调用方一个明确的"进行中"信号）。
 *
 * 与页面的耦合降到两个入参：`path()` 取播放地址、`onError(msg)` 提示失败
 * （保持本模块与 UI/状态库无关，可独立单测）。
 */
import { onUnmounted, ref } from 'vue'
import type { Ref } from 'vue'

import { loadAudioBlob } from '@/api/client'

export interface ReferenceAudio {
  /** 是否正在播放（按钮文案/禁用态用） */
  playing: Ref<boolean>
  /** 播放/停止切换（同一按钮第二次点是停止） */
  toggle: () => Promise<void>
  /** 停止并回收资源（幂等；换歌/关面板/卸载都要调） */
  stop: () => void
}

export function useReferenceAudio(
  path: () => string | null,
  onError: (message: string) => void,
): ReferenceAudio {
  const playing = ref(false)
  let audio: HTMLAudioElement | null = null
  let objectUrl: string | null = null
  let busy = false

  function stop() {
    audio?.pause()
    audio = null
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl) // P1-7：唯一的回收点
      objectUrl = null
    }
    playing.value = false
  }

  async function toggle() {
    if (playing.value) {
      stop()
      return
    }
    const src = path()
    if (!src) {
      onError('该曲目暂无参考旋律音频')
      return
    }
    if (busy) return // P1-7：加载中重入直接忽略
    busy = true
    try {
      const blob = await loadAudioBlob(src)
      objectUrl = URL.createObjectURL(blob)
      audio = new Audio(objectUrl)
      audio.onended = () => stop()
      await audio.play()
      playing.value = true
    } catch {
      stop()
      onError('参考旋律播放失败，请重试')
    } finally {
      busy = false
    }
  }

  onUnmounted(stop) // 卸载兜底（原实现只清引用，URL 泄漏）

  return { playing, toggle, stop }
}
