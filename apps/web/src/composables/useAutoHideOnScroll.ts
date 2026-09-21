/**
 * 页首吸顶区「下滚收起 / 上滚出现」（社交 App 惯例；2026-09-21 组长反馈：
 * 酒馆改语言、社区切领域要滑回顶部 → 顶栏常驻 + 方向感知收起）。
 *
 * 用法：把宿主元素（`.u-head` 吸顶区，或单独使用的顶栏自身）挂 ref 后调用。
 * 本 composable 只负责在滚动方向变化时给宿主加/去 `is-hidden` 类，位移与过渡由 CSS 负责
 * （见 mobile-uic.css「页首吸顶区」段）。
 *
 * 规则：
 * - 距顶 TOP_ZONE 内恒显示（回到顶部一定看得到顶栏）；
 * - 下滚累计超过 DELTA 才收起、上滚累计超过 DELTA 才出现（滚动抖动不闪烁）；
 * - 焦点在宿主内的输入框时（软键盘弹出会带动滚动）不收起——正在输入就不该把输入条藏掉。
 */
import { onMounted, onUnmounted } from 'vue'

/** 距顶恒显示区（≈ 顶栏高度） */
const TOP_ZONE = 56
/** 方向判定阈值（累计位移，px） */
const DELTA = 6

export function useAutoHideOnScroll(getHost: () => HTMLElement | null | undefined): void {
  let host: HTMLElement | null = null
  let lastY = 0

  function show(): void {
    host?.classList.remove('is-hidden')
  }

  function onScroll(): void {
    if (!host) return
    const y = Math.max(0, window.scrollY)
    if (y <= TOP_ZONE || host.contains(document.activeElement)) {
      lastY = y
      show()
      return
    }
    const dy = y - lastY
    if (dy > DELTA) {
      lastY = y
      host.classList.add('is-hidden')
    } else if (dy < -DELTA) {
      lastY = y
      show()
    }
  }

  onMounted(() => {
    host = getHost() ?? null
    lastY = Math.max(0, window.scrollY)
    window.addEventListener('scroll', onScroll, { passive: true })
  })

  onUnmounted(() => {
    window.removeEventListener('scroll', onScroll)
    show()
  })
}
