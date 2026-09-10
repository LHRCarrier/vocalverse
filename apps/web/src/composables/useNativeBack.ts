/**
 * Android 返回手势/返回键的「页面优先」接管点
 * （2026-09-10 修复手机端滑动返回直接退到桌面，见 worklog/BUG实测/手机端滑动返回直接退桌面.md）。
 *
 * 链路：手机壳 `apps/mobile/android/.../MainActivity.java` 拦截返回 → 调
 * `window.__vvNativeBack()` → 本模块按**后进先出**依次尝试页面注册的处理器
 * （如阅读器的目录/设置/词卡弹层、全局账户抽屉）。
 * 某个处理器返回 true = 已消费本次返回（关掉最上层弹层），原生不再回退/退出。
 *
 * 浏览器里这段是死代码：没有任何调用方，`__vvNativeBack` 只被原生壳 invoke。
 */
import { onBeforeUnmount } from 'vue'

type NativeBackHandler = () => boolean

const handlers: NativeBackHandler[] = []

/** 注册一个「关闭优先」处理器；返回注销函数（组件卸载自动注销） */
export function registerNativeBackHandler(handler: NativeBackHandler): () => void {
  handlers.push(handler)
  return () => {
    const i = handlers.indexOf(handler)
    if (i >= 0) handlers.splice(i, 1)
  }
}

/** 后进先出：最后注册的（视觉上最上层）优先；全部未消费 → false（交给原生回退/退出） */
export function runNativeBackHandlers(): boolean {
  for (let i = handlers.length - 1; i >= 0; i -= 1) {
    const handler = handlers[i]
    if (handler?.()) return true
  }
  return false
}

/** 挂到 window 供原生壳调用（幂等） */
export function installNativeBackBridge(): void {
  ;(window as Window & { __vvNativeBack?: () => boolean }).__vvNativeBack = runNativeBackHandlers
}

/** 组件内用法：setup 中注册，卸载自动注销 */
export function useNativeBack(handler: NativeBackHandler): void {
  const off = registerNativeBackHandler(handler)
  onBeforeUnmount(off)
}
