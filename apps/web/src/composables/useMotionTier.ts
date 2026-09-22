/**
 * 动效分级（docs/31 §2 规则 4：低端机保基础体验；高端机呈现完整细节）
 *
 * 三级语义：
 *   high —— 完整动效（默认）
 *   low  —— 缩短过渡时长 + 去位移（省电模式 / 低内存低核数机型）
 *   off  —— 只保留颜色变化（系统"减少动效"开启，或用户手动覆盖）
 *
 * 落地方式：把档位写到 `document.documentElement.dataset.motion`，
 * 样式侧统一用 `html[data-motion='low'|'off']` 选择器降级（不在 JS 里散落分支）。
 *
 * 优先级：URL `?motion=` > localStorage `vv_motion_tier` > prefers-reduced-motion > 设备能力探测。
 */
import { readonly, ref } from 'vue'

export type MotionTier = 'high' | 'low' | 'off'

const tier = ref<MotionTier>('high')
let bound = false

function isTier(v: unknown): v is MotionTier {
  return v === 'high' || v === 'low' || v === 'off'
}

/** 探测当前应使用的档位（纯函数，便于测试） */
export function detectMotionTier(win: Window = window, storage: Storage | null = localStorage): MotionTier {
  const nav = win.navigator as Navigator & {
    deviceMemory?: number
    connection?: { saveData?: boolean }
  }
  const forced =
    new URLSearchParams(win.location.search).get('motion') ??
    (storage ? storage.getItem('vv_motion_tier') : null)
  if (isTier(forced)) return forced

  // 系统"减少动效"：直接关闭
  if (typeof win.matchMedia === 'function' && win.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return 'off'
  }

  // 设备能力：省数据 / 低内存 / 低核数 → 降一档（iOS 无 deviceMemory，不做误降）
  const cores = nav.hardwareConcurrency ?? 8
  if (nav.connection?.saveData === true) return 'low'
  if (nav.deviceMemory != null && nav.deviceMemory <= 4) return 'low'
  if (cores <= 4) return 'low'
  return 'high'
}

function apply(next: MotionTier): void {
  tier.value = next
  document.documentElement.dataset.motion = next
}

/**
 * 全局调用一次（App.vue setup）：写入档位并跟随系统"减少动效"开关变化。
 * 重复调用是幂等的（只绑定一次监听）。
 */
export function useMotionTier(): { tier: Readonly<typeof tier> } {
  if (!bound) {
    bound = true
    apply(detectMotionTier())
    if (typeof window.matchMedia === 'function') {
      window.matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', () => {
        apply(detectMotionTier())
      })
    }
  }
  return { tier: readonly(tier) }
}