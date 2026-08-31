import type { GlobalThemeOverrides } from 'naive-ui'

import { tokens } from './tokens'

/** naive-ui 主题覆盖（docs/13）：全部由 tokens 驱动，组件级定制仅做品牌圆角/胶囊化。 */
export const themeOverrides: GlobalThemeOverrides = {
  common: {
    primaryColor: tokens.colors.brand,
    primaryColorHover: tokens.colors.brandLight,
    primaryColorPressed: tokens.colors.brandDeep,
    primaryColorSuppl: tokens.colors.brandLight,
    borderRadius: tokens.radius.base,
    fontFamily: tokens.fontFamily,
    textColorBase: tokens.colors.text,
  },
  Button: {
    borderRadiusMedium: tokens.radius.pill,
    borderRadiusLarge: tokens.radius.pill,
  },
}
