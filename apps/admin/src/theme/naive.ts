import type { GlobalThemeOverrides } from 'naive-ui'

import { consoleTheme } from '@/styles/tokens'

/**
 * naive-ui 主题覆盖（docs/50 §11.1）——**全应用唯一注入点**（`App.vue`）。
 *
 * 两条口径：
 * 1. 品牌色 = 产品现行强调色 `#2f6bff`，**不是已退役的移动端绿 `#16A34A`**
 *    （`apps/web/src/styles/theme.ts` 仍用绿，控制台不跟随）；
 * 2. 圆角走控制台尺度（控件 8px），**按钮保持胶囊 999px** 作为品牌签名
 *    （docs/13:27「组件 8px / 卡片 12px / 胶囊 999px」）。
 *
 * naive-ui 由 primaryColor 自动派生 hover/pressed/suppl，故只需给主色；
 * 状态色仍显式给，避免与 --c-* 语义变量漂移。
 */
export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: consoleTheme.accent,
    primaryColorHover: '#4a7dff',
    primaryColorPressed: '#1f56e0',
    primaryColorSuppl: '#4a7dff',
    successColor: consoleTheme.success,
    warningColor: consoleTheme.warn,
    errorColor: consoleTheme.error,
    textColorBase: consoleTheme.ink,
    textColor1: consoleTheme.ink,
    textColor2: consoleTheme.sub,
    textColor3: consoleTheme.weak,
    borderColor: consoleTheme.track,
    dividerColor: consoleTheme.track,
    bodyColor: consoleTheme.paper,
    cardColor: consoleTheme.card,
    modalColor: consoleTheme.card,
    popoverColor: consoleTheme.card,
    tableColor: consoleTheme.card,
    tableHeaderColor: consoleTheme.paperGrid,
    borderRadius: consoleTheme.rCtl,
    borderRadiusSmall: '6px',
    fontFamily: consoleTheme.font,
    fontSize: '14px',
    fontWeightStrong: '600',
  },
  Button: {
    // 品牌签名：按钮恒为胶囊
    borderRadiusMedium: consoleTheme.rPill,
    borderRadiusLarge: consoleTheme.rPill,
    borderRadiusSmall: consoleTheme.rPill,
    fontWeight: '500',
    heightMedium: '36px',
  },
  Card: {
    borderRadius: consoleTheme.rCard,
  },
  DataTable: {
    borderRadius: consoleTheme.rCard,
    thFontWeight: '600',
    thColor: consoleTheme.paperGrid,
    tdColorHover: '#f7f6f3',
  },
  Input: {
    borderRadius: consoleTheme.rCtl,
    heightMedium: '36px',
  },
  Menu: {
    borderRadius: consoleTheme.rCtl,
    itemHeight: '38px',
  },
  Dialog: {
    borderRadius: consoleTheme.rCard,
  },
  Tag: {
    borderRadius: consoleTheme.rPill,
  },
}
