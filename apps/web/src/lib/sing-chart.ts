/**
 * D3 唱歌对齐图（docs/13 已定案：D3 仅用于唱歌逐句音准/对齐图，M3）：
 * - x = 时间轴（ms）；y = 半音音高（midi，用户曲线按参考旋律时间轴对齐）；
 * - 参考旋律线（song lines[].pitch_ref.f0s，逐帧折线）；
 * - 用户曲线（result.lines[].user_f0 逐帧折线，按评分对齐 offset 时间轴平移）；
 * - 逐句音准分柱（顶部条带，色彩映射 95 绿 → <40 红）。
 *
 * 纯函数渲染（不持内部状态）：每次调用清空并重绘；容器尺寸自适应 width。
 */

import * as d3 from 'd3'

import type { SingAttemptResult, SongDetail, SongLine } from '@/api/sing'

export interface SingChartOptions {
  /** 曲线高度（默认 120px） */
  height?: number
  /** 评分时间偏置（result.alignment.offset_ms，用户曲线平移量） */
  alignOffsetMs?: number
}

function f0ToMidi(f0: number): number {
  return f0 > 0 ? 69 + 12 * Math.log2(f0 / 440) : NaN
}

/** 把参考句的 f0s 帧序列化为 [{t, midi}]（相对句起点） */
function refPoints(line: SongLine): { t: number; midi: number }[] {
  const hop = 32 // hop 512 @16k = 32ms（docs/06 §9.4）
  return (line.pitch_ref?.f0s ?? [])
    .map((f0, i) => ({ t: line.start_ms + i * hop, midi: f0ToMidi(f0) }))
    .filter((p) => Number.isFinite(p.midi))
}

export function renderSingChart(
  container: HTMLElement,
  detail: SongDetail,
  result: SingAttemptResult,
  _opts: SingChartOptions = {},
): void {
  const width = Math.max(container.clientWidth || 320, 320)
  const height = _opts.height ?? 130
  const margin = { top: 18, right: 8, bottom: 20, left: 34 }
  const innerH = height - margin.top - margin.bottom

  const alignOffset = _opts.alignOffsetMs ?? (result.alignment?.offset_ms ?? 0)

  d3.select(container).selectAll('*').remove()
  const svg = d3
    .select(container)
    .append('svg')
    .attr('viewBox', `0 0 ${width} ${height}`)
    .attr('role', 'img')
    .attr('aria-label', '参考旋律与跟唱音高对齐图')

  // 时间范围（参考旋律曲长）
  const tMax = Math.max(1, ...detail.lines.map((l) => l.end_ms ?? l.start_ms + 1000))
  const x = d3.scaleLinear().domain([0, tMax]).range([margin.left, width - margin.right])
  const y = d3
    .scaleLinear()
    .domain([0, 90]) // midi 可视化范围（C2~D6 附近）
    .range([margin.top + innerH, margin.top])

  // 参考旋律线（逐句拼接）
  const refAll = detail.lines.flatMap(refPoints)
  if (refAll.length > 1) {
    svg
      .append('path')
      .datum(refAll)
      .attr('fill', 'none')
      .attr('stroke', '#3a8fb7')
      .attr('stroke-width', 1.6)
      .attr('opacity', 0.9)
      .attr('d', d3.line<{ t: number; midi: number }>().x((p) => x(p.t)).y((p) => y(p.midi)))
  }

  // 用户曲线（逐句用户 F0，按对齐偏置换算 → 参考时钟）
  const userAll = result.lines.flatMap((l) =>
    (l.user_f0 ?? []).map(([t, f0]) => ({
      t: t + alignOffset,
      midi: f0ToMidi(f0),
    })),
  )
  if (userAll.length > 1) {
    svg
      .append('path')
      .datum(userAll)
      .attr('fill', 'none')
      .attr('stroke', '#e07a3f')
      .attr('stroke-width', 1.4)
      .attr('stroke-dasharray', '4 2')
      .attr('opacity', 0.9)
      .attr('d', d3.line<{ t: number; midi: number }>().x((p) => x(p.t)).y((p) => y(p.midi)))
  }

  // 逐句音准分柱（顶部条带：绿 95 → 红 <40）
  for (const l of result.lines) {
    if (l.skipped) continue
    const score = l.pitch_score ?? l.pron_score ?? 0
    const color = d3.interpolateRdYlGn(Math.min(Math.max((score - 30) / 65, 0), 1))
    svg
      .append('rect')
      .attr('x', x(l.start_ms))
      .attr('y', margin.top - 6)
      .attr('width', Math.max(2, x(l.end_ms ?? l.start_ms + 1000) - x(l.start_ms)))
      .attr('height', 5)
      .attr('fill', color)
      .attr('opacity', 0.85)
  }

  // 坐标轴
  const xAxis = d3.axisBottom(x).ticks(6).tickFormat((d) => `${Math.round(Number(d) / 1000)}s`)
  svg
    .append('g')
    .attr('transform', `translate(0, ${margin.top + innerH})`)
    .call(xAxis)
    .style('font-size', 10)
  const yAxis = d3
    .axisLeft(y)
    .ticks(4)
    .tickFormat((d) => noteName(Number(d)))
  svg.append('g').attr('transform', `translate(${margin.left}, 0)`).call(yAxis).style('font-size', 10)
}

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

function noteName(midi: number): string {
  if (!Number.isFinite(midi)) return ''
  return `${NOTE_NAMES[Math.round(midi) % 12]}${Math.floor(midi / 12) - 1}`
}
