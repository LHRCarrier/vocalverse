/**
 * 跟唱歌词区组件测试（components/sing/SingLyrics，2026-09-22 按视频模板重排）。
 * 覆盖：时间数字、当前句颜色推进（clip-path 裁出已唱宽度）、透明度渐隐分层（焦点句最亮）、
 * 无焦点态、降级档语义完整、拖动后自动归位（含「瞬时归零后紧接着拖动」回归）。
 */
import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import SingLyrics from '@/components/sing/SingLyrics.vue'

const lines = [
  { seq: 1, start_ms: 0, end_ms: 1000, text: 'line one' },
  { seq: 2, start_ms: 1000, end_ms: 3000, text: 'line two' },
  { seq: 3, start_ms: 3000, end_ms: 5000, text: 'line three' },
  { seq: 4, start_ms: 5000, end_ms: 7000, text: 'line four' },
  { seq: 5, start_ms: 7000, end_ms: 9000, text: 'line five' },
  { seq: 6, start_ms: 9000, end_ms: 11_000, text: 'line six' },
  { seq: 7, start_ms: 11_000, end_ms: 13_000, text: 'line seven' },
]

const mountWith = (timeMs: number | null) => mount(SingLyrics, { props: { lines, timeMs } })

beforeEach(() => {
  document.documentElement.dataset.motion = 'high'
})

describe('SingLyrics · 播放位置数字（取代传统进度条）', () => {
  it('显示 mm:ss；无游标 → 不渲染占位（排版优化：`--:--` 在真机上像渲染坏了）', () => {
    expect(mountWith(0).find('.m-sing-lyrics__time').text()).toBe('00:00')
    expect(mountWith(52_000).find('.m-sing-lyrics__time').text()).toBe('00:52')
    expect(mountWith(65_000).find('.m-sing-lyrics__time').text()).toBe('01:05')
    expect(mountWith(null).find('.m-sing-lyrics__time').exists()).toBe(false)
    // 时钟槽位本身仍在（高度由 CSS `min-height: 16px` 固定）→ 有无游标切换时歌词区不跳动
    expect(mountWith(null).find('.m-sing-lyrics__head').exists()).toBe(true)
  })

  it('不再渲染传统进度条元素', () => {
    expect(mountWith(1500).find('.m-sing-lyric__bar').exists()).toBe(false)
  })
})

