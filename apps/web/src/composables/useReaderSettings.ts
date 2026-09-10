/**
 * 阅读器 · 阅读设置（字号/行距/主题，localStorage 持久化）。
 * 抽到 composable 的原因：MobileReaderView 有 350 行门禁（fe-08）。
 * 主题值同时驱动 `.u-rd-views[data-theme]`（reader-uic.css 里的 --ur-theme-* 变量）。
 */
import { reactive } from 'vue'

export type ReaderTheme = 'paper' | 'cream' | 'night'

export interface ReaderSettings {
  theme: ReaderTheme
  fontSize: number
  lineHeight: number
}

function readTheme(): ReaderTheme {
  const raw = localStorage.getItem('vv_rd_theme')
  return raw === 'cream' || raw === 'night' ? raw : 'paper'
}

export function useReaderSettings() {
  const settings = reactive<ReaderSettings>({
    theme: readTheme(),
    fontSize: Number(localStorage.getItem('vv_rd_font') ?? 19),
    lineHeight: Number(localStorage.getItem('vv_rd_line') ?? 1.85),
  })

  function patchSettings(patch: Partial<ReaderSettings>): void {
    Object.assign(settings, patch)
    localStorage.setItem('vv_rd_theme', settings.theme)
    localStorage.setItem('vv_rd_font', String(settings.fontSize))
    localStorage.setItem('vv_rd_line', String(settings.lineHeight))
  }

  return { settings, patchSettings }
}
