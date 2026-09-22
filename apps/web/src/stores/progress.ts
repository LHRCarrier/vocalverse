/**
 * 学习进度 store（2026-09-05 组长拍板：Duolingo 式等级制度——完成练习 +XP → 升级 LV）
 * 联动：学习页画像卡（中心焦点）/ 我的档案卡 / 账户抽屉 / 社区帖子卡 / 私信列表·会话头——同一份 level。
 *
 * 2026-09-21（docs/53 P5 ③）：XP/等级**由服务端计算**（`GET /api/v1/stats/progress`，
 * 规则见 Python `app/insight/xp.py`）——本地不再写死初始 320 XP 与升级表，localStorage
 * 只作冷启动首屏缓存（服务端返回后覆盖）；练习/对话完成后调 `refresh()` 重拉。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { fetchProgressSummary } from '@/api/stats'

const CACHE_KEY = 'vv_progress'

interface CachedProgress {
  xp: number
  level: number
  title: string
  base: number
  next: number | null
}

/** 冷启动缓存（整组存，避免 xp 与等级不一致；旧 `vv_xp` 键废弃不再读） */
function readCache(): CachedProgress | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as CachedProgress
    return typeof parsed?.xp === 'number' ? parsed : null
  } catch {
    return null
  }
}

export const useProgressStore = defineStore('progress', () => {
  const cached = readCache()
  const xp = ref(cached?.xp ?? 0)
  const level = ref(cached?.level ?? 1)
  const title = ref(cached?.title ?? '英语新手')
  const base = ref(cached?.base ?? 0)
  /* 快照整组恢复（`next: null` = 满级，不能被 ?? 回退成 100） */
  const next = ref<number | null>(cached ? cached.next : 100)

  async function refresh() {
    try {
      const s = await fetchProgressSummary()
      xp.value = s.xp
      level.value = s.level
      title.value = s.title
      base.value = s.base
      next.value = s.next
      const snapshot: CachedProgress = {
        xp: s.xp,
        level: s.level,
        title: s.title,
        base: s.base,
        next: s.next,
      }
      localStorage.setItem(CACHE_KEY, JSON.stringify(snapshot))
    } catch {
      /* 非关键路径：失败保留缓存值（离线仍可展示上次等级） */
    }
  }

  /** 当前等级信息：level / title / 本级起点 base / 下级门槛 next（null = 满级） */
  const info = computed(() => ({ level: level.value, title: title.value, base: base.value, next: next.value }))

  /** LV 展示串：LV3 */
  const lvLabel = computed(() => `LV${level.value}`)

  /** 本级进度百分比（满级 = 100） */
  const progressPct = computed(() => {
    const nxt = next.value
    if (nxt == null) return 100
    const span = nxt - base.value
    if (span <= 0) return 0
    return Math.min(100, Math.max(0, Math.round(((xp.value - base.value) / span) * 100)))
  })

  /** 本级已有 XP */
  const xpInLevel = computed(() => Math.max(0, xp.value - base.value))

  /** 下一级门槛（null = 满级） */
  const nextXp = computed(() => next.value)

  return { xp, info, lvLabel, progressPct, xpInLevel, nextXp, refresh }
})
