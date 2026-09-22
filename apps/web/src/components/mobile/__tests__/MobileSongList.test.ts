/**
 * MobileSongList（唱吧歌单 · 滚动动画列表）组件测试 —— 2026-09-22
 *
 * 上游是 React Bits `AnimatedList`，本组件是它的 Vue 移植（逐项对照见组件头注释）。
 * 这里锁的是**移植后必须成立的契约**，以及三处有意偏离上游的理由：
 *
 * 1. **滚动区定高**（本需求的全部意义）：曲库只有 3 首时看不出问题，几十首时原来那条
 *    `.u-dotline` 长列表会把整页拉到几千像素。故用样式契约守卫 `max-height` + `overflow-y: auto`
 *    必须同时存在 —— 少任何一个都退回「随内容长高」。
 * 2. **不注入隐藏初值**（偏离 1）：上游 `initial={{opacity:0}}` + `useInView` 才显形；
 *    宿主 `IntersectionObserver` 不触发时整个列表会**永久空白**。本组件默认可见、动画只做叠加，
 *    且宿主没有 WAAPI 时压根不启动动画 —— 这两条各自有用例钉住。
 * 3. **键盘导航按可见性收窄 + 尊重开关**（偏离 2/3）：列表不在屏上或
 *    `enableArrowNavigation=false` 时完全不接管 window 的 ↑↓/Tab；动效 `off` 档不放动画。
 *
 * 执行纪律：`trigger()` 会 `await nextTick()`，而 `window.dispatchEvent` **不会** ——
 * 键盘用例必须显式 await 一次，否则读到的是上一次渲染的 DOM（写成同步断言必假红）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { nextTick } from 'vue'

import type { MotionTier } from '@/composables/useMotionTier'

/** 动效档位替身：默认 high（与仓内其余测试同口径），off 用例单独改 */
const tierState = { tier: 'high' as MotionTier }
vi.mock('@/composables/useMotionTier', () => ({
  useMotionTier: () => ({ tier: { get value() { return tierState.tier } } }),
}))

/**
 * motion 替身：不真跑动画（happy-dom 下真动画会引入计时噪声），只记录调用参数。
 * 显式声明调用签名 —— 不写的话 `vi.fn(() => …)` 会被推断成**零参**函数，
 * `mock.calls[0][2]` 在 typecheck 下就是「元组没有索引 2」。
 */
type AnimateCall = [Element, Record<string, unknown>, Record<string, number>]
const animateMock = vi.fn((...args: AnimateCall) => {
  void args // 只为声明调用签名：mock 体本身不需要参数
  return { finished: Promise.resolve(), stop: vi.fn() }
})
vi.mock('motion', () => ({
  animate: (...args: AnimateCall) => animateMock(...args),
  inView: vi.fn(() => vi.fn()),
}))

import MobileSongList from '@/components/mobile/MobileSongList.vue'
import type { SongSummary } from '@/api/sing'

function song(id: number, over: Partial<SongSummary> = {}): SongSummary {
  return {
    id,
    title: `Song ${id}`,
    artist: 'Traditional',
    level: 1,
    pitch_ref_status: 'ready',
    expected_lines: 6,
    favorited: false,
    ...over,
  }
}

const songs = [song(1, { title: 'Twinkle' }), song(2, { title: 'Mary' }), song(3, { title: 'Ode' })]

function mountList(props: Record<string, unknown> = {}) {
  return mount(MobileSongList, { props: { songs, ...props } })
}

/**
 * 读出组件内部的 `listVisible` 并置位。
 * 为什么必须直接置位：happy-dom 的 `IntersectionObserver` **从不回调**（实测），
 * 而本组件在没有 `IntersectionObserver` 时按「常驻可见」降级 —— 于是 happy-dom 下
 * 键盘导航是**开**的，可见性守卫这条分支只能靠直接改状态来覆盖。
 */
function setListVisible(w: ReturnType<typeof mountList>, value: boolean) {
  ;(w.vm as unknown as { listVisible: boolean }).listVisible = value
}

