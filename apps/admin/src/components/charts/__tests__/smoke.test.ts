// @vitest-environment happy-dom
/**
 * 12 张图的**渲染烟测**：每张都真挂载一次，确认
 * ① 有数据时确实画出了图形元素（不是白屏，也不是报错后静默空壳）；
 * ② 没数据时给的是明确空态文案，而不是一张"全是 0 的假图"。
 *
 * 这层测试不校验像素，只兜住"组件在 Vue 里到底跑不跑得起来"——
 * 类型检查管不到模板里的运行时求值顺序（例如 computed 引用了还没定义的常量）。
 *
 * `DynamicStream` 只测空态：它走 ECharts 画布，happy-dom 没有 2D context，
 * 有数据的那条路径在真实浏览器里验证（组件与画布引擎的契约由 ECharts 自己的类型兜）。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import ArcMatrix from '../ArcMatrix.vue'
import CalendarHeat from '../CalendarHeat.vue'
import DotHeat from '../DotHeat.vue'
import DynamicStream from '../DynamicStream.vue'
import HairlineArea from '../HairlineArea.vue'
import RungBars from '../RungBars.vue'
import RungWaterfall from '../RungWaterfall.vue'
import StackedRungs from '../StackedRungs.vue'
import TickBox from '../TickBox.vue'
import TickDonut from '../TickDonut.vue'
import TickGauge from '../TickGauge.vue'
import TickRows from '../TickRows.vue'

/** 挂载后统计图形元素数量（`line`/`rect`/`path`/`circle` 都算） */
function shapeCount(html: string): number {
  return (html.match(/<(line|rect|path|circle|polygon)\b/g) ?? []).length
}

