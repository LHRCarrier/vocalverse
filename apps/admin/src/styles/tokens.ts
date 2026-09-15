/**
 * VV Console 设计 token（docs/50 §11.2）。
 *
 * 来源与理由：
 * - 色彩**继承产品 `u-*` 纸墨**（`apps/web/src/styles/mobile-uic.css:14-61`，即用户真实看到的形态）；
 * - 圆角**降级到控制台尺度**（docs/13:27「组件 8px / 卡片 12px / 胶囊 999px」的控制台精神）；
 * - 与 lieflat Mono 的关系：Mono 的 `INK #1C1C1A` 与产品 `ink #1c1c1a` **完全相同**，
 *   `PAPER #F0EFEB` 与产品 `paper #f5f4f1` 同族 —— 这让「UI 与图表」视觉上天然一家人。
 *
 * 三层分工（硬规则）：
 *   primitive（本文件 / tokens.css 的 `--vv-*`）  →  semantic（`--c-*`）  →  component（`.c-*` 类）
 * 组件里**禁止**直接引用 `--vv-*`；只准用 `--c-*`。
 */

/** primitive：从产品继承，不在组件里直接使用 */
export const consoleTheme = {
  // 墨与纸
  ink: '#1c1c1a',
  inkHover: '#333330',
  sub: '#6f6f6a',
  weak: '#a6a6a0',
  paper: '#f5f4f1',
  paperGrid: '#eae8e3',
  card: '#ffffff',
  track: '#eceae5',
  trackHover: '#e2e0da',

  // 强调与状态
  accent: '#2f6bff',
  accentSoft: '#e8edff',
  success: '#16a34a',
  successSoft: '#dcfce7',
  warn: '#b45309',
  warnSoft: '#fff4d6',
  error: '#dc2626',
  errorSoft: '#fee2e2',

  // 形状
  rCtl: '8px',
  rCard: '16px',
  rPill: '999px',
  shadow1: '0 2px 8px rgba(28,28,26,.08)',
  shadow2: '0 8px 24px rgba(28,28,26,.06)',

  // 字体：仓库**无任何字体真实加载**（Nunito 被引用但无 @font-face），
  // 故沿用系统栈，不引 CDN 字体（内网/离线可用；docs/50 §11.1）
  font: "'Segoe UI','Microsoft YaHei UI','Microsoft YaHei',sans-serif",
  fontMono: "'JetBrains Mono','Cascadia Mono',Consolas,'Courier New',monospace",

  // 动效（仅 transform/opacity/box-shadow）
  tPress: '60ms',
  tMicro: '150ms',
  tStd: '220ms',
  easeOut: 'cubic-bezier(.22,1,.36,1)',
} as const

/** lieflat Mono 图表色彩系统（移植自 skill `mono-tokens.js`，docs/50 §12.1） */
export const mono = {
  INK: '#1C1C1A',
  PAPER: '#F0EFEB',
  MUTED: '#8F8E88',
  FAINT: '#C6C5BF',
  GRID: '#DEDDD6',
  /** 7 级灰阶：多系列按重要性从黑到浅分配（明度即数据） */
  L: ['#1C1C1A', '#4A4944', '#6A6963', '#8F8E88', '#B0AFA9', '#C6C5BF', '#D8D7D1'],
  /** 5 级简版（少系列场景） */
  LAD: ['#1C1C1A', '#4A4944', '#8F8E88', '#B0AFA9', '#D8D7D1'],
  DARK: {
    bg: '#1C1C1A',
    ink: '#F0EFEB',
    muted: '#8F8E88',
    faint: '#55554F',
    grid: '#2E2D29',
    gridSoft: '#2A2925',
    ladder: ['#F0EFEB', '#DCDAD2', '#C9C7BD', '#B3B0A4', '#8F8E88', '#6A6963', '#4A4944'],
  },
  /** 字号（SKILL §2：SVG 最小字号 半宽 6.5px / 通栏 5.5px） */
  FONT: {
    title: { size: 16.5, weight: 700, spacing: '-.02em' },
    titleBig: { size: 19, weight: 700, spacing: '-.02em' },
    sub: { size: 11.5, weight: 400 },
    src: { size: 9.5, weight: 500, spacing: '.08em' },
    value: 800,
    axis: { size: 9.5, weight: 600 },
    minHalf: 6.5,
    minWide: 5.5,
  },
  /** 形状（SKILL §3） */
  SHAPE: { cardRadius: 24, barRadius: 99, tooltipRadius: 12 },
  /** 动画性格（SKILL §4：快进快停，不弹跳） */
  MOTION: {
    enter: 900,
    enterSlow: 1200,
    easing: 'quarticOut',
    staggerDot: 12,
    staggerBar: 100,
  },
  /** Tooltip：浅卡黑底纸字 */
  tipLight: {
    backgroundColor: '#1C1C1A',
    borderWidth: 0,
    padding: [10, 14],
    textStyle: { color: '#F0EFEB', fontSize: 12 },
  },
} as const

export type ConsoleTheme = typeof consoleTheme