/** 派发键盘事件并等一次渲染（window.dispatchEvent 不会自动 flush） */
async function press(key: string, init: KeyboardEventInit = {}) {
  const e = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init })
  window.dispatchEvent(e)
  await nextTick()
  return e
}

/** 选中行的下标（无选中 → null） */
function selectedIndex(w: ReturnType<typeof mountList>): string | null {
  return w.find('.m-sing-list__item.is-selected').exists()
    ? w.get('.m-sing-list__item.is-selected').attributes('data-index')!
    : null
}

/** 渐隐带的 opacity（从内联样式里读） */
function gradientOpacity(w: ReturnType<typeof mountList>, which: 'top' | 'bottom'): number {
  const style = w.get(`.m-sing-list__grad--${which}`).attributes('style') ?? ''
  return Number(style.match(/opacity:\s*([\d.]+)/)?.[1])
}

/** 伪造滚动几何（happy-dom 无排版引擎，scrollTop/scrollHeight 恒为 0） */
async function fakeScroll(w: ReturnType<typeof mountList>, top: number, height: number, client: number) {
  const scroller = w.get('.m-sing-list__scroll')
  Object.defineProperties(scroller.element, {
    scrollTop: { value: top, configurable: true },
    scrollHeight: { value: height, configurable: true },
    clientHeight: { value: client, configurable: true },
  })
  await scroller.trigger('scroll')
}

beforeEach(() => {
  tierState.tier = 'high'
  animateMock.mockClear()
})

/**
 * **必须自动卸载**：本组件在 window 上挂 keydown，且键盘用例会把 `listVisible` 置 true。
 * 上一个用例的实例若还活着，它的监听器会先 `preventDefault()` 掉下一个用例的按键 →
 * 下一个用例的组件被「别处已处理」守卫挡掉 → 假红（实测：滚动用例之后三个用例集体失败）。
 */
enableAutoUnmount(afterEach)

