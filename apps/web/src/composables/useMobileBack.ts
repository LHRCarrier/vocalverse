/**
 * 移动端「返回」语义（2026-09-10 修复读书域返回死循环，见 worklog/BUG实测/读书域返回键来回跳.md）。
 *
 * 顶栏「离开」钮 = 回上一页；无上一页（冷启/深链直达）时回退到 fallback 页。
 *
 * ⚠️ 必须用 router.back() 而不是 router.push('固定目标')：
 * push 会**新增**历史条目，若目标页自己的返回又是 back()，两页就会把对方反复压回历史栈
 * —— 书详情 ⇄ 阅读器 来回跳、退不出去（组长手机实测 bug 1）。
 * 反向同理：本组件只做「回退」，永不 push，历史栈深度单调不增。
 */
import { useRouter } from 'vue-router'

/** 是否有可回退的上一条历史（vue-router 4 把上一条路径写进 history.state.back） */
export function hasPreviousEntry(): boolean {
  const state = window.history.state as { back?: unknown } | null
  return state?.back != null
}

export function useMobileBack(fallback: string) {
  const router = useRouter()
  return function goBack(): void {
    if (hasPreviousEntry()) router.back()
    else void router.replace(fallback)
  }
}
