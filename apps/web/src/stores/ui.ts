/**
 * 全局 UI store（2026-09-05：账户抽屉全局化 + 全局 toast 统一）
 * - drawerOpen：App 级挂载 MobileAccountDrawer（任意页面点头像可开）；
 * - toastText：App 级挂载 u-toast（各页不再自建 toast）。
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const drawerOpen = ref(false)
  const toastText = ref('')
  let toastTimer: ReturnType<typeof setTimeout> | null = null

  function openDrawer() {
    drawerOpen.value = true
  }

  function closeDrawer() {
    drawerOpen.value = false
  }

  function showToast(msg: string) {
    toastText.value = msg
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => {
      toastText.value = ''
    }, 2200)
  }

  return { drawerOpen, toastText, openDrawer, closeDrawer, showToast }
})
