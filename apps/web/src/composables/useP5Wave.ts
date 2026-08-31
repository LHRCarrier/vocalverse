/**
 * P5.js 动效封装（docs/13 §4）：仅用于"演示记忆点"类品牌动效（录音声波/氛围粒子）。
 *
 * 约定：
 * - 动态 import('p5') —— 不进首屏 chunk，Docker/演示环境无此依赖也可运行（页面级降级）；
 * - 必须由组件在 onMounted 挂载、onUnmounted 销毁，避免泄漏；
 * - 品牌色从 tokens 传入，不在此写死 hex。
 */
import type { Ref } from 'vue'
import { onBeforeUnmount, onMounted } from 'vue'

import type p5 from 'p5'

import { tokens } from '@/styles/tokens'

export function useP5Wave(
  containerRef: Ref<HTMLElement | null>,
  opts: { color?: string; height?: number } = {},
) {
  const color = opts.color ?? tokens.colors.brand
  const height = opts.height ?? 160
  let instance: p5 | null = null

  async function mount() {
    const el = containerRef.value
    if (!el) return
    try {
      const mod = await import('p5')
      const P5 = mod.default
      const sketch = (p: p5) => {
        p.setup = () => {
          p.createCanvas(el.clientWidth, height)
          p.noStroke()
        }
        p.draw = () => {
          const t = p.frameCount * 0.02
          p.background(0, 0, 0, 0)
          p.fill(color)
          for (let i = 0; i < 6; i++) {
            const size = 44 - i * 6
            const x = p.width / 2 + Math.sin(t + (i * Math.PI) / 3) * (p.width * 0.32)
            const y = p.height / 2 + Math.cos(t * 1.5 + i) * (height * 0.22)
            p.ellipse(x, y, size, size)
          }
        }
        p.windowResized = () => p.resizeCanvas(el.clientWidth, height)
      }
      instance = new P5(sketch, el)
    } catch {
      // 动效降级：CSS 兜底即可，不阻塞页面（docs/13 §4）
      instance = null
    }
  }

  onMounted(mount)
  onBeforeUnmount(() => {
    instance?.remove()
    instance = null
  })
}
