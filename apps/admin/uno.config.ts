import { defineConfig, presetUno } from 'unocss'

import { consoleTheme } from './src/styles/tokens'

/**
 * UnoCSS（docs/50 §11.2）：布局工具类层——只管 padding/gap/flex/grid/文本，
 * 设计语义（色彩/圆角/阴影）统一走 `src/styles/tokens.css` 的 CSS 变量，
 * 组件样式交给 naive-ui themeOverrides（单一注入点）。
 * 与 `apps/web/uno.config.ts` 同构，便于两端口径对齐。
 */
export default defineConfig({
  presets: [presetUno()],
  theme: {
    colors: {
      ink: {
        DEFAULT: consoleTheme.ink,
        hover: consoleTheme.inkHover,
        sub: consoleTheme.sub,
        weak: consoleTheme.weak,
      },
      paper: {
        DEFAULT: consoleTheme.paper,
        grid: consoleTheme.paperGrid,
      },
      brand: {
        DEFAULT: consoleTheme.accent,
        soft: consoleTheme.accentSoft,
      },
    },
    borderRadius: {
      ctl: consoleTheme.rCtl,
      card: consoleTheme.rCard,
    },
  },
})