describe('MobileSongList · 结构与滚动容器', () => {
  it('每首歌一个动画壳 + 一行 MobileSongRow；下标写进 data-index', () => {
    const w = mountList()
    const items = w.findAll('.m-sing-list__item')
    expect(items).toHaveLength(3)
    expect(w.findAll('.m-sing-row')).toHaveLength(3) // 行本体仍是 MobileSongRow（交互不变）
    expect(items.map((i) => i.attributes('data-index'))).toEqual(['0', '1', '2'])
    expect(w.find('.m-sing-list__scroll').exists()).toBe(true)
  })

  it('上下渐隐默认渲染（showGradients），关掉即不渲染', async () => {
    const w = mountList()
    expect(w.find('.m-sing-list__grad--top').exists()).toBe(true)
    expect(w.find('.m-sing-list__grad--bottom').exists()).toBe(true)
    await w.setProps({ showGradients: false })
    expect(w.find('.m-sing-list__grad--top').exists()).toBe(false)
    expect(w.find('.m-sing-list__grad--bottom').exists()).toBe(false)
  })

  it('滚动改渐隐透明度：未滚时顶部全透明、滚过半屏后两端都显形', async () => {
    const w = mountList()
    expect(gradientOpacity(w, 'top')).toBe(0) // 未滚 → 不压暗首行
    await fakeScroll(w, 100, 1000, 300) // 内容远长于一屏
    expect(gradientOpacity(w, 'top')).toBe(1)
    expect(gradientOpacity(w, 'bottom')).toBe(1)
  })

  /**
   * **真机实测抓到的 BUG（2026-09-22，本用例即回归守卫）**：
   * 上游只在 `onScroll` 里算渐隐透明度，而「内容不满一屏」**永远不产生滚动事件** →
   * 底渐隐停在初值 `1`，把**最后一张卡整片糊掉**（真机截图里第三首的副文与徽标被纸面色洗掉）。
   *
   * 下面这条**必须在不伪造任何滚动几何的前提下**断言：happy-dom 里
   * `scrollHeight === clientHeight === 0` → 正是「没有可滚内容」这一档 → 底渐隐必须是 0。
   * 修复前这里会读到 1（= 开局就把末行压暗），是真正能红的那条判据。
   */
  it('**初始即判定**：内容不满一屏时底渐隐为 0（不靠滚动事件，修复前必失败）', async () => {
    const w = mountList()
    // 挂载期 `onMounted` 里的测量会把 ref 改掉，但内联样式要下一次渲染才落盘 → 必须 await
    await nextTick()
    expect(gradientOpacity(w, 'bottom')).toBe(0)
    expect(gradientOpacity(w, 'top')).toBe(0)
  })

  it('内容不满一屏 → 滚动事件也不把底渐隐点亮', async () => {
    const w = mountList()
    await fakeScroll(w, 0, 300, 300) // scrollHeight === clientHeight → 没有可滚内容
    expect(gradientOpacity(w, 'bottom')).toBe(0)
  })

  it('曲目变为"不满一屏"后重测渐隐（不会把上一种状态的旧值留着）', async () => {
    const w = mountList()
    // ① 先撑成"内容超一屏且停在顶部" → 底渐隐 1（提示下面还有）
    await fakeScroll(w, 0, 1000, 300)
    expect(gradientOpacity(w, 'bottom')).toBe(1)
    // ② 曲目减到 1 首，并把几何改回"不满一屏"（happy-dom 无排版引擎，几何只能自己摆）
    await w.setProps({ songs: songs.slice(0, 1) })
    await nextTick()
    await fakeScroll(w, 0, 300, 300)
    expect(w.findAll('.m-sing-list__item')).toHaveLength(1)
    // ③ 行数变化触发的重测必须把底渐隐归零（不重测就会留着 1 → 糊住唯一那张卡）
    expect(gradientOpacity(w, 'bottom')).toBe(0)
  })

  it('displayScrollbar=false → 加 is-nobar 类（只藏滑块，不锁滚动）', async () => {
    const w = mountList()
    expect(w.get('.m-sing-list__scroll').classes()).not.toContain('is-nobar')
    await w.setProps({ displayScrollbar: false })
    expect(w.get('.m-sing-list__scroll').classes()).toContain('is-nobar')
  })

  it('className / itemClassName 透传（上游同名 props）', () => {
    const w = mountList({ className: 'my-list', itemClassName: 'my-item' })
    expect(w.get('.m-sing-list').classes()).toContain('my-list')
    expect(w.get('.m-sing-list__item').classes()).toContain('my-item')
  })
})

describe('MobileSongList · 行交互与下标', () => {
  it('点行 → emit preview(songId, index)（2026-09-23 原型口径：行=试听，下标即上游 onItemSelect 的第二参数）', async () => {
    const w = mountList()
    await w.findAll('button.m-sing-row__hit')[2].trigger('click')
    expect(w.emitted('preview')?.[0]).toEqual([3, 2])
    expect(w.emitted('open')).toBeUndefined()
  })

  it('点「去跟唱」药丸 → emit open(songId, index)（行内独立按钮，不触发试听）', async () => {
    const w = mountList()
    await w.findAll('button.m-sing-row__sing')[1].trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([2, 1])
    expect(w.emitted('preview')).toBeUndefined()
  })

  it('activeId 命中该行 → 叠加在播音波（`.m-sing-row.is-active`）', () => {
    const w = mountList({ activeId: 2 })
    const rows = w.findAll('.m-sing-row')
    expect(rows[1].classes()).toContain('is-active')
    expect(rows[1].find('.m-sing-row__wave').exists()).toBe(true)
    expect(rows[0].find('.m-sing-row__wave').exists()).toBe(false)
  })

  it('点收藏 → emit favorite(song)，且**不会**顺带触发试听/跟唱（三颗独立按钮，嵌套 button 无效）', async () => {
    const w = mountList()
    await w.findAll('button.m-sing-fav')[1].trigger('click')
    expect(w.emitted('favorite')?.[0]).toEqual([songs[1]])
    expect(w.emitted('open')).toBeUndefined()
    expect(w.emitted('preview')).toBeUndefined()
  })

  it('悬停 / 聚焦把选中态挪到该行（键盘与鼠标共用同一个 selectedIndex）', async () => {
    const w = mountList()
    expect(w.findAll('.m-sing-list__item.is-selected')).toHaveLength(0)
    await w.findAll('.m-sing-list__item')[1].trigger('mouseenter')
    expect(selectedIndex(w)).toBe('1')
    await w.findAll('.m-sing-list__item')[0].trigger('focusin')
    expect(selectedIndex(w)).toBe('0')
  })

  it('initialSelectedIndex 生效（-1 = 初始无选中）', () => {
    expect(selectedIndex(mountList({ initialSelectedIndex: 2 }))).toBe('2')
    expect(mountList().findAll('.m-sing-list__item.is-selected')).toHaveLength(0)
  })
})

