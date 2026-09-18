/**
 * 加载态防抖（docs/31 §2 硬规则 3：加载 >300ms 才出指示器）
 *
 * 解决两个真实体验问题：
 *   1) 快速返回时骨架屏一闪而过（实测真机仅显示 18ms）——比不显示更显卡顿；
 *   2) 已显示的骨架立刻消失会在长列表上造成"跳一下"——给最短可见时长。
 *
 * 用法：`const { visible } = useDelayedLoading(computed(() => store.loading))`
 * 注意：`visible` 只控制"指示器"，业务数据分支仍按原 loading/空态判断。
 */
import { onScopeDispose, ref, watch, type Ref } from 'vue'

export function useDelayedLoading(
  loading: Ref<boolean>,
  opts: { delay?: number; minVisible?: number } = {},
): { visible: Ref<boolean>; pending: Ref<boolean> } {
  const delay = opts.delay ?? 300
  const minVisible = opts.minVisible ?? 300
  const visible = ref(false)

  let timer: ReturnType<typeof setTimeout> | null = null
  let shownAt = 0

  const clear = () => {
    if (timer) {
      clearTimeout(timer)
      timer = null
    }
  }

  watch(
    loading,
    (isLoading) => {
      clear()
      if (isLoading) {
        // 未超过 delay 就结束 → 永不显示
        timer = setTimeout(() => {
          visible.value = true
          shownAt = Date.now()
          timer = null
        }, delay)
        return
      }
      if (!visible.value) return
      // 已经显示过 → 至少留够 minVisible，避免"闪一下就没"
      const remain = minVisible - (Date.now() - shownAt)
      if (remain > 0) {
        timer = setTimeout(() => {
          visible.value = false
          timer = null
        }, remain)
      } else {
        visible.value = false
      }
    },
    { immediate: true },
  )

  onScopeDispose(clear)
  /**
   * visible —— 是否**显示**加载指示器（>delay 才为真）
   * pending —— 请求是否仍在进行（用于渲染"不可见占位"，高度先占住，
   *            这样内容到达时不会把下方元素顶下去：实测可消除 CLS 0.66 的跳变）
   */
  return { visible, pending: loading }
}