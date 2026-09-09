/**
 * 原生返回手势的弹层栈（2026-09-09 抽离，阅读器与社区详情页共用）
 *
 * 语义：安卓返回键/滑动返回时，**先关最上层弹层**，全部关闭后才交给原生回退历史；
 * 否则滑动返回会连带退页/退到桌面（见 worklog/BUG实测/手机端滑动返回直接退桌面.md）。
 * 顺序即「视觉层级由外到内」，与模板里的弹层挂载顺序保持一致。
 */
import { useNativeBack } from '@/composables/useNativeBack'

export interface BackLayer {
  /** 该层是否处于打开态 */
  open: () => boolean
  /** 关闭该层 */
  close: () => void
}

export function useBackLayers(layers: BackLayer[]): void {
  useNativeBack(() => {
    for (const layer of layers) {
      if (layer.open()) {
        layer.close()
        return true
      }
    }
    return false
  })
}
