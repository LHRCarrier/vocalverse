<script setup lang="ts">
/**
 * 移动端 · 我的学习（2026-09-09 组长与组员讨论拍板 v4：重新设计，当前设计作废）
 * 定位修正：学习主页 = 「我的学习」画像总览——一句话结论 + 微识别 + 一张信息图 + 模块列表，
 * 数据细节下沉到模块详情页（/m/learn/:module，手机小屏不挤一页）。
 * 结构（X 式）：
 *   ① 欢迎定位行：Hi 昵称 + 一句话画像（一眼明白的锚点）
 *   ② 识别行（轻量）：LV3 chip + 70/500 XP + 金条 + 🔥12天（不做大卡）
 *   ③ 学习热力图（信息图 · 保留：好看且用户可读；只图 + 右下 +XP）
 *   ④ 模块列表（4 行：我的单词 / 社区足迹 / 我的发音 / 练习情况——每行一句摘要，要细节点进去）
 * 数据口径：progress/auth 真实；热力图/摘要演示帧（M3 接 attempts/埋点聚合）。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useProgressStore } from '@/stores/progress'
import '@/styles/mobile-uic.css'

const progress = useProgressStore()
const auth = useAuthStore()
const router = useRouter()

const displayName = computed(() => auth.me?.nickname ?? auth.me?.username ?? '学习者')

/* ---------- 一句话画像（演示帧 · M3 接 learner.py 聚合生成） ---------- */
const profileLine = '你本周练了 6 次，发音进步 +4 分——表达越来越自然了。'

/* ---------- 识别行 ---------- */
const streak = 12 // 连续天数（演示；M3 打卡聚合）

/* ---------- 学习热力图（12 周 × 7 天 · 自绘零依赖 · 演示确定性数据） ---------- */
type HeatCell = { date: Date; level: 0 | 1 | 2 | 3; xp: number }

/** 确定性伪随机（同一天恒同值）——演示帧; M3 换 attempts 聚合 */
function dayLevel(d: Date): { level: 0 | 1 | 2 | 3; xp: number } {
  const today = new Date()
  if (d.getTime() > today.getTime()) return { level: 0, xp: 0 } // 未来日期不画数据
  if (d.toDateString() === today.toDateString()) return { level: 3, xp: 75 }
  const h = (d.getFullYear() * 372 + (d.getMonth() + 1) * 31 + d.getDate() * 7) % 10
  if (h < 5) return { level: 0, xp: 0 }
  if (h < 7) return { level: 1, xp: 25 }
  if (h < 9) return { level: 2, xp: 50 }
  return { level: 3, xp: 75 }
}

/** 近 12 周网格（列=周 · 行=周一~周日）；今天位于末列 | [演示帧] */
function buildWeeks(weeks: number): HeatCell[][] {
  const today = new Date()
  const monday = new Date(today)
  monday.setDate(today.getDate() - ((today.getDay() + 6) % 7))
  const start = new Date(monday)
  start.setDate(monday.getDate() - (weeks - 1) * 7)
  const cols: HeatCell[][] = []
  for (let w = 0; w < weeks; w++) {
    const col: HeatCell[] = []
    for (let d = 0; d < 7; d++) {
      const date = new Date(start)
      date.setDate(start.getDate() + w * 7 + d)
      const { level, xp } = dayLevel(date)
      col.push({ date, level, xp })
    }
    cols.push(col)
  }
  return cols
}

const heatCells: HeatCell[] = buildWeeks(12).flat()
const isToday = (c: HeatCell) => c.date.toDateString() === new Date().toDateString()
const isFuture = (c: HeatCell) => c.date.getTime() > new Date().getTime()
const dateKey = (c: HeatCell) =>
  `${c.date.getFullYear()}-${String(c.date.getMonth() + 1).padStart(2, '0')}-${String(c.date.getDate()).padStart(2, '0')}`

/** 选中格 → 右下角显示该日经验（演示帧详情；默认今天） */
const selected = ref<HeatCell>(heatCells.find(isToday) ?? heatCells[heatCells.length - 2])
function pick(cell: HeatCell) {
  selected.value = cell
}
const selectedXpLabel = computed(() =>
  isFuture(selected.value) || selected.value.level === 0 ? '未练习' : `+${selected.value.xp} XP`,
)