describe('MobileSongList · 键盘导航（上游 enableArrowNavigation）', () => {
  it('列表不在屏上 → 完全不接管键盘（不 preventDefault、不动选中）', async () => {
    const w = mountList()
    setListVisible(w, false)
    const e = await press('ArrowDown')
    expect(e.defaultPrevented).toBe(false)
    expect(selectedIndex(w)).toBeNull()
  })

  it('enableArrowNavigation=false → 同样不接管（上游同名 props）', async () => {
    const w = mountList({ enableArrowNavigation: false })
    setListVisible(w, true)
    expect((await press('ArrowDown')).defaultPrevented).toBe(false)
    expect(selectedIndex(w)).toBeNull()
  })

  it('↑/↓ 移动选中并 preventDefault，且不越过两端', async () => {
    const w = mountList()
    setListVisible(w, true)
    expect((await press('ArrowDown')).defaultPrevented).toBe(true)
    expect(selectedIndex(w)).toBe('0')
    await press('ArrowDown')
    await press('ArrowDown')
    expect(selectedIndex(w)).toBe('2')
    await press('ArrowDown') // 已到底：停在最后一首，不越界
    expect(selectedIndex(w)).toBe('2')
    await press('ArrowUp')
    expect(selectedIndex(w)).toBe('1')
  })

  it('Enter 试听选中行（带下标）；无选中时什么也不做', async () => {
    const w = mountList()
    setListVisible(w, true)
    await press('Enter') // 初始 -1 → 无选中，不应 emit
    expect(w.emitted('preview')).toBeUndefined()
    await press('ArrowDown')
    await press('Enter')
    expect(w.emitted('preview')?.[0]).toEqual([1, 0])
  })

  it('别处已 preventDefault 的按键不抢（跟唱面板的方向键优先）', async () => {
    const w = mountList()
    setListVisible(w, true)
    const e = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true })
    e.preventDefault() // 模拟面板先处理
    window.dispatchEvent(e)
    await nextTick()
    expect(selectedIndex(w)).toBeNull()
  })

  it('Tab / Shift+Tab 也走同一套（上游口径），并 preventDefault 不让焦点跑掉', async () => {
    const w = mountList()
    setListVisible(w, true)
    expect((await press('Tab', { shiftKey: true })).defaultPrevented).toBe(true)
    expect(selectedIndex(w)).toBe('0')
    await press('Tab')
    expect(selectedIndex(w)).toBe('1')
  })

  it('键盘移动后把选中行滚回视野（上游 extraMargin=50 口径）', async () => {
    const w = mountList()
    setListVisible(w, true)
    const scroller = w.get('.m-sing-list__scroll').element as HTMLElement
    const scrollTo = vi.fn()
    Object.defineProperty(scroller, 'scrollTo', { value: scrollTo, configurable: true })
    // 第 2 行在视口下缘之外（offsetTop 400 > scrollTop 0 + clientHeight 300 - 50）
    const row = w.findAll('.m-sing-list__item')[1].element as HTMLElement
    Object.defineProperties(row, {
      offsetTop: { value: 400, configurable: true },
      offsetHeight: { value: 92, configurable: true },
    })
    await press('ArrowDown')
    await press('ArrowDown')
    expect(scrollTo).toHaveBeenCalled()
  })

  it('卸载后 window 监听器摘掉（不残留孤儿监听）', async () => {
    const w = mountList()
    setListVisible(w, true)
    await press('ArrowDown')
    expect(selectedIndex(w)).toBe('0')
    w.unmount()
    // 卸载后按键不得报错：监听器已摘；若未摘，回调会在已失效的实例上继续跑
    expect(() => {
      window.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    }).not.toThrow()
    expect(animateMock).toHaveBeenCalledTimes(3) // 卸载不产生额外动画
  })
})

