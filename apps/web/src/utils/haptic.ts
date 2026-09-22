/**
 * 触觉反馈（2026-09-18 新增，docs/31 §2 规则 3「即时反馈」）
 *
 * 用零依赖的 Vibration API：Android WebView 支持；iOS 与桌面静默降级为无操作。
 * 只在**语义动作**上调用（点赞 / 支持 / 收藏 / 发送），不做全局"按哪都震"——
 * 全量振动既费电又廉价，还会在滚动误触时给出错误信号。
 *
 * 权限：Android 壳需在 `apps/mobile/android/app/src/main/AndroidManifest.xml`
 * 声明 `android.permission.VIBRATE`，否则 WebView 内调用会静默失败。
 */
export type HapticStrength = 'light' | 'medium'

const DURATION: Record<HapticStrength, number> = { light: 10, medium: 20 }

/** 当前环境是否支持振动（测试环境 / 桌面 / iOS 返回 false） */
export function hapticSupported(): boolean {
  return typeof navigator !== 'undefined' && typeof navigator.vibrate === 'function'
}

/** 触发一次轻/中振动；不支持或抛错时静默（振动不在关键路径，绝不打断交互） */
export function hapticTap(strength: HapticStrength = 'light'): void {
  if (!hapticSupported()) return
  try {
    navigator.vibrate(DURATION[strength])
  } catch {
    /* 静默降级 */
  }
}