/**
 * 酒馆 · 流式跟随滚动（docs/57 §3.2「阅读区优先」）：
 *
 * - `text_delta` 内容增长时**节流**跟随（默认 120ms），且只在用户仍贴底时滚；
 * - 用户上滑离底 → 暂停跟随（不抢滚动条）；再次滚回底部附近 → 自动恢复；
 * - 新用户动作（发送/点 chip）→ `reengage()` 重新吸附；
 * - `turn_end` → `onTurnEnd()` 保证一次滚底（无论此前是否暂停）。
 *
 * 本文件同时是「滚动跟随」这一域的唯一 composable（docs/56 §6）：上面是纯函数 + 注入式视口
 * （window 或任意 scrollport，便于单测），下面是 Vue 接线（`useTavernScrollFollow`）。
 */
import { computed, nextTick, onMounted, onUnmounted, watch, type Ref } from 'vue'

/** 视为「贴底」的阈值（px）：小于此距离时跟随滚动 */
export const NEAR_BOTTOM_PX = 96

export interface ScrollViewport {
  scrollTop: number
  scrollHeight: number
  innerHeight: number
}

/** 距底部距离（负值/越界钳为 0） */
export function distanceFromBottom(vp: ScrollViewport): number {
  return Math.max(0, vp.scrollHeight - vp.scrollTop - vp.innerHeight)
}

/** 是否在底部附近（可跟随） */
export function isNearBottom(vp: ScrollViewport, threshold = NEAR_BOTTOM_PX): boolean {
  return distanceFromBottom(vp) <= threshold
}

export interface StreamFollowOptions {
  /** 读取当前滚动几何 */
  getViewport: () => ScrollViewport
  /** 滚到底部；smooth=false 用于流式/回合结束（即时不闪） */
  scrollToBottom: (smooth: boolean) => void
  /** 节流窗口（ms） */
  throttleMs?: number
  threshold?: number
  /** 可注入时钟（测试用） */
  now?: () => number
}

export interface StreamFollow {
  /** 当前是否吸附（贴底） */
  readonly engaged: boolean
  /** 用户动作：重新吸附 */
  reengage(): void
  /** 内容增长（流式）：节流 + 仅吸附时滚动；返回是否真的滚了 */
  onContentGrow(at?: number): boolean
  /** 用户手动滚动后同步吸附状态；返回是否仍吸附 */
  onUserScroll(): boolean
  /** 回合结束：一律滚一次（保证末行可见） */
  onTurnEnd(): void
  /** 距底部距离（px） */
  distance(): number
}

export function createStreamFollow(options: StreamFollowOptions): StreamFollow {
  const throttleMs = options.throttleMs ?? 120
  const threshold = options.threshold ?? NEAR_BOTTOM_PX
  const now = options.now ?? (() => Date.now())
  let lastAt = Number.NEGATIVE_INFINITY
  let engaged = isNearBottom(options.getViewport(), threshold)

  return {
    get engaged() {
      return engaged
    },
    reengage() {
      engaged = true
    },
    onContentGrow(at = now()) {
      if (!engaged) return false
      if (at - lastAt < throttleMs) return false
      lastAt = at
      options.scrollToBottom(false)
      return true
    },
    onUserScroll() {
      engaged = isNearBottom(options.getViewport(), threshold)
      return engaged
    },
    onTurnEnd() {
      engaged = true
      options.scrollToBottom(false)
    },
    distance() {
      return distanceFromBottom(options.getViewport())
    },
  }
}

/* ============================================================
 * Vue 接线（页面用）：window 滚动 + rows 指纹/turn_end/ending 触发
 * ============================================================ */

export interface ScrollFollowInput {
  rows: Ref<ReadonlyArray<{ content: string; live?: boolean }>>
  /** 每次 turn_end +1（会话侧递增） */
  turnEndAt: Ref<number>
  /** 实时尾声信号（出现时定位到卡） */
  ending: Ref<unknown>
}

export function useTavernScrollFollow(input: ScrollFollowInput) {
  function scrollToLatest(smooth = true) {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: smooth ? 'smooth' : 'auto' })
  }

  const follow = createStreamFollow({
    getViewport: () => ({
      scrollTop: window.scrollY,
      scrollHeight: document.documentElement.scrollHeight,
      innerHeight: window.innerHeight,
    }),
    scrollToBottom: () => scrollToLatest(false),
  })

  /** 流式内容指纹（text_delta 会让末行 content 增长） */
  const fingerprint = computed(() => {
    const last = input.rows.value[input.rows.value.length - 1]
    return `${input.rows.value.length}:${last?.content.length ?? 0}:${last?.live ? 1 : 0}`
  })
  watch(fingerprint, () => { void nextTick(() => follow.onContentGrow()) })
  watch(() => input.rows.value.length, () => {
    follow.reengage()
    void nextTick(() => follow.onTurnEnd())
  })
  watch(() => input.turnEndAt.value, () => { void nextTick(() => follow.onTurnEnd()) })
  watch(input.ending, (value) => {
    if (value) void nextTick(() => follow.onTurnEnd())
  })

  function onUserScroll() { follow.onUserScroll() }

  onMounted(() => window.addEventListener('scroll', onUserScroll, { passive: true }))
  onUnmounted(() => window.removeEventListener('scroll', onUserScroll))

  return {
    onUserScroll,
    /** 用户动作（发送/点 chip）→ 重新吸附 */
    reengage: () => follow.reengage(),
    /** 保证一次滚底（结算/回合末） */
    pinToBottom: () => follow.onTurnEnd(),
  }
}