describe('MobileSongList · 动效降级与「不注入隐藏初值」契约', () => {
  it('high 档：每行叠加入场动画一次（上游 duration .2 / delay .1 × index）', async () => {
    mountList()
    await nextTick()
    expect(animateMock).toHaveBeenCalledTimes(3)
    const [, keyframes, options] = animateMock.mock.calls[0]
    expect(keyframes).toEqual({ opacity: [0, 1], scale: [0.7, 1] })
    expect(options.duration).toBe(0.2)
    expect(options.delay).toBe(0) // index 0
    expect(animateMock.mock.calls[2][2].delay).toBeCloseTo(0.2) // index 2 × 0.1
  })

  it('low 档：动画时长缩短到 0.09s（与样式侧 90ms 口径对齐）', async () => {
    tierState.tier = 'low'
    mountList()
    await nextTick()
    expect(animateMock.mock.calls[0][2].duration).toBe(0.09)
  })

  it('off 档：不启动任何动画（系统「减少动效」/ 手动覆盖）', async () => {
    tierState.tier = 'off'
    mountList()
    await nextTick()
    expect(animateMock).not.toHaveBeenCalled()
    // 关掉动画不等于关掉内容
    expect(mountList().findAll('.m-sing-row')).toHaveLength(3)
  })

  it('**不注入隐藏初值**（偏离上游 1）：组件自己绝不写 opacity/transform 内联样式', async () => {
    // off 档 = 一条动画都不跑 → 此时行上的内联样式**只可能**来自组件自身。
    // 上游正是在这里写 `initial={{scale:.7, opacity:0}}`：一旦 reveal 不触发，列表永久空白。
    tierState.tier = 'off'
    const w = mountList()
    await nextTick()
    for (const item of w.findAll('.m-sing-list__item')) {
      const style = item.attributes('style') ?? ''
      expect(style).not.toMatch(/opacity/)
      expect(style).not.toMatch(/transform/)
    }
    expect(w.findAll('.m-sing-row')).toHaveLength(3)
  })

  it('重复 patch 不对同一元素重复启动动画（避免打断 → AbortError 噪声）', async () => {
    // Vue 会在 patch 中重调 `:ref` 回调，同一元素可能被 `bindItem` 命中多次；
    // 第二次 `animate()` 会打断第一个 WAAPI 动画，其 finished promise 以 AbortError 拒绝，
    // 在 happy-dom 里升级成 unhandled rejection（实测摘掉守卫后 35 个，整轮被判失败）。
    // 判据必须**按元素**去重统计 —— 只数总次数会让「同一元素两次」被漏掉。
    const w = mountList()
    await nextTick()
    expect(animateMock).toHaveBeenCalledTimes(3)
    expect(animateMock.mock.calls.map((c) => c[0].getAttribute('data-index'))).toEqual([
      '0',
      '1',
      '2',
    ])
    // 反复 patch：选中态变化 + 渐隐带增删（都会让 Vue 重走 children 的 patch）
    await w.findAll('.m-sing-list__item')[0].trigger('mouseenter')
    await w.setProps({ showGradients: false })
    await w.findAll('.m-sing-list__item')[1].trigger('mouseenter')
    await w.setProps({ displayScrollbar: false })
    await nextTick()
    const rows = w.findAll('.m-sing-list__item').map((i) => i.element)
    const counts = rows.map((r) => animateMock.mock.calls.filter((c) => c[0] === r).length)
    expect(counts).toEqual([1, 1, 1]) // 每行恰好一次
  })
})