/* ---------- 模块列表（每行 = 图标块 + 名称 + 一句摘要 + 箭头；详情下沉到 /m/learn/:module） ---------- */
const modules = [
  {
    key: 'words',
    icon: 'bookmark',
    tint: 'var(--u-dark-green)',
    title: '我的单词',
    summary: '阅读查词即收 · 生词本',
    path: '/m/vocab',
  },
  {
    key: 'shelf',
    icon: 'book',
    tint: 'var(--u-dark-navy)',
    title: '书房',
    summary: '英文小说 · 查词 · 听书',
    path: '/m/bookshelf',
  },
  {
    key: 'community',
    icon: 'heart',
    tint: 'var(--u-dark-navy)',
    title: '社区足迹',
    summary: '常逛英语新闻 · 点赞 8 帖',
    path: '/m/learn/community',
  },
  {
    key: 'speaking',
    icon: 'mic',
    tint: 'var(--u-dark-teal)',
    title: '我的发音',
    summary: '发音 82 · 流利 78 · 语法 85',
    path: '/m/learn/speaking',
  },
  {
    key: 'practice',
    icon: 'flame',
    tint: 'var(--u-dark-purple)',
    title: '练习情况',
    summary: '场景掌握 5/8 · 本周 86 分钟',
    path: '/m/learn/practice',
  },
] as const

function openModule(path: string) {
  void router.push(path)
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="学习" />

    <div class="u-learn">
      <!-- ① 欢迎定位行（画像一句话 · 一眼明白的锚点） -->
      <section class="u-learn-greet">
        <p class="u-learn-greet__hi">Hi，{{ displayName }}</p>
        <p class="u-learn-greet__line">{{ profileLine }}</p>
      </section>

      <!-- ② 识别行（轻量：LV chip + XP 条 + 连续天数） -->
      <section class="u-learn-id">
        <b class="u-learn-id__lv">{{ progress.lvLabel }}</b>
        <span class="u-learn-id__xp">{{ progress.xpInLevel }} / {{ progress.nextXp ?? '—' }} XP</span>
        <span class="u-learn-id__bar" role="progressbar" :aria-valuenow="progress.progressPct" aria-valuemin="0" aria-valuemax="100">
          <span class="u-learn-id__fill" :style="{ width: `${progress.progressPct}%` }" />
        </span>
        <span class="u-learn-id__streak">
          <MobileIcon name="flame" :size="15" />{{ streak }} 天
        </span>
      </section>

      <!-- ③ 学习热力图（信息图 · 只图 + 右下角经验） -->
      <section class="u-learn-heat" aria-label="学习热力图">
        <div class="u-learn-heat__grid">
          <button
            v-for="cell in heatCells"
            :key="dateKey(cell)"
            type="button"
            class="u-learn-heat__cell"
            :class="[
              `lv${cell.level}`,
              { today: isToday(cell), future: isFuture(cell), picked: dateKey(cell) === dateKey(selected) },
            ]"
            :disabled="isFuture(cell)"
            :aria-label="`${dateKey(cell)} · ${isFuture(cell) ? '还没到' : cell.level === 0 ? '未练习' : `+${cell.xp} XP`}`"
            @click="pick(cell)"
          />
        </div>
        <div class="u-learn-heat__xp" aria-live="polite">{{ selectedXpLabel }}</div>
      </section>

      <!-- ④ 模块列表（一句话即结论，细节进详情页） -->
      <section class="u-learn-modules" aria-label="我的学习模块">
        <button
          v-for="m in modules"
          :key="m.key"
          type="button"
          class="u-learn-module"
          @click="openModule(m.path)"
        >
          <span class="u-learn-module__icon" :style="{ background: m.tint }">
            <MobileIcon :name="m.icon" :size="18" />
          </span>
          <span class="u-learn-module__body">
            <strong class="u-learn-module__title">{{ m.title }}</strong>
            <span class="u-learn-module__summary">{{ m.summary }}</span>
          </span>
          <MobileIcon name="chevron" :size="16" class="u-learn-module__go" />
        </button>
      </section>

      <p class="u-learn-foot-note">热力图/摘要为演示帧，M3 接入 attempts 与埋点聚合。</p>
    </div>
  </div>
</template>