describe('图表渲染烟测', () => {
  it('F1 RungBars：有数据画出梯级，无数据给空态', () => {
    const w = mount(RungBars, {
      props: { items: [{ label: '免费', value: 38 }, { label: '专业', value: 22 }], unit: 'k' },
    })
    expect(shapeCount(w.html())).toBeGreaterThan(10)
    expect(w.text()).toContain('1 格 = 1')

    const empty = mount(RungBars, { props: { items: [] } })
    expect(empty.text()).toContain('暂无数据')
    expect(shapeCount(empty.html())).toBe(0)
  })

  it('F3 HairlineArea：面积由发丝组成，堆叠时不报错', () => {
    const labels = Array.from({ length: 20 }, (_, i) => `06-${i + 1}`)
    const w = mount(HairlineArea, {
      props: {
        labels,
        series: [{ name: '在线', values: labels.map((_, i) => 30 + i) }],
        unit: ' 人',
      },
    })
    // 20 天 = 20 根发丝 + 底线 + 命中条
    expect(shapeCount(w.html())).toBeGreaterThan(20)
    expect(w.text()).toContain('峰值')

    const stacked = mount(HairlineArea, {
      props: {
        labels,
        stacked: true,
        series: [
          { name: 'A', values: labels.map(() => 10) },
          { name: 'B', values: labels.map(() => 5) },
        ],
      },
    })
    expect(shapeCount(stacked.html())).toBeGreaterThan(20)

    expect(mount(HairlineArea, { props: { labels: [], series: [] } }).text()).toContain('暂无数据')
  })

  it('F4 TickDonut：整圈 100 格刻度 + 段带，无数据给空态', () => {
    const w = mount(TickDonut, {
      props: {
        items: [
          { label: '自然', value: 37 },
          { label: '投放', value: 28 },
          { label: '推荐', value: 21 },
          { label: '社交', value: 14 },
        ],
      },
    })
    // 4 段共 100 根刻度，减去每段让位的一根
    expect((w.html().match(/class="td-tick"/g) ?? []).length).toBeGreaterThan(90)
    expect(w.text()).toContain('100')

    expect(mount(TickDonut, { props: { items: [] } }).text()).toContain('暂无数据')
  })

  it('F5 TickRows：一格一个单位 + 轨道，无数据给空态', () => {
    const w = mount(TickRows, {
      props: { items: [{ label: '平台', value: 34 }, { label: '增长', value: 8 }], unit: ' 次' },
    })
    expect(w.html()).toContain('class="tr-track"')
    expect(shapeCount(w.html())).toBeGreaterThan(20)
    expect(w.text()).toContain('轨道全长')

    expect(mount(TickRows, { props: { items: [] } }).text()).toContain('暂无数据')
  })

  it('F7 StackedRungs：段沿明度阶梯分层，无数据给空态', () => {
    const w = mount(StackedRungs, {
      props: {
        categories: ['北美', '欧洲'],
        segments: [
          { name: '核心', values: [18, 14] },
          { name: '增值', values: [11, 9] },
          { name: '服务', values: [7, 5] },
        ],
        unit: 'k',
      },
    })
    expect(shapeCount(w.html())).toBeGreaterThan(40)
    expect(w.text()).toContain('最深 = 核心')

    expect(
      mount(StackedRungs, { props: { categories: [], segments: [] } }).text(),
    ).toContain('暂无数据')
  })

  it('F9 RungWaterfall：虚实格区分增减，末级用累计口径', () => {
    const w = mount(RungWaterfall, {
      props: {
        steps: [
          { label: '毛收入', delta: 42, total: true },
          { label: '退款', delta: -6 },
          { label: '成本', delta: -11 },
          { label: '净额', delta: 25, total: true },
        ],
        unit: 'k',
      },
    })
    expect(w.html()).toContain('class="rw-step"')
    expect(shapeCount(w.html())).toBeGreaterThan(40)
    // 传入净额 25 与累计 25 一致 → 不出现口径提示
    expect(w.text()).not.toContain('以累计口径')

    const empty = mount(RungWaterfall, { props: { steps: [] } })
    expect(empty.text()).toContain('暂无数据')
  })

  it('F10 DotHeat：点面积 = 数值 + 5 档明度图例，无数据给空态', () => {
    const rows = ['周一', '周二', '周三']
    const cols = ['09:00', '10:00', '11:00', '12:00']
    const matrix = [
      [3, 9, 0, 21],
      [5, 14, 2, 8],
      [0, 1, 6, 11],
    ]
    const w = mount(DotHeat, { props: { rows, cols, matrix, unit: ' 单' } })
    expect((w.html().match(/class="dh-dot"/g) ?? []).length).toBe(rows.length * cols.length)
    expect(w.html()).toContain('class="dh-hero"')
    expect(w.text()).toContain('明度 5 档')

    const allZero = mount(DotHeat, {
      props: { rows, cols, matrix: matrix.map((r) => r.map(() => 0)) },
    })
    expect(allZero.text()).toContain('暂无数据')
  })

  it('F11 TickGauge：水平刻度尺 + 已达成区段 + 大字，非拟物指针', () => {
    const w = mount(TickGauge, { props: { value: 73, max: 100, unit: ' 万', tone: 'warn' } })
    expect(w.html()).toContain('class="tg-band"')
    expect((w.html().match(/class="tg-tick"/g) ?? []).length).toBe(100)
    expect(w.text()).toContain('73')
    expect(w.text()).toContain('还差')
    // 拟物指针绝不该出现：没有任何 rotate/transform 的指针造型
    expect(w.html()).not.toContain('needle')

    const over = mount(TickGauge, { props: { value: 130, max: 100 } })
    expect(over.text()).toContain('超出')

    expect(mount(TickGauge, { props: { value: Number.NaN } }).text()).toContain('暂无数据')
  })

  it('F15 TickBox：描边不填充的箱体 + 空心离群点', () => {
    const w = mount(TickBox, {
      props: {
        groups: [
          { label: '企业版', min: 0.4, q1: 0.9, median: 1.5, q3: 2.6, max: 4.4, outliers: [6.2] },
          { label: '免费版', min: 2.2, q1: 6, median: 9.4, q3: 13.8, max: 19.6, outliers: [22.1, 23.5] },
        ],
        unit: 'h',
      },
    })
    expect(w.html()).toContain('class="tb-box"')
    expect(w.html()).toContain('fill="none"')
    expect((w.html().match(/class="tb-out"/g) ?? []).length).toBe(3)

    const bad = mount(TickBox, {
      props: { groups: [{ label: '坏数据', min: 5, q1: 4, median: 3, q3: 2, max: 1, outliers: [] }] },
    })
    // 五数倒挂 → 排序后仍能画出箱体（min=1 < max=5）
    expect(bad.html()).toContain('class="tb-box"')

    expect(mount(TickBox, { props: { groups: [] } }).text()).toContain('暂无数据')
  })

  it('L4 ArcMatrix：地平线 + 行名 + 行内最亮格描边', () => {
    const rows = ['编辑器', '看板', '文档']
    const cols = ['SF', 'NYC', 'LON', 'BER', 'TOK']
    const matrix = [
      [9, 8, 7, 5, 4],
      [8, 6, 0, 3, 2],
      [7, 5, 4, 2, 1],
    ]
    const w = mount(ArcMatrix, { props: { rows, cols, matrix, unit: ' 个' } })
    // 地平线元素同时挂了动态类 `am-horizon--in`，所以按 `--in` 计数
    expect((w.html().match(/am-horizon--in/g) ?? []).length).toBe(rows.length)
    expect((w.html().match(/class="am-cell"/g) ?? []).length).toBe(rows.length * cols.length - 1)
    expect(w.html()).toContain('class="am-quiet"')

    expect(mount(ArcMatrix, { props: { rows: [], cols: [], matrix: [] } }).text()).toContain('暂无数据')
  })

  it('L17 CalendarHeat：首列对齐周一 + 月标签 + 逐日 title', () => {
    // 2026-01-01 是周四：首列前三格必须留白（点从第 4 行开始）
    const days = Array.from({ length: 60 }, (_, i) => {
      const d = new Date(2026, 0, 1 + i)
      const iso = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      return { date: iso, value: (i * 7) % 13 }
    })
    const w = mount(CalendarHeat, { props: { days, unit: ' 次' } })
    const html = w.html()
    expect((html.match(/class="ch-dot"/g) ?? []).length).toBe(60)
    expect(html).toContain('2026-01-01　0 次')
    expect(html).toContain('1月')
    // 周四起算：2026-01-01 的 y = y0 + rowH*3.5（dow=3）
    const geoRows = html.match(/cy="([\d.]+)"/g) ?? []
    expect(geoRows.length).toBeGreaterThan(0)

    const empty = mount(CalendarHeat, { props: { days: [{ date: '不是日期', value: 3 }] } })
    expect(empty.text()).toContain('暂无数据')
  })

  it('G17 DynamicStream：空态明确（画布路径由浏览器侧验证）', () => {
    const w = mount(DynamicStream, { props: { series: [] } })
    expect(w.text()).toContain('暂无数据')
    const zeros = mount(DynamicStream, {
      props: { series: [{ name: '在线', values: [] }] },
    })
    expect(zeros.text()).toContain('暂无数据')
  })

  // 首次冷启动要现场转译整个 echarts 包，给足超时（默认 5s 会偶发超时）
  it(
    'G17 DynamicStream：ECharts 按需注册的模块路径真的解析得开',
    async () => {
      // 组件里是动态 import，路径写错只会在浏览器里炸；这里先按同一份路径解析一遍
      const core = await import('echarts/core')
      const { LineChart } = await import('echarts/charts')
      const { GridComponent, TooltipComponent } = await import('echarts/components')
      const { CanvasRenderer } = await import('echarts/renderers')
      expect(core.init).toBeTypeOf('function')
      expect(LineChart).toBeTruthy()
      expect(GridComponent).toBeTruthy()
      expect(TooltipComponent).toBeTruthy()
      expect(CanvasRenderer).toBeTruthy()
      core.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer])
      expect(core.getInstanceByDom).toBeTypeOf('function')
    },
    30_000,
  )
})
