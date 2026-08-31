/**
 * 设计 token（docs/13 唯一来源）——B 多邻国活力方向（2026-08-31 拍板）。
 *
 * 纪律：css 写 hex 一律引用这里（或 uno.config theme 映射）；改风格只改本文件 +
 * docs/13。文字级绿色用 brandDeep（#15803D，AA 对比度）；brand 用于按钮底/图形。
 */
export const tokens = {
  colors: {
    brand: '#16A34A', // 主色（按钮底/品牌图形）
    brandLight: '#22C55E', // hover/强调图形
    brandDeep: '#15803D', // 文字级绿色（AA）
    accent: '#FACC15', // 柠檬黄（徽章/激励，配深色文字）
    score: '#FB923C', // 评分/高亮橙
    success: '#22C55E',
    error: '#EF4444',
    info: '#0EA5E9',
    bg: '#F9FAFB',
    bgBrand: '#ECFDF5', // 品牌浅底（区块/渐变起始）
    card: '#FFFFFF',
    text: '#101828',
    textSecondary: '#667085',
    border: '#E5E7EB',
  },
  radius: {
    base: '8px',
    card: '12px',
    pill: '999px',
  },
  spacing: [4, 8, 12, 16, 24, 32],
  /** Nunito 为可选外网字体（演示机器断网时回退系统栈，不阻塞） */
  fontFamily:
    "'Nunito', ui-rounded, system-ui, -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif",
} as const
