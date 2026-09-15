/**
 * 学习进度 store（2026-09-05 组长拍板：Duolingo 式等级制度——完成练习 +XP → 升级 LV）
 * 联动：学习页画像卡（中心焦点）/ 我的档案卡 / 账户抽屉 / 社区帖子卡 / 私信列表·会话头——同一份 level。
 * 演示级：xp 存 localStorage（vv_xp，初始 320 演示）；真实经验规则（练习时长/评分加权）M3 后端化。
 * 等级表（演示）：LV1 英语新手 0 · LV2 口语学徒 100 · LV3 对话能手 250 · LV4 表达达人 500 · LV5 流利大师 900。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { useUiStore } from '@/stores/ui'

const XP_KEY = 'vv_xp'
const INIT_XP = 320 // 演示初始（LV3 · 对话能手）

const LEVELS: Array<{ level: number; title: string; xp: number }> = [
  { level: 1, title: '英语新手', xp: 0 },
  { level: 2, title: '口语学徒', xp: 100 },
  { level: 3, title: '对话能手', xp: 250 },
  { level: 4, title: '表达达人', xp: 500 },
  { level: 5, title: '流利大师', xp: 900 },
]

export const useProgressStore = defineStore('progress', () => {
  const xp = ref(Number(localStorage.getItem(XP_KEY) ?? INIT_XP))

  function persist() {
    localStorage.setItem(XP_KEY, String(xp.value))
  }

  /** 当前等级信息：level / title / 本级起点 base / 下级门槛 next（null = 满级） */
  const info = computed(() => {
    let cur = LEVELS[0]
    let next: (typeof LEVELS)[number] | null = null
    for (const l of LEVELS) {
      if (xp.value >= l.xp) cur = l
      else {
        next = l
        break
      }
    }
    return { level: cur.level, title: cur.title, base: cur.xp, next: next ? next.xp : null }
  })

  /** LV 展示串：LV3 */
  const lvLabel = computed(() => `LV${info.value.level}`)

  /** 本级进度百分比（满级 = 100） */
  const progressPct = computed(() => {
    const { base, next } = info.value
    if (next == null) return 100
    return Math.min(100, Math.round(((xp.value - base) / (next - base)) * 100))
  })

  /** 本级已有 XP */
  const xpInLevel = computed(() => xp.value - info.value.base)

  /** 下一级门槛（null = 满级） */
  const nextXp = computed(() => info.value.next)

  function addXp(n: number) {
    xp.value += n
    persist()
    useUiStore().showToast(`+${n} XP`)
  }

  return { xp, info, lvLabel, progressPct, xpInLevel, nextXp, addXp }
})
