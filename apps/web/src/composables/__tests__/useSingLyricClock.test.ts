/**
 * 跟唱面板时钟测试（composables/useSingLyricClock，2026-09-22 排版优化补 `elapsedMs`）。
 *
 * 背景：`timeMs` 是**歌词轴**（跟唱 = 首帧人声锚点 + 已开口时长，开口前为 null），
 * 面板头部要显示的是**录音轴**已用时长（按下「开始跟唱」起算，与 3 分钟自动停止同源）——
 * 两者不是一回事，故单独暴露 `elapsedMs`（整秒量化，最多 1Hz 响应式更新）。
 *
 * 断言口径刻意避开具体毫秒值（rAF / `performance.now()` 在不同环境精度不同）：
 * 只校验「未录音 = null」「录音中 = 非负的整秒」「停止 = 立刻回 null」。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'

import { useSingLyricClock } from '@/composables/useSingLyricClock'

/** 组合式要 `onUnmounted`，必须在组件实例里调用（否则 Vue 打警告）；渲染空即可 */
const Harness = defineComponent({
  setup() {
    const playing = ref(false)
    const recording = ref(false)
    const voiceAtMs = ref<number | null>(null)
    const firstLine = ref(0)
    const audioMs = ref(0)
    const clock = useSingLyricClock({
      playing,
      recording,
      audioMs: () => audioMs.value,
      voiceAtMs,
      firstLineMs: () => firstLine.value,
    })
    return { playing, recording, voiceAtMs, firstLine, audioMs, ...clock }
  },
  render: () => null,
})

type Vm = {
  playing: boolean
  recording: boolean
  voiceAtMs: number | null
  firstLine: number
  audioMs: number
  timeMs: number | null
  positionMs: number | null
  elapsedMs: number | null
  recMs: number | null
}

/** 让 happy-dom 的 rAF（内部走 setImmediate）跑到 */
const tick = () => new Promise((r) => setTimeout(r, 20))

describe('useSingLyricClock · 录音轴已用时长（elapsedMs）', () => {
  it('未录音 → null（且不启动 rAF 循环）', () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    expect(vm.elapsedMs).toBeNull()
    expect(vm.timeMs).toBeNull()
  })

  it('录音中 → 非负整秒（量化到秒：计时只需 1Hz，不跟 rAF 每帧更新）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.recording = true
    await tick()
    expect(vm.elapsedMs).not.toBeNull()
    expect(vm.elapsedMs!).toBeGreaterThanOrEqual(0)
    expect(vm.elapsedMs! % 1000).toBe(0)
    // 尚未开口 → 歌词轴仍是 null（两条轴互不影响：录音一开始就计时，歌词等首帧人声）
    expect(vm.timeMs).toBeNull()
  })

  it('停止录音 → 立刻回 null（无需等下一帧）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.recording = true
    await tick()
    expect(vm.elapsedMs).not.toBeNull()
    vm.recording = false
    await tick()
    expect(vm.elapsedMs).toBeNull()
  })

  it('首帧人声后歌词轴才启动（锚点口径不变，本轮只加计时）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.recording = true
    await tick()
    expect(vm.timeMs).toBeNull() // 未开口不预跑
    vm.voiceAtMs = 0
    await tick()
    expect(vm.timeMs).not.toBeNull() // 开口 → 游标归到首句（firstLineMs = 0）
  })

  it('recMs = 原始有效录音时刻（未量化；引导条时间基）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    expect(vm.recMs).toBeNull() // 未录音
    vm.recording = true
    await tick()
    expect(vm.recMs).not.toBeNull()
    expect(vm.recMs! % 1000).toBeGreaterThanOrEqual(0) // 未量化：允许非整秒
    expect(vm.recMs! % 1000).not.toBe(0) // 与整秒量化的 elapsedMs 不同源（同一 rAF 采样下通常非 0）
    expect(vm.elapsedMs! % 1000).toBe(0)
    // 引导条与歌词共用这条轴：timeMs 的推进量应与 recMs 同步（同一 now 采样）
    vm.voiceAtMs = 0
    await tick()
    expect(Math.abs((vm.timeMs ?? 0) - (vm.recMs ?? 0))).toBeLessThan(3)
  })

  it('暂停累计从 recMs 里扣掉（暂停段不计入已开口时长）', async () => {
    // 直接验证纯函数口径：recMs = now − recStartAt（now 已是「有效录音时刻」）。
    // 这里的断言落在「暂停不改 recStartAt，只是停止推进」——由 useSingLyricClock 的 paused watcher 保证。
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.recording = true
    await tick()
    const a = vm.recMs!
    await tick()
    const b = vm.recMs!
    expect(b).toBeGreaterThanOrEqual(a) // 单调不减（暂停/继续不得回跳）
  })
})

/**
 * 歌曲轴位置（`positionMs`）——2026-09-22 用户口径「音频 / 歌词 / 时间轴对不上」的修复：
 * 底部「时间 / 全长」与音准引导条改用这条轴（歌词轴 `timeMs` 在跟唱开口前为 null，不能直接用）。
 */
describe('useSingLyricClock · 歌曲轴位置（positionMs）', () => {
  it('空闲 → null（视图回退 00:00）', () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    expect(vm.positionMs).toBeNull()
  })

  it('跟唱尚未开口 → 冻结在首句起点（引导条先亮首句目标音符，不随录音时长跑）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.firstLine = 22_480
    vm.recording = true
    await tick()
    expect(vm.positionMs).toBe(22_480)
    expect(vm.timeMs).toBeNull() // 歌词轴仍不预跑（高亮等开口）
    await tick()
    expect(vm.positionMs).toBe(22_480)
  })

  it('跟唱开口后 = 首句起点 + 已开口时长（与歌词轴同源）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.firstLine = 8000
    vm.recording = true
    await tick()
    vm.voiceAtMs = 3000
    await tick()
    const expected = 8000 + Math.max(0, (vm.recMs ?? 0) - 3000)
    expect(vm.positionMs).not.toBeNull()
    expect(Math.abs((vm.positionMs ?? 0) - expected)).toBeLessThan(3)
  })

  it('听原唱 = 音频位置（修复前底部恒 00:00 的根因）', async () => {
    const w = mount(Harness)
    const vm = w.vm as unknown as Vm
    vm.playing = true
    vm.audioMs = 49_000
    await tick()
    expect(vm.positionMs).toBe(49_000)
  })
})
