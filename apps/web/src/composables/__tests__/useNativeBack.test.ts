/**
 * Android 返回手势「页面优先」接管（2026-09-10 · 组长手机实测 bug 3）
 * 修复前：壳里没有任何返回处理 → 系统返回手势直接结束 Activity（退回手机桌面）。
 * 修复后：原生壳调 window.__vvNativeBack() → 页面按后进先出关闭最上层弹层；
 *        未消费才回退 WebView 历史 / 退出。
 */
import { describe, expect, it } from 'vitest'

import {
  installNativeBackBridge,
  registerNativeBackHandler,
  runNativeBackHandlers,
} from '@/composables/useNativeBack'

describe('useNativeBack · 处理器注册表', () => {
  it('后进先出：最上层（最后注册）优先，一旦消费即停止', () => {
    const calls: string[] = []
    const offA = registerNativeBackHandler(() => {
      calls.push('a')
      return false
    })
    const offB = registerNativeBackHandler(() => {
      calls.push('b')
      return true
    })
    const offC = registerNativeBackHandler(() => {
      calls.push('c')
      return false
    })

    expect(runNativeBackHandlers()).toBe(true)
    expect(calls).toEqual(['c', 'b']) // b 消费 → 不再问 a

    offA()
    offB()
    offC()
  })

  it('无处理器或全部未消费 → false（交给原生回退历史/退出应用）', () => {
    expect(runNativeBackHandlers()).toBe(false)
    const off = registerNativeBackHandler(() => false)
    expect(runNativeBackHandlers()).toBe(false)
    off()
  })

  it('注销后不再被调用', () => {
    let called = 0
    const off = registerNativeBackHandler(() => {
      called += 1
      return true
    })
    off()
    expect(runNativeBackHandlers()).toBe(false)
    expect(called).toBe(0)
  })

  it('installNativeBackBridge 把入口挂到 window（原生壳唯一调用点）', () => {
    installNativeBackBridge()
    const bridge = (window as Window & { __vvNativeBack?: () => boolean }).__vvNativeBack
    expect(typeof bridge).toBe('function')

    const off = registerNativeBackHandler(() => true)
    expect(bridge?.()).toBe(true)
    off()
    expect(bridge?.()).toBe(false)
  })
})
