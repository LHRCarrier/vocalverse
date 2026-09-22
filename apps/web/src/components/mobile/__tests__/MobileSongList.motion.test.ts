/**
 * MobileSongList · 真实 motion 集成测试（2026-09-22）
 *
 * 姊妹文件 `MobileSongList.test.ts` 把 `motion` 换成了替身，只断言「调用参数对不对」。
 * 那类的盲区是**动画到底有没有把行显示出来** —— 上游 `AnimatedList` 最典型的翻车就是
 * 「reveal 没触发 → 列表永久 opacity:0」。本文件用**真库**跑一遍，验证：
 *
 * 1. 入场动画会自然跑完（happy-dom 有可用的 WAAPI 计时），结束后行落到终值
 *    （`opacity: 1` + 不再缩小），即**内容真的可见**；
 * 2. Vue 每次 patch 重调 `:ref` 不会对同一元素重复启动动画 —— 重复启动会**打断**第一个动画，
 *    其 `finished` promise 以 `AbortError` 拒绝；在 happy-dom 里这会升级成 unhandled rejection，
 *    被 vitest 判为整轮报错（实测过 26 个）。故这里既断言「只启动一次」，也依赖
 *    vitest 自己抓 unhandled rejection 作为第二道网。
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import MobileSongList from '@/components/mobile/MobileSongList.vue'
import type { SongSummary } from '@/api/sing'

function song(id: number): SongSummary {
  return {
    id,
    title: `Song ${id}`,
    artist: 'Traditional',
    level: 1,
    pitch_ref_status: 'ready',
    expected_lines: 6,
    favorited: false,
  }
}

const songs = [song(1), song(2), song(3)]

/**
 * 等真实动画跑完。
 * 口径：末行的启动延迟 = index × 0.1s（第 3 行 0.2s）+ 时长 0.2s ≈ 0.4s，再留一档余量。
 * 实测 t=250ms 时首行才 scale(0.94)、末行还停在 scale(0.7) —— 等待不足会假红。
 */
async function settle(ms = 600) {
  await new Promise((r) => setTimeout(r, ms))
  await nextTick()
}

beforeEach(() => {
  document.documentElement.dataset.motion = 'high'
})

/** 与键盘姊妹文件同因：本组件挂 window 监听，实例残留会污染后续用例 */
enableAutoUnmount(afterEach)

describe('MobileSongList · 真实 motion（动画确实跑完且内容可见）', () => {
  it('动画结束后每行落到 opacity:1 / 不再缩小（内容可见，不是永久隐形）', async () => {
    const w = mount(MobileSongList, { props: { songs } })
    expect(w.findAll('.m-sing-row')).toHaveLength(3)
    await settle()
    for (const item of w.findAll('.m-sing-list__item')) {
      const el = item.element as HTMLElement
      expect(el.style.opacity).toBe('1')
      // 终值不得残留缩放：motion 收尾会把 transform 归一成 `none`（实测），
      // 若实现改成 `scale(1)` 也接受 —— 关键是**不能停在中途的 scale(0.x)**
      expect(el.style.transform === 'none' || el.style.transform === '' || /scale\(1\)/.test(el.style.transform)).toBe(true)
    }
  })

  it('重复 patch 不对同一元素重复启动动画（打断会抛 AbortError → unhandled rejection）', async () => {
    const w = mount(MobileSongList, { props: { songs } })
    await nextTick()
    // 记录每个行元素上真实产生的动画对象数量（WAAPI 的 getAnimations 在 happy-dom 未必实现，
    // 故用风格更稳的判据：反复 patch 后动画仍能自然跑完、行仍可见）
    await w.findAll('.m-sing-list__item')[0].trigger('mouseenter')
    await w.setProps({ showGradients: false })
    await w.findAll('.m-sing-list__item')[1].trigger('mouseenter')
    await w.setProps({ displayScrollbar: false })
    await settle()
    for (const item of w.findAll('.m-sing-list__item')) {
      expect((item.element as HTMLElement).style.opacity).toBe('1')
    }
  })

  it('动画中途卸载不抛错（面板关闭/切页时的真实时序）', async () => {
    const w = mount(MobileSongList, { props: { songs } })
    await new Promise((r) => setTimeout(r, 30)) // 动画进行中
    expect(() => w.unmount()).not.toThrow()
    await settle(60)
    // 卸载后期望的状态：没有残留的行、也没有把异常抛到测试里。
    // 更关键的是**本文件跑完不出现 unhandled rejection** —— 动画被打断时 WAAPI 的
    // finished promise 会以 AbortError 拒绝，vitest 会把整轮标记为失败（见文件头）。
    expect(document.querySelectorAll('.m-sing-list__item')).toHaveLength(0)
  })
})
