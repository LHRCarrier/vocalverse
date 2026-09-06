<script setup lang="ts">
/**
 * 学习模块详情页（/m/learn/:module · 2026-09-09 组长拍板 v4：数据细节下沉到详情层）
 * 主页只给一句话结论，这里才是数据展示：单词 / 社区足迹 / 我的发音 / 练习情况。
 * 演示帧数据为主（M3 接 attempts/词级/埋点聚合）；布局 X 式（顶部标题 + 内容区）。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const route = useRoute()
const router = useRouter()

type ModuleKey = 'words' | 'community' | 'speaking' | 'practice'

const MODULE_TITLES: Record<ModuleKey, string> = {
  words: '我的单词',
  community: '社区足迹',
  speaking: '我的发音',
  practice: '练习情况',
}

const moduleKey = computed<ModuleKey>(() => {
  const k = String(route.params.module ?? '')
  return (['words', 'community', 'speaking', 'practice'] as const).includes(k as ModuleKey)
    ? (k as ModuleKey)
    : 'practice'
})
const title = computed(() => MODULE_TITLES[moduleKey.value])

function backToLearn() {
  void router.push('/m/learn')
}

/* ---------- 我的发音（attempts 三维 · 演示帧） ---------- */
const speakingTrend = { pron: [78, 80, 82, 84, 81, 85, 82], flu: [70, 72, 75, 77, 79, 78, 78], gram: [85, 86, 84, 88, 90, 87, 85] }
const speakingAvg = computed(() => ({
  pron: Math.round(speakingTrend.pron.reduce((a, b) => a + b, 0) / 7),
  flu: Math.round(speakingTrend.flu.reduce((a, b) => a + b, 0) / 7),
  gram: Math.round(speakingTrend.gram.reduce((a, b) => a + b, 0) / 7),
}))
const weakPhonemes = ['/θ/', '/ð/', '/r/']
/** 柱高：60~95 → 0~100% 可视范围 */
function barH(v: number) {
  return Math.max(10, Math.min(100, ((v - 60) / 35) * 100))
}

/* ---------- 练习情况（12 周热力图复用主页逻辑 · 演示帧） ---------- */
type HeatCell = { date: Date; level: 0 | 1 | 2 | 3; xp: number }
function dayLevel(d: Date): { level: 0 | 1 | 2 | 3; xp: number } {
  const today = new Date()
  if (d.getTime() > today.getTime()) return { level: 0, xp: 0 }
  if (d.toDateString() === today.toDateString()) return { level: 3, xp: 75 }
  const h = (d.getFullYear() * 372 + (d.getMonth() + 1) * 31 + d.getDate() * 7) % 10
  if (h < 5) return { level: 0, xp: 0 }
  if (h < 7) return { level: 1, xp: 25 }
  if (h < 9) return { level: 2, xp: 50 }
  return { level: 3, xp: 75 }
}
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
const heatCells = buildWeeks(12).flat()
const isToday = (c: HeatCell) => c.date.toDateString() === new Date().toDateString()
const isFuture = (c: HeatCell) => c.date.getTime() > new Date().getTime()
const dateKey = (c: HeatCell) =>
  `${c.date.getFullYear()}-${String(c.date.getMonth() + 1).padStart(2, '0')}-${String(c.date.getDate()).padStart(2, '0')}`
const selected = ref<HeatCell>(heatCells.find(isToday) ?? heatCells[heatCells.length - 2])
function pick(cell: HeatCell) {
  selected.value = cell
}
const selectedXpLabel = computed(() =>
  isFuture(selected.value) || selected.value.level === 0 ? '未练习' : `+${selected.value.xp} XP`,
)

const scenes = [
  { name: '咖啡馆 · 点单', score: 78 },
  { name: '咖啡馆 · 订单沟通', score: 54 },
  { name: '机场 · 值机出行', score: 82 },
  { name: '机场 · 航班变动', score: 47 },
  { name: '面试 · 自我介绍', score: 85 },
  { name: '面试 · 深挖追问', score: 38 },
  { name: '图书馆 · 借阅', score: 70 },
  { name: '图书馆 · 学业交流', score: 61 },
] as const
function band(score: number) {
  return score >= 80 ? 'high' : score >= 60 ? 'mid' : 'low'
}

/* ---------- 社区足迹（演示帧：收藏/点赞列表 + 偏好占比） ---------- */
const communityLikes = [
  { title: "'AI learning' is taking over China's classrooms", when: '今天 · 英语新闻' },
  { title: '6 Minute English: Why do we procrastinate?', when: '昨天 · 英语新闻' },
  { title: 'How I memorize 100 new words a month', when: '3 天前 · 学习分享' },
  { title: 'Dorm life at MIT: my morning in 60 seconds', when: '上周 · 海外生活' },
]
const communityPref = [
  { label: '英语新闻', pct: 46 },
  { label: '学习分享', pct: 32 },
  { label: '海外生活', pct: 22 },
]

/* ---------- 我的单词（演示帧：收藏词 + 薄弱词） ---------- */
const words = [
  { word: 'pick up', meaning: '学会 / 顺便买 / 接人', score: 92 },
  { word: 'run out of', meaning: '用光，耗尽', score: 60 },
  { word: 'comfortable', meaning: '舒适的', score: 41 },
  { word: 'world', meaning: '世界', score: 38 },
  { word: 'interesting', meaning: '有趣的', score: 35 },
]
</script>

