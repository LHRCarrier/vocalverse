/**
 * 页面转场方向信号（2026-09-18 新增，docs/31 §2 规则 4）
 *
 * 三类动效里的「页面切换」需要知道是"进入下一层"还是"回退上一层"，
 * 才能给出方向一致的位移（前进向左进入、后退向右退出），避免"来回都往一个方向滑"的违和感。
 *
 * 判定顺序：
 *   1) history.state.position —— vue-router 4 为每条历史记录写入的递增序号；
 *      后退时新序号 < 旧序号 → back；
 *   2) 退化：路径层级（段数）比较（深链/替换导航等 position 不可用的场景）。
 *
 * 注意：不做整屏 push（底部 TabBar 挂在 router-view 之外，整屏位移会让底栏与内容脱节），
 * 只做 16px 微位移 + 淡入淡出，所以方向信号仅影响符号。
 */
import { ref } from 'vue'
import type { RouteLocationNormalized, Router } from 'vue-router'

export type PageDir = 'forward' | 'back'

const dir = ref<PageDir>('forward')
let prevPosition: number | null = null

function positionOf(): number | null {
  const state = window.history.state as { position?: number } | null
  return typeof state?.position === 'number' ? state.position : null
}

function depthOf(path: string): number {
  return path.split('/').filter(Boolean).length
}

/** 纯函数：给定前后路由与位置序号，算出方向（便于单测） */
export function resolvePageDir(
  from: RouteLocationNormalized,
  to: RouteLocationNormalized,
  prev: number | null,
  next: number | null,
): PageDir {
  if (prev != null && next != null && next !== prev) return next < prev ? 'back' : 'forward'
  return depthOf(to.path) >= depthOf(from.path) ? 'forward' : 'back'
}

/** 在 App.vue 调用一次：注册钩子并把方向写进响应式 ref */
export function usePageTransition(router: Router): { dir: typeof dir } {
  router.beforeEach(() => {
    const p = positionOf()
    if (p != null) prevPosition = p
  })

  router.afterEach((to, from) => {
    const next = positionOf()
    dir.value = resolvePageDir(from, to, prevPosition, next)
    if (next != null) prevPosition = next
  })

  return { dir }
}