describe('MobileSongList · 样式契约守卫', () => {
  const css = () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    return readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8') as string
  }

  it('选中态：圆角浅底、无左侧蓝条（2026-09-23 用户口径，改回即红）', () => {
    const start = css().indexOf('.m-sing-list__item.is-selected {')
    const rule = css().slice(start, css().indexOf('}', start))
    expect(rule).toContain('border-radius: 12px')
    expect(rule).not.toContain('inset 2px 0 0')
  })
  it('滚动区必须同时有 max-height 与 overflow-y（少一个就退回「随内容长高」）', () => {
    const block = css().slice(
      css().indexOf('.m-sing-list__scroll {'),
      css().indexOf('/* —— 自定义滚动条'),
    )
    expect(block).toContain('max-height')
    expect(block).toContain('overflow-y: auto')
    expect(block).toContain('--m-sing-list-row: 96px')
    // 行高口径 × 可见行数：改行高必须同步改倍数，否则可见行数会悄悄变化
    expect(block).toContain('calc(var(--m-sing-list-row) * 3.5)')
  })

  /**
   * 滚动链抑制**必须是有条件的**（2026-09-22 用户口径「滑列表时只滑列表、不滑整页」）：
   * 无条件 `contain` 在"元素不可滚"的宿主上可能把整页滚动一起吃掉（死区）。
   * 契约两条：① 基础规则里**不得**出现 overscroll-behavior；
   *          ② 只在 `.is-scrollable` 下声明 contain。
   */
  it('overscroll-behavior 只在"真有可滚内容"（.is-scrollable）时才声明', () => {
    const all = css()
    // 只取 `.m-sing-list__scroll { … }` 这一条规则本体（到它自己的 `}` 为止），
    // 否则会把紧跟着的解释性注释一起吃进来（注释里提到 overscroll-behavior，会假红）
    const start = all.indexOf('.m-sing-list__scroll {')
    const base = all.slice(start, all.indexOf('}', start))
    expect(base).not.toContain('overscroll-behavior')
    expect(all).toContain('.m-sing-list.is-scrollable .m-sing-list__scroll')
    const condStart = all.indexOf('.m-sing-list.is-scrollable .m-sing-list__scroll')
    expect(all.slice(condStart, all.indexOf('}', condStart))).toContain('overscroll-behavior: contain')
  })

  it('无溢出（happy-dom 默认 0/0）时不挂 is-scrollable —— 滚动链交给页面', async () => {
    const w = mountList()
    await nextTick()
    expect(w.get('.m-sing-list').classes()).not.toContain('is-scrollable')
  })

  it('有溢出时挂 is-scrollable（量到 scrollHeight > clientHeight）', async () => {
    const w = mountList()
    await nextTick()
    await fakeScroll(w, 0, 1000, 300)
    expect(w.get('.m-sing-list').classes()).toContain('is-scrollable')
  })

  it('渐隐带不吃点击、且不盖住滚动条', () => {
    const block = css().slice(css().indexOf('.m-sing-list__grad {'), css().indexOf('/* —— 行（入场动画壳）'))
    expect(block).toContain('pointer-events: none')
    expect(block).toContain('width: calc(100% - 10px)') // 与滚动区右内边距 10px 对齐
  })

  it('降级契约：data-motion=off 时行与渐隐都不做过渡', () => {
    expect(css()).toContain("html[data-motion='off'] .m-sing-list__item")
    expect(css()).toContain("html[data-motion='off'] .m-sing-list__grad")
  })
})