<template>
  <div class="u-phone">
    <MobileTopBar :title="title" back @back="backToLearn" />

    <div class="u-learn-detail">
      <!-- 我的发音：三维均分 + 趋势柱 + 薄弱音素 -->
      <template v-if="moduleKey === 'speaking'">
        <section class="u-learn-detail__scores">
          <div class="u-learn-detail__score">
            <b>{{ speakingAvg.pron }}</b><i>发音</i>
          </div>
          <div class="u-learn-detail__score">
            <b>{{ speakingAvg.flu }}</b><i>流利度</i>
          </div>
          <div class="u-learn-detail__score">
            <b>{{ speakingAvg.gram }}</b><i>语法</i>
          </div>
        </section>

        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">近 7 次练习 · 三维评分</div>
          <div class="u-learn-detail__trend" aria-label="发音/流利度/语法近 7 次趋势">
            <div class="u-learn-detail__tel">
              <span v-for="(v, i) in speakingTrend.pron" :key="`p${i}`" class="u-learn-detail__pr" :style="{ height: `${barH(v)}%` }" />
              <span v-for="(v, i) in speakingTrend.flu" :key="`f${i}`" class="u-learn-detail__fl" :style="{ height: `${barH(v)}%` }" />
              <span v-for="(v, i) in speakingTrend.gram" :key="`g${i}`" class="u-learn-detail__gr" :style="{ height: `${barH(v)}%` }" />
            </div>
            <div class="u-learn-detail__legend">
              <span><i class="dot dot--pr" />发音</span>
              <span><i class="dot dot--fl" />流利度</span>
              <span><i class="dot dot--gr" />语法</span>
            </div>
          </div>
        </section>

        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">薄弱音素（M3 讯飞词级替换）</div>
          <div class="u-learn-detail__chips">
            <span v-for="p in weakPhonemes" :key="p" class="u-chip u-chip--warm">{{ p }}</span>
          </div>
          <p class="u-learn-detail__note">词级错误沉淀自每次练习的发音评测（attempts.details.word_level）。</p>
        </section>
      </template>

      <!-- 练习情况：热力图 + 场景掌握度 -->
      <template v-else-if="moduleKey === 'practice'">
        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">近 12 周练习热力图</div>
          <div class="u-learn-heat__grid">
            <button
              v-for="cell in heatCells"
              :key="dateKey(cell)"
              type="button"
              class="u-learn-heat__cell"
              :class="[`lv${cell.level}`, { today: isToday(cell), future: isFuture(cell), picked: dateKey(cell) === dateKey(selected) }]"
              :disabled="isFuture(cell)"
              :aria-label="`${dateKey(cell)} · ${isFuture(cell) ? '还没到' : cell.level === 0 ? '未练习' : `+${cell.xp} XP`}`"
              @click="pick(cell)"
            />
          </div>
          <div class="u-learn-heat__xp" aria-live="polite">{{ selectedXpLabel }}</div>
        </section>

        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">场景掌握度（8 套 · Duo-Strength 式）</div>
          <ul class="u-learn-scenes">
            <li v-for="s in scenes" :key="s.name" class="u-learn-scenes__row">
              <span class="u-learn-scenes__name">{{ s.name }}</span>
              <span class="u-learn-scenes__track" aria-hidden="true">
                <span class="u-learn-scenes__fill" :class="band(s.score)" :style="{ width: `${s.score}%` }" />
              </span>
              <span class="u-learn-scenes__score">{{ s.score }}</span>
            </li>
          </ul>
        </section>
      </template>

      <!-- 我的单词：收藏词 + 薄弱词（数据源：笔记页 + 词级错误） -->
      <template v-else-if="moduleKey === 'words'">
        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">收藏单词（演示；M3 词汇速记接入）</div>
          <ul class="u-learn-words">
            <li v-for="w in words" :key="w.word" class="u-learn-words__row">
              <span class="u-learn-words__word">{{ w.word }}</span>
              <span class="u-learn-words__meaning">{{ w.meaning }}</span>
              <span class="u-learn-words__score" :class="w.score < 60 ? 'low' : ''">{{ w.score }}</span>
            </li>
          </ul>
        </section>
      </template>

      <!-- 社区足迹：收藏/点赞 + 偏好占比（M3 埋点；演示帧） -->
      <template v-else>
        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">内容偏好（点赞/收藏/浏览 · 演示帧 M3 埋点）</div>
          <ul class="u-learn-pref">
            <li
              v-for="p in communityPref"
              :key="p.label"
              class="u-learn-pref__row"
            >
              <span class="u-learn-pref__label">{{ p.label }}</span>
              <span class="u-learn-pref__track" aria-hidden="true">
                <span class="u-learn-pref__fill" :style="{ width: `${p.pct}%` }" />
              </span>
              <span class="u-learn-pref__pct">{{ p.pct }}%</span>
            </li>
          </ul>
        </section>

        <section class="u-learn-detail__card">
          <div class="u-learn-detail__sub">最近互动</div>
          <ul class="u-learn-posts">
            <li v-for="p in communityLikes" :key="p.title" class="u-learn-posts__row">
              <span class="u-learn-posts__title">{{ p.title }}</span>
              <span class="u-learn-posts__when">{{ p.when }}</span>
            </li>
          </ul>
        </section>
      </template>

      <p class="u-learn-foot-note">数据为演示帧，M3 接入真实聚合（attempts · 埋点 · 词汇本）。</p>
    </div>
  </div>
</template>
