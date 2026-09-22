/**
 * 酒馆 · 动作面板 chip 行的溢出几何（docs/57 N7：溢出提示只在真的溢出侧出现）。
 *
 * 纯函数（组件文件守 fe-08 行数上限，也便于单测直接喂几何值）。
 */
export interface RowScrollState {
  /** 内容宽于视口（有 chip 被藏住） */
  overflowing: boolean
  /** 还能向左滑（左侧有被藏的内容） */
  fadeStart: boolean
  /** 还能向右滑（右侧有被藏的内容） */
  fadeEnd: boolean
}

export function computeRowScrollState(el: {
  scrollLeft: number
  scrollWidth: number
  clientWidth: number
}): RowScrollState {
  const max = Math.max(0, el.scrollWidth - el.clientWidth)
  const overflowing = max > 1
  return {
    overflowing,
    fadeStart: overflowing && el.scrollLeft > 1,
    fadeEnd: overflowing && el.scrollLeft < max - 1,
  }
}
