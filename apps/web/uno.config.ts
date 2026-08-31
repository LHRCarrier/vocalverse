import { defineConfig, presetUno } from 'unocss'

import { tokens } from './src/styles/tokens'

/**
 * UnoCSS（docs/13）：布局工具类层——只管 padding/gap/flex/文本等，
 * 设计语义（色彩/圆角）统一走 tokens；组件样式全交 naive-ui themeOverrides。
 */
export default defineConfig({
  presets: [presetUno()],
  theme: {
    colors: {
      brand: {
        DEFAULT: tokens.colors.brand,
        light: tokens.colors.brandLight,
        deep: tokens.colors.brandDeep,
      },
      accent: { DEFAULT: tokens.colors.accent },
      score: tokens.colors.score,
    },
  },
})