describe('SingLyrics · 当前句颜色推进（进度指示）', () => {
  it('已唱层用 clip-path 裁出已唱宽度（0 / 25% / 100%）', () => {
    const rightInsetPct = (t: number) => {
      const s = mountWith(t).find('.m-sing-lyric__sung').attributes('style') ?? ''
      return Number(/inset\(0 ([\d.]+)%/.exec(s)?.[1])
    }
    // 第 2 句 1000~3000ms（注意 t=3000 恰好切到第 3 句 → 该句进度归 0，是刻意的边界语义）
    expect(rightInsetPct(1000)).toBe(100) // 未开始唱
    expect(rightInsetPct(1500)).toBe(75) // 唱到 25%
    expect(rightInsetPct(2000)).toBe(50) // 唱到一半
    expect(rightInsetPct(2999)).toBeLessThan(1) // 句尾：几乎唱完（浮点尾数不做精确串比较）
  })

  it('已唱层文案与当前句一致，且只有一行带已唱层', () => {
    const w = mountWith(1500)
    const sung = w.findAll('.m-sing-lyric__sung')
    expect(sung).toHaveLength(1)
    expect(sung[0].text()).toBe('line two')
    expect(sung[0].attributes('aria-hidden')).toBe('true')
  })

  it('未播放（timeMs=null）→ 无焦点句、无已唱层', () => {
    const w = mountWith(null)
    expect(w.findAll('.m-sing-lyric.is-focus')).toHaveLength(0)
    expect(w.find('.m-sing-lyric__sung').exists()).toBe(false)
  })

  it('clip-path 随句内时间单调推进（同一句内）', () => {
    const pct = (t: number) => {
      const s = mountWith(t).find('.m-sing-lyric__sung').attributes('style') ?? ''
      return Number(/inset\(0 ([\d.]+)%/.exec(s)?.[1])
    }
    expect(pct(1000)).toBe(100)
    expect(pct(1500)).toBe(75)
    expect(pct(2999)).toBeLessThan(1)
    expect(pct(1000)).toBeGreaterThan(pct(1500))
    expect(pct(1500)).toBeGreaterThan(pct(2999))
  })

  /**
   * 句内逐字节奏（2026-09-22 用户口径：整句对得上，但唱得有快有慢、唱到哪个字对不上）。
   * 有 `pitch_ref.midi` 时按音符段推进（长音慢填/短音快填/休止保持），不再按整句匀速。
   */
  it('有参考旋律时：clip-path 按音符段推进（长音过半只填 1/4 字，而非线性的 3/8）', () => {
    // 单句 0~2000ms：长音 0~1500（47 帧）+ 短音 1500~1984（15 帧），文本 4 字
    const rhythmLines = [
      {
        seq: 1,
        start_ms: 0,
        end_ms: 2000,
        text: 'abcd',
        pitch_ref: { midi: [...Array(47).fill(60), ...Array(15).fill(62)] },
      },
    ]
    const pct = (t: number) => {
      const s =
        mount(SingLyrics, { props: { lines: rhythmLines, timeMs: t } })
          .find('.m-sing-lyric__sung')
          .attributes('style') ?? ''
      return Number(/inset\(0 ([\d.]+)%/.exec(s)?.[1])
    }
    expect(pct(0)).toBe(100)
    expect(pct(752)).toBeCloseTo(75, 1) // 长音过半 → 只填 1 个字（线性口径会是 ~62%）
    expect(pct(1504)).toBeCloseTo(50, 1) // 长音结束 → 2/4 字
    expect(pct(1984)).toBeCloseTo(0, 1) // 短音结束 → 全填
  })

  it('无参考旋律（pitch_ref 缺失/全静音）→ 回退按句长线性推进（旧口径不变）', () => {
    const noPitch = [
      { seq: 1, start_ms: 0, end_ms: 1000, text: 'abcd' },
      { seq: 2, start_ms: 1000, end_ms: 2000, text: 'efgh', pitch_ref: { midi: [-1, -1, -1] } },
    ]
    const pct = (t: number) => {
      const s =
        mount(SingLyrics, { props: { lines: noPitch, timeMs: t } })
          .find('.m-sing-lyric__sung')
          .attributes('style') ?? ''
      return Number(/inset\(0 ([\d.]+)%/.exec(s)?.[1])
    }
    expect(pct(500)).toBe(50) // 线性
    expect(pct(1500)).toBe(50) // 第 2 句无有效音符 → 同样线性
  })
})

describe('SingLyrics · 透明度渐隐（远近表达，按视频模板：不用模糊）', () => {
  it('焦点句 is-dim-0（最亮）；±1 为 1 级；±2 为 2 级；更远封顶 3 级', () => {
    const w = mountWith(1500) // 时间轴当前句 idx=1
    const rows = w.findAll('.m-sing-lyric')
    expect(rows[1].classes()).toContain('is-focus')
    expect(rows[1].classes()).toContain('is-dim-0')
    expect(rows[0].classes()).toContain('is-dim-1')
    expect(rows[2].classes()).toContain('is-dim-1')
    expect(rows[3].classes()).toContain('is-dim-2')
    expect(rows[6].classes()).toContain('is-dim-3') // 距离 5 → 封顶 3
  })

  it('无游标（timeMs=null）→ 每行都取 1 级（可读），无焦点句、**无最淡行**', () => {
    // 2026-09-22 排版优化：旧口径无游标时把每行都算成 3 级（opacity 0.20）→
    // 真机截图里整张歌词卡看着像空白卡（用户反馈的「大面积留白」主要来源之一）。
    const w = mountWith(null)
    expect(w.findAll('.m-sing-lyric.is-dim-1')).toHaveLength(lines.length)
    expect(w.findAll('.m-sing-lyric.is-dim-3')).toHaveLength(0)
    expect(w.findAll('.m-sing-lyric.is-focus')).toHaveLength(0)
  })

  it('不再有模糊相关类（远近改用透明度表达）', () => {
    const w = mountWith(1500)
    expect(w.find('.is-blur-1').exists()).toBe(false)
    expect(w.find('.is-blur-3').exists()).toBe(false)
  })

  it('几何契约（占比上限 + 行高与容器解耦 + 首/末句可居中 + 透明度分级，任意屏尺寸成立）', () => {
    // 「占比」= 卡片 `max-height: L × var(--rows-cap) + 卡头`（2026-09-22 尺寸优化：不再吃满剩余空间）；
    // 「行高」= `--line-h: clamp(42px, 6.6vh, 56px)` —— 由**屏高**定，**不再**由容器高度反推
    //   （旧口径 `100%/5.5` 会在实时分区展开/收起时让所有行重排一遍）；「可见句数随 H 浮动」；
    // 「字号」= 正文 `clamp(14px, 4vw, 17px)` / 焦点 `clamp(16px, 4.6vw, 19px)`；
    // 「留白」= (H − L)/2（用**元素**而非 padding：padding 百分比按宽度解析，高度比例必须靠子元素高度）；
    // 「边缘渐隐」= 0.45L（H 不再是 L 的整数倍 → 边行可能被裁一半，靠它柔和化开）。
    // 任一被改即红（2026-09-22）。
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    expect(css).toContain('--line-h: clamp(42px, 6.6vh, 56px)') // 行高由屏高定（与容器解耦）
    expect(css).toContain('max-height: calc(var(--line-h) * var(--rows-cap, 7) + 30px)') // 占比上限
    expect(css).toContain('font-size: clamp(14px, 4vw, 17px)') // 正文字号
    expect(css).toContain('font-size: clamp(16px, 4.6vw, 19px)') // 焦点字号
    expect(css).toContain('min-height: var(--line-h)') // 每行 = L
    expect(css).toContain('height: max(0px, calc((100% - var(--line-h)) / 2))') // 留白 → 首/末句也能居中
    expect(css).toContain('calc(var(--line-h) * 0.45)') // 边缘渐隐带按行高表达
    expect(css).toContain('.is-dim-1') // 透明度渐隐分级
    expect(css).toContain('.is-dim-3')
    expect(css).not.toContain('is-blur-1') // 不再用模糊
    expect(css).not.toContain('min-height: calc(100% / 5.5)') // 旧口径不得回流（否则行高又被容器绑架）
    // 视图侧：歌词区 + 顶栏组件 + 底部五键组件（2026-09-22 深色录唱页）
    const view = readFileSync(resolve(process.cwd(), 'src/views/mobile/MobileSingView.vue'), 'utf-8')
    expect(view).toContain('<SingActionBar')
    expect(view).toContain('<SingSheetHead')
    const bar = readFileSync(resolve(process.cwd(), 'src/components/sing/SingActionBar.vue'), 'utf-8')
    expect(bar).toContain('class="m-sing-dock"')
    expect(bar).toContain('m-sing-dock__main')
    expect(bar).toContain('m-sing-dock__key')
  })

  it('占比上限：`--rows-cap` = 句数 + 1（封顶 7 行），短歌卡片更矮', () => {
    const cap = (w: ReturnType<typeof mountWith>) =>
      (w.find('.m-sing-lyrics').element as HTMLElement).getAttribute('style') ?? ''
    expect(cap(mountWith(0))).toContain('--rows-cap: 7') // lines fixture 有 7 句 → 封顶 7
    const short = mount(SingLyrics, {
      props: { lines: lines.slice(0, 4), timeMs: 0 },
    })
    expect(cap(short)).toContain('--rows-cap: 5') // 4 句 → 5 行（不是 7）
  })

  it('降级档语义：颜色推进保留（`blurLevel` 的档位门控见 lib 单测），样式表含 off 降级规则', () => {
    // 注意：`useMotionTier` 是模块级单例、只在首次调用时读档，改 dataset 不会改变 tier；
    // 这里校验样式契约（与既有 MobileSingView 的「样式契约」测试同款做法：读 CSS 源文件）。
    const w = mountWith(1500)
    expect(w.find('.m-sing-lyric__sung').attributes('style')).toContain('inset(0 75% 0 0)')
    expect(w.find('.m-sing-lyric.is-focus').text()).toContain('line two')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    expect(css).toContain("html[data-motion='off'] .m-sing-lyric")
    expect(css).toContain('mask-image: linear-gradient') // 边缘柔和渐隐
  })
})

describe('SingLyrics · 拖动后自动归位', () => {
  afterEach(() => vi.useRealTimers())

  /** happy-dom 无布局：桩出「视口 300 / 行高 50 / 首行顶 150（留白）」的等高歌词几何。
   *  行位置随 `scrollTop` 上移（真实滚动语义）——否则 `padTop` 会随 scrollTop 一起漂，
   *  「最近中心句」永远算回第 0 句。 */
  const stubGeometry = (box: HTMLElement, rows: HTMLElement[]) => {
    const rect = (top: number, height: number) =>
      ({
        top,
        bottom: top + height,
        height,
        left: 0,
        right: 0,
        width: 0,
        x: 0,
        y: top,
        toJSON: () => ({}),
      }) as DOMRect
    Object.defineProperty(box, 'clientHeight', { value: 300, configurable: true })
    Object.defineProperty(box, 'scrollHeight', { value: 650, configurable: true }) // 可滚 350
    box.getBoundingClientRect = () => rect(0, 300)
    box.scrollTop = 0
    rows.forEach((r, i) => {
      r.getBoundingClientRect = () => rect(150 + i * 50 - box.scrollTop, 50)
    })
  }

  const stubRows = (w: ReturnType<typeof mountWith>) =>
    w.findAll('.m-sing-lyric').map((r) => r.element as HTMLElement)

  it('用户拖动（scroll）期间不抢滚动；停止 2s 后自动居中当前句', async () => {
    vi.useFakeTimers()
    const scrollTo = vi.fn()
    // happy-dom 无真实布局：桩掉 scrollTo 以断言「自动归位」被触发
    Element.prototype.scrollTo = scrollTo as unknown as Element['scrollTo']
    const w = mountWith(1500)
    const box = w.find('.m-sing-lyrics__scroller').element as HTMLElement
    scrollTo.mockClear()
    // 拖动（该 scroll 事件非自身滚动）
    box.dispatchEvent(new Event('scroll'))
    // 拖动期间换句：不应抢滚动
    await w.setProps({ timeMs: 4000 })
    expect(scrollTo).not.toHaveBeenCalled()
    // 停止拖动 2s → 自动归位
    vi.advanceTimersByTime(2100)
    expect(scrollTo).toHaveBeenCalled()
  })

  it('程序化滚动不被当成用户拖动，只有「距离不再缩小」才交还控制权', async () => {
    // 回归（2026-09-22 真机实测）：判「自身滚动」曾用**固定 700ms 时间窗**，慢设备上平滑滚动的
    // scroll 事件晚于窗口到达 → 被误判为用户拖动 → 焦点句跳到「视口中心句」并与自动滚动互相
    // 打架（时钟单调推进 00:00→00:10 期间焦点却在 0/1/2 句之间来回跳）。现改为按目标距离判断。
    vi.useFakeTimers()
    const scrollTo = vi.fn()
    Element.prototype.scrollTo = scrollTo as unknown as Element['scrollTo']
    const w = mountWith(1500) // 时间轴当前句 idx=1
    const box = w.find('.m-sing-lyrics__scroller').element as HTMLElement
    stubGeometry(box, stubRows(w))
    scrollTo.mockClear()
    // 换句 → 平滑滚动到第 2 句（idx=2）居中：目标 = (150+100) − (300−50)/2 = 125
    await w.setProps({ timeMs: 4000 })
    expect(scrollTo).toHaveBeenCalledWith({ top: 125, behavior: 'smooth' })
    // 平滑滚动逐步逼近目标：一律不算用户拖动，焦点句仍是时间轴当前句
    for (const st of [30, 80, 120, 125]) {
      box.scrollTop = st
      box.dispatchEvent(new Event('scroll'))
      await nextTick()
      expect(w.find('.m-sing-lyric.is-focus').text()).toContain('line three')
    }
    // 用户接管（距离从 0 变大到 65）→ 焦点切到视口中心句（scrollTop 60 → 最近中心是 idx=1）
    box.scrollTop = 60
    box.dispatchEvent(new Event('scroll'))
    await nextTick()
    expect(w.find('.m-sing-lyric.is-focus').text()).toContain('line two')
  })

  it('时间轴归零（无游标）→ 首句顶对齐（瞬时），不再把首句居中留出半屏空白', async () => {
    // 回归：无游标时旧实现归零到 `scrollTop = 0`，等价于「首句居中」——留白 (H−L)/2 全露在上方，
    // 未播放/未开口时卡片上半张是空的（2026-09-22 排版优化改为顶对齐：`top = padTop`）。
    vi.useFakeTimers()
    const scrollTo = vi.fn()
    Element.prototype.scrollTo = scrollTo as unknown as Element['scrollTo']
    const w = mountWith(1500)
    const box = w.find('.m-sing-lyrics__scroller').element as HTMLElement
    stubGeometry(box, stubRows(w)) // 首行顶 150 = 留白（padTop）
    await w.setProps({ timeMs: null }) // current 1 → -1：走瞬时归零分支
    expect(scrollTo).toHaveBeenCalledWith({ top: 150, behavior: 'auto' })
    // 真机上瞬时滚动会**真的**落到目标（这里 scrollTo 是桩，故手动补上落位 + 一次 scroll 事件）；
    // 缺这一步会把「用户从 0 拖到 120」误当成「自身滚动还在途」（120 比 0 更接近目标 150）。
    box.scrollTop = 150
    box.dispatchEvent(new Event('scroll'))
    // 用户立刻把视口拖到 120（远离归零目标）→ 应立刻交还控制权
    box.scrollTop = 120
    box.dispatchEvent(new Event('scroll'))
    await nextTick()
    const focus = w.find('.m-sing-lyric.is-focus')
    expect(focus.exists()).toBe(true)
    expect(focus.text()).toContain('line three') // 120 → 最近中心 idx=2
  })

  it('有游标 → 当前句居中（顶对齐只作用于无游标态）', async () => {
    vi.useFakeTimers()
    const scrollTo = vi.fn()
    Element.prototype.scrollTo = scrollTo as unknown as Element['scrollTo']
    const w = mountWith(null)
    const box = w.find('.m-sing-lyrics__scroller').element as HTMLElement
    stubGeometry(box, stubRows(w))
    scrollTo.mockClear()
    await w.setProps({ timeMs: 0 }) // 首句命中时间轴
    // 居中目标 = firstRect.top(150) − (clientHeight 300 − 行高 50)/2 = 25（≠ 顶对齐的 150）
    expect(scrollTo).toHaveBeenCalledWith({ top: 25, behavior: 'smooth' })
  })
})
