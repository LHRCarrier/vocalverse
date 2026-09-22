/**
 * 打卡 store（2026-09-21 改版：用户手动打卡）
 *
 * - **不再由练习自动触发**：打卡页点「打卡」→ Python 聚合当日练习并物化当日卡（幂等）；
 * - **状态真源** = 我的打卡卡（`fetchFeed(mine=true)` 里的 `kind==='checkin'` 行）：
 *   今日是否已打卡、连续天数都从真实卡片算，不写死、不臆造；
 * - 「今天」按**用户本地日期**（与打卡页/卡面 checkinDate 同口径）。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { manualCheckin } from '@/api/checkin'
import { fetchFeed } from '@/api/community'
import { useUiStore } from '@/stores/ui'

import type { CommunityPostView } from '@/types/community'

/** 本地日期键 YYYY-MM-DD（避免 toISOString 的 UTC 偏移把凌晨算成昨天）。 */
export function localDateKey(d: Date = new Date()): string {
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${month}-${day}`
}

/**
 * 连续打卡天数：今天已打卡则从今天起数；今天还没打卡则从昨天起数（当天未打卡不算断签）。
 */
export function computeStreak(dates: Iterable<string>, today: string = localDateKey()): number {
  const set = new Set(dates)
  const cursor = new Date(`${today}T00:00:00`)
  if (!set.has(today)) cursor.setDate(cursor.getDate() - 1)
  let n = 0
  while (set.has(localDateKey(cursor))) {
    n += 1
    cursor.setDate(cursor.getDate() - 1)
  }
  return n
}

export const useCheckinStore = defineStore('checkin', () => {
  const ui = useUiStore()
  const loading = ref(false)
  const submitting = ref(false)
  const loaded = ref(false)
  const failed = ref(false)
  const cards = ref<CommunityPostView[]>([])
  const today = ref(localDateKey())

  const checkedIn = computed(() => cards.value.some((c) => c.checkinDate === today.value))
  const streak = computed(() =>
    computeStreak(
      cards.value.map((c) => c.checkinDate).filter((d): d is string => !!d),
      today.value,
    ),
  )

  /** 拉我的打卡卡（mine=true）；失败静默（打卡提示不该因网络抖动误报「未打卡」）。 */
  async function refresh(force = false) {
    if (loading.value || (loaded.value && !force)) return
    loading.value = true
    today.value = localDateKey()
    try {
      const page = await fetchFeed(null, null, 30, undefined, true)
      cards.value = page.items.filter((p) => p.kind === 'checkin')
      loaded.value = true
      failed.value = false
    } catch {
      failed.value = true
    } finally {
      loading.value = false
    }
  }

  async function checkIn(): Promise<boolean> {
    if (submitting.value) return false
    submitting.value = true
    try {
      const result = await manualCheckin(localDateKey())
      await refresh(true)
      const overall = result.overall
      ui.showToast(
        result.practiceCount > 0 && overall != null
          ? `打卡成功 · 今日综合分 ${overall.toFixed(0)}`
          : '打卡成功',
      )
      return true
    } catch (e) {
      ui.showToast(e instanceof Error ? e.message : '打卡失败，请稍后重试')
      return false
    } finally {
      submitting.value = false
    }
  }

  return { loading, submitting, loaded, failed, cards, today, checkedIn, streak, refresh, checkIn }
})
