/**
 * 回合计时器统一管理（docs/14 §3.7 / docs/16 A4）：
 * 8s 无录音救场 / 15s 自动停止 / 30s 跳出记时；卸载统一清理（防泄漏）。
 */
import { onUnmounted } from 'vue'

export function useTurnTimers() {
  const timers: Array<ReturnType<typeof setTimeout>> = []

  function setTimer(fn: () => void, ms: number): void {
    timers.push(setTimeout(fn, ms))
  }

  function clearAll(): void {
    timers.splice(0).forEach((t) => clearTimeout(t))
  }

  onUnmounted(clearAll)

  return { setTimer, clearAll }
}
