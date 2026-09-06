<script setup lang="ts">
/**
 * 移动端 · 学习（2026-09-09 组长反馈 v2：卡片太多像拼凑 → 参考社区页高密度合并为 3 卡；
 * 顶栏头像本页去掉（画像页 LV 徽章已是身份焦点）；热力图只留图 + 右下角经验）
 * 结构：
 *   卡 1 画像主卡（身份行：LV 徽章+等级+XP 条+双数字 ｜ 分割线 ｜ 今日四数）
 *   卡 2 学习热力图（12 周 × 7 天填满 · 绿阶 · 今天蓝框 · 点格 → 右下角 +XP）
 *   卡 3 能力画像（流利度趋势 7 天柱 + 场景掌握度 8 条 + 薄弱点 chips + AI 一句话）
 * 数据口径：progress store 真实 XP/LV；其余演示帧，M3 换 attempts/词级真实聚合（docs/36）。
 */
import { computed, ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useProgressStore } from '@/stores/progress'
import '@/styles/mobile-uic.css'

const progress = useProgressStore()

/* ---------- 今日四数（演示帧 · M3 打卡/练习聚合替换） ---------- */
const todayTurns = 3
const todayMinutes = 42
const weekTurns = 15
const streak = 12 // 连续天数（演示；M3 打卡聚合）
const weekMinutes = 86 // 本周时长（演示）

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

/** 近 12 周网格（列=周 · 行=周一~周日）；今天位于末列 |
 *  [演示帧] M3 换 attempts 打卡聚合 */
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

/* ---------- 流利度趋势（最近 7 天·演示；M3 换 attempts 平均分） ---------- */
const weekTrend = [72, 75, 71, 80, 82, 86, 90]
const trendAvg = Math.round(weekTrend.reduce((a, b) => a + b, 0) / weekTrend.length)
/** 分数 → 绿阶（成绩语义，与热力图同族）：≥85 深绿 / ≥78 绿 / 其余浅绿 */
function trendTone(v: number) {
  return v >= 85 ? 'deep' : v >= 78 ? 'mid' : 'soft'
}

/* ---------- 场景掌握度（演示；M3 换 user_corpus_mastery 聚合） ---------- */
const scenes = [
  { name: '咖啡馆 · 点单', score: 78, diff: '入门' },
  { name: '咖啡馆 · 订单沟通', score: 54, diff: '进阶' },
  { name: '机场 · 值机出行', score: 82, diff: '入门' },
  { name: '机场 · 航班变动', score: 47, diff: '进阶' },
  { name: '面试 · 自我介绍', score: 85, diff: '入门' },
  { name: '面试 · 深挖追问', score: 38, diff: '进阶' },
  { name: '图书馆 · 借阅', score: 70, diff: '入门' },
  { name: '图书馆 · 学业交流', score: 61, diff: '进阶' },
] as const
/** 强度条色档：≥80 绿 / ≥60 黄 / <60 红（语义色 = 信息） */
function band(score: number) {
  return score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low'
}

/* ---------- 薄弱点速览（演示帧 · M3 讯飞词级数据替换） ---------- */
const weakPhonemes = ['/θ/', '/ð/', '/r/']
const weakWords = ['interesting', 'comfortable', 'world']

/* ---------- AI 一句话点评（演示帧 · M3 接 learner.py + DeepSeek） ---------- */
const aiNote = '本周 6 次练习、流利度 +4 分。机场 · 航班变动最薄弱——先补「值机出行」的高频表达会更顺。'
</script>

