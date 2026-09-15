/**
 * 批注色板 · 单一真源（2026-09-09）
 *
 * 为什么单独成文件：色板原先在 `MobileAnnotationSheet.vue` / `MobileAnnotationNoteSheet.vue` /
 * `MobileReaderSelectionBar.vue` 各抄一份，而暗黑模式对比度门禁
 * （`src/styles/__tests__/reader-annotation-contrast.test.ts`）要从源码里抠色板算对比度——
 * 拷贝一多，改了颜色却漏改一处，门禁就会「静默失去覆盖」。这里收成一份。
 *
 * 颜色是**不可信输入**（来自后端 `annotations.color`，任意字符串）：
 * `safeAnnColor` 只放行色板内的 6 位十六进制，其余一律回退默认色。
 * 两条收益：
 *   ① 杜绝 CSS 注入/非法值让 `--ur-ann-color` 整条声明失效（批注底色变透明）；
 *   ② 对比度门禁的覆盖范围 = 实际可能渲染的颜色集合（见门禁用例的最坏色矩阵）。
 */

export interface AnnotationColor {
  id: string
  value: string
  label: string
}

/** 批注色板（顺序即 UI 展示顺序；默认色 = 首色） */
export const ANNOTATION_COLORS: readonly AnnotationColor[] = [
  { id: 'yellow', value: '#fde68a', label: '黄' },
  { id: 'green', value: '#bbf7d0', label: '绿' },
  { id: 'blue', value: '#bfdbfe', label: '蓝' },
  { id: 'pink', value: '#fbcfe8', label: '粉' },
]

/** 批注色缺省值（色板首色） */
export const ANN_FALLBACK_COLOR = ANNOTATION_COLORS[0].value

/** 色板值的集合（小写归一，用于白名单判定） */
const ALLOWED = new Set(ANNOTATION_COLORS.map((c) => c.value.toLowerCase()))

/**
 * 批注色白名单：色板内 → 原样；其余（空/非字符串/rgb()/命名色/注入串/色板外色）→ 默认色。
 * 纯函数（无 DOM 依赖），供渲染层与单测共用。
 */
export function safeAnnColor(color?: string | null): string {
  if (typeof color !== 'string') return ANN_FALLBACK_COLOR
  const v = color.trim().toLowerCase()
  return ALLOWED.has(v) ? v : ANN_FALLBACK_COLOR
}