<template>
  <div class="u-phone">
    <!-- 学习页顶栏无头像：画像页 LV 徽章已是身份焦点（2026-09-09 组长反馈） -->
    <MobileTopBar title="学习" :show-avatar="false" />

    <div class="u-learn">
      <!-- 卡 1 · 画像主卡：身份行 ｜ 分割线 ｜ 今日四数（参考社区页帖子卡结构） -->
      <section class="u-learn-hero">
        <div class="u-learn-hero__row">
          <div class="u-learn-hero__badge">
            <span class="u-learn-hero__lv">{{ progress.lvLabel }}</span>
            <span class="u-learn-hero__rank">{{ progress.info.title }}</span>
          </div>
          <div class="u-learn-hero__body">
            <div class="u-learn-hero__bar" role="progressbar" :aria-valuenow="progress.progressPct" aria-valuemin="0" aria-valuemax="100">
              <span class="u-learn-hero__fill" :style="{ width: `${progress.progressPct}%` }" />
            </div>
            <div class="u-learn-hero__xp">
              {{ progress.xpInLevel }} / {{ progress.nextXp ?? '—' }} XP{{ progress.nextXp ? ' · 距下一级' : ' · 已满级' }}
            </div>
            <div class="u-learn-hero__stats">
              <span class="u-learn-hero__stat">
                <MobileIcon name="flame" :size="16" />{{ streak }} 天
              </span>
              <span class="u-learn-hero__stat">
                <MobileIcon name="clock" :size="16" />本周 {{ weekMinutes }} 分钟
              </span>
            </div>
          </div>
        </div>

        <div class="u-learn-hero__today" aria-label="今日概览">
          <div class="u-learn-today__item">
            <span class="u-learn-today__num">{{ todayTurns }}</span>
            <span class="u-learn-today__label">今日练习</span>
          </div>
          <div class="u-learn-today__item">
            <span class="u-learn-today__num">{{ todayMinutes }}</span>
            <span class="u-learn-today__label">今日分钟</span>
          </div>
          <div class="u-learn-today__item">
            <span class="u-learn-today__num">{{ weekTurns }}</span>
            <span class="u-learn-today__label">本周练习</span>
          </div>
          <div class="u-learn-today__item">
            <span class="u-learn-today__num">{{ progress.xp }}</span>
            <span class="u-learn-today__label">总 XP</span>
          </div>
        </div>
      </section>

      <!-- 卡 2 · 学习热力图：只留图 + 右下角经验（无图例/无日期/无切换） -->
      <section class="u-learn-card u-learn-heat" aria-label="学习热力图">
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

      <!-- 卡 3 · 能力画像：趋势 + 场景掌握度 + 薄弱点 + AI 点评（高密度一大卡） -->
      <section class="u-learn-card u-learn-ability">
        <div class="u-section-title" style="margin-bottom: 0">能力画像</div>

        <!-- 流利度趋势 -->
        <div class="u-learn-ability__sub">
          <span>流利度趋势</span>
          <span class="u-learn-trend__avg">近 7 天均分 {{ trendAvg }}</span>
        </div>
        <div class="u-learn-trend" aria-label="最近 7 天平均分趋势">
          <div
            v-for="(v, i) in weekTrend"
            :key="i"
            class="u-learn-trend__bar"
            :class="[`tone-${trendTone(v)}`, { 'is-last': i === weekTrend.length - 1 }]"
            :style="{ height: `${v * 0.8}%` }"
            :title="`第 ${i + 1} 天 · ${v} 分`"
          />
        </div>

        <!-- 场景掌握度 -->
        <div class="u-learn-ability__sub">
          <span>场景掌握度</span>
          <span class="u-learn-ability__hint">进阶场景偏弱？先回入门场景巩固</span>
        </div>
        <ul class="u-learn-scenes">
          <li v-for="s in scenes" :key="s.name" class="u-learn-scenes__row">
            <span class="u-learn-scenes__name">{{ s.name }}</span>
            <span class="u-learn-scenes__track" aria-hidden="true">
              <span class="u-learn-scenes__fill" :class="band(s.score)" :style="{ width: `${s.score}%` }" />
            </span>
            <span class="u-learn-scenes__score">{{ s.score }}</span>
          </li>
        </ul>

        <!-- 薄弱点 + AI 点评（画像结论行） -->
        <div class="u-learn-ability__concl">
          <div class="u-learn-card__row" style="margin-top: 0">
            <span class="u-learn-card__label">薄弱音素</span>
            <span v-for="p in weakPhonemes" :key="p" class="u-chip u-chip--warm">{{ p }}</span>
          </div>
          <div class="u-learn-card__row">
            <span class="u-learn-card__label">高频错误词</span>
            <span v-for="w in weakWords" :key="w" class="u-chip u-chip--ink">{{ w }}</span>
          </div>
          <div class="u-learn-ai">
            <span class="u-learn-ai__icon"><MobileIcon name="wave" :size="16" /></span>
            <p class="u-learn-ai__text">{{ aiNote }}</p>
          </div>
        </div>
      </section>

      <p class="u-note" style="text-align: center; margin-top: 20px">
        等级经验真实结算；热力图/画像数据 M3 接入（attempts · 讯飞词级）。
      </p>
    </div>
  </div>
</template>
