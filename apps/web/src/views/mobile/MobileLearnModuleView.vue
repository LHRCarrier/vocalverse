<script setup lang="ts">
/**
 * 学习模块详情页（/m/learn/:module · 2026-09-09 组长拍板 v4：数据细节下沉到详情层）
 * 主页只给一句话结论，这里才是数据展示：单词 / 社区足迹 / 我的发音 / 冒险进度。
 * 数据源（docs/53 P4）：`GET /api/v1/stats/learn/{key}`（Python `app/insight/learn.py`）；
 * 空数据与接口失败均有显式空态（不再硬编码演示帧，DoD ①/③）。
 */
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchLearnModule } from '@/api/stats'
import type { LearnModuleDetail } from '@/api/stats'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import {
  buildHeatmapWeeks,
  heatCellKey,
  isFutureCell,
  isTodayCell,
} from '@/composables/useLearnHeatmap'
import '@/styles/mobile-uic.css'

import type { HeatCell } from '@/composables/useLearnHeatmap'

const route = useRoute()
const router = useRouter()

type ModuleKey = 'words' | 'community' | 'speaking' | 'practice'

const MODULE_TITLES: Record<ModuleKey, string> = {
  words: '我的单词',
  community: '社区足迹',
  speaking: '我的发音',
  practice: '冒险进度',
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

/* ---------- 数据加载（docs/53 P4；模块切换重拉） ---------- */
const detail = ref<LearnModuleDetail | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  detail.value = null
  try {
    detail.value = await fetchLearnModule(moduleKey.value)
  } catch (e) {
    error.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}
watch(moduleKey, () => void load(), { immediate: true })

/* ---------- 我的发音（attempts 三维 + 薄弱音素 · 真实聚合） ---------- */
const fmt = (v?: number | null) => (v == null ? '—' : String(v))
const speakingTrend = computed(() => (detail.value?.trend ?? []).slice(-7))
const trendSeries = computed(() => ({
  pron: speakingTrend.value.map((r) => r.pron ?? null),
  flu: speakingTrend.value.map((r) => r.flu ?? null),
  gram: speakingTrend.value.map((r) => r.gram ?? null),
}))
/** 柱高：60~95 → 0~100% 可视范围（该日无此维度 → 0） */
function barH(v: number | null) {
  if (v == null) return 0
  return Math.max(6, Math.min(100, ((v - 60) / 35) * 100))
}
const weakPhonemes = computed(() => detail.value?.weak_phonemes ?? [])

/* ---------- 冒险进度（热力图 + 会话分布 + 酒馆剧本 · 真实聚合） ---------- */
const heatCells = computed(() => buildHeatmapWeeks(detail.value?.heatmap, 12).flat())
const dateKey = heatCellKey
const isToday = isTodayCell
const isFuture = isFutureCell
const selected = ref<HeatCell | null>(null)
watch(
  heatCells,
  (cells) => {
    if (selected.value && selected.value.level > 0) return
    selected.value = cells.find(isTodayCell) ?? cells[cells.length - 2] ?? null
  },
  { immediate: true },
)
function pick(cell: HeatCell) {
  selected.value = cell
}
const selectedXpLabel = computed(() => {
  const cell = selected.value
  if (!cell || isFuture(cell) || cell.level === 0) return '未练习'
  return `+${cell.xp} XP`
})

const KIND_LABELS: Record<string, string> = {
  sing: '唱吧跟唱',
  defense: '答辩练习',
  shadow: '影子跟读',
  free_chat: '自由对话',
}
const byKind = computed(() => detail.value?.by_kind ?? [])
const practiceMinutes = computed(() => detail.value?.minutes ?? 0)
const practiceCount = computed(() => byKind.value.reduce((sum, k) => sum + k.count, 0))

const campaigns = computed(() => detail.value?.campaigns ?? [])
function turnRatio(c: { turns: number; user_turns: number }) {
  return c.turns ? Math.round((c.user_turns / c.turns) * 100) : 0
}
function band(pct: number) {
  return pct >= 50 ? 'high' : pct >= 25 ? '' : 'low'
}

/* ---------- 我的单词（生词本 + 词典首义） ---------- */
const STATUS_LABELS: Record<string, string> = { new: '新词', learning: '学习中', known: '已掌握' }
const SCENE_LABELS: Record<string, string> = { reading: '阅读', community: '社区', manual: '手动' }
const words = computed(() => detail.value?.items ?? [])
function wordMeta(w: { status: string; scene: string; created_at: string | null }) {
  const scene = SCENE_LABELS[w.scene] ?? w.scene
  const date = w.created_at ? w.created_at.slice(0, 10) : ''
  return [scene, date].filter(Boolean).join(' · ')
}

/* ---------- 社区足迹（埋点分布 + 常逛页面） ---------- */
const EVENT_LABELS: Record<string, string> = {
  page_view: '页面浏览',
  word_lookup: '划词查词',
  vocab_add: '加入生词本',
  annotation_add: '笔记批注',
  practice_complete: '完成练习',
  score_event: '评分事件',
  recording_start: '开始录音',
  recording_complete: '完成录音',
  tts_play: '听书播放',
  tts_prepare: '整章预合成',
  scene_start: '开始场景',
  recommend_impression: '推荐曝光',
  recommend_click: '推荐点击',
  free_chat_open: '打开自由对话',
  free_chat_turn: '自由对话回合',
  free_chat_reset: '重置自由对话',
}
const PAGE_LABELS: Record<string, string> = {
  '/m/home': '首页',
  '/m/learn': '学习',
  '/m/sing': '唱吧',
  '/m/tavern': '酒馆',
  '/m/bookshelf': '书房',
  '/m/vocab': '生词本',
  '/m/notes': '笔记',
  '/m/checkin': '打卡',
  '/m/search': '搜索',
}
function pageLabel(path: string) {
  if (PAGE_LABELS[path]) return PAGE_LABELS[path]
  if (path.startsWith('/m/reader/')) return '阅读器'
  if (path.startsWith('/m/books/')) return '书籍详情'
  if (path.startsWith('/m/post/')) return '帖子详情'
  return path
}
const pages = computed(() => detail.value?.pages ?? [])
const pageMax = computed(() => Math.max(1, ...pages.value.map((p) => p.count)))
const events = computed(() => detail.value?.events ?? [])
const communityTotal = computed(() =>
  (detail.value?.trend ?? []).reduce((sum, d) => sum + (d.count ?? 0), 0),
)
</script>

<template>
  <div class="u-phone">
    <MobileTopBar :title="title" back @back="backToLearn" />

    <div class="u-learn-detail">
      <!-- 加载中 -->
      <section v-if="loading" class="u-comm-skel" aria-label="加载中" aria-busy="true">
        <div v-for="i in 3" :key="i" class="u-comm-skel__card"><span class="u-comm-skel__lines" /></div>
      </section>

      <!-- 接口失败：显式错误 + 重试（DoD ③） -->
      <div v-else-if="error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">加载失败</span>
        <p class="u-comm-empty__sub">{{ error }}</p>
        <button class="u-comm-empty__btn" type="button" @click="load">重试</button>
      </div>

      <template v-else-if="detail">
        <!-- 我的发音：三维均分 + 趋势柱 + 薄弱音素 -->
        <template v-if="moduleKey === 'speaking'">
          <section class="u-learn-detail__scores">
            <div class="u-learn-detail__score">
              <b>{{ fmt(detail.dims?.pron) }}</b><i>发音</i>
            </div>
            <div class="u-learn-detail__score">
              <b>{{ fmt(detail.dims?.flu) }}</b><i>流利度</i>
            </div>
            <div class="u-learn-detail__score">
              <b>{{ fmt(detail.dims?.gram) }}</b><i>语法</i>
            </div>
          </section>

          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">近 7 次练习 · 三维评分</div>
            <div v-if="speakingTrend.length" class="u-learn-detail__trend" aria-label="发音/流利度/语法近 7 次趋势">
              <div class="u-learn-detail__tel">
                <span v-for="(v, i) in trendSeries.pron" :key="`p${i}`" class="u-learn-detail__pr" :style="{ height: `${barH(v)}%` }" />
                <span v-for="(v, i) in trendSeries.flu" :key="`f${i}`" class="u-learn-detail__fl" :style="{ height: `${barH(v)}%` }" />
                <span v-for="(v, i) in trendSeries.gram" :key="`g${i}`" class="u-learn-detail__gr" :style="{ height: `${barH(v)}%` }" />
              </div>
              <div class="u-learn-detail__legend">
                <span><i class="dot dot--pr" />发音</span>
                <span><i class="dot dot--fl" />流利度</span>
                <span><i class="dot dot--gr" />语法</span>
              </div>
            </div>
            <p v-else class="u-learn-detail__note">还没有练习记录——完成一次答辩或跟唱后，这里会出现三维趋势。</p>
          </section>

          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">薄弱音素（近 30 天错误 Top3）</div>
            <div v-if="weakPhonemes.length" class="u-learn-detail__chips">
              <span v-for="p in weakPhonemes" :key="p.phoneme" class="u-chip u-chip--warm">
                /{{ p.phoneme }}/ · {{ p.count }} 次
              </span>
            </div>
            <p v-else class="u-learn-detail__note">暂无薄弱音素记录——有词级评测数据后自动统计。</p>
            <p class="u-learn-detail__note">词级错误沉淀自每次练习的发音评测（scores.error_type）。</p>
          </section>
        </template>

        <!-- 冒险进度：热力图 + 练习分布 + 酒馆剧本推进度 -->
        <template v-else-if="moduleKey === 'practice'">
          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">近 12 周练习热力图</div>
            <div class="u-learn-heat__grid">
              <button
                v-for="cell in heatCells"
                :key="dateKey(cell)"
                type="button"
                class="u-learn-heat__cell"
                :class="[`lv${cell.level}`, { today: isToday(cell), future: isFuture(cell), picked: selected != null && dateKey(cell) === dateKey(selected) }]"
                :disabled="isFuture(cell)"
                :aria-label="`${dateKey(cell)} · ${isFuture(cell) ? '还没到' : cell.level === 0 ? '未练习' : `+${cell.xp} XP`}`"
                @click="pick(cell)"
              />
            </div>
            <div class="u-learn-heat__xp" aria-live="polite">{{ selectedXpLabel }}</div>
          </section>

          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">近 30 天练习分布</div>
            <p class="u-learn-detail__note u-learn-detail__note--lead">
              共 {{ practiceMinutes }} 分钟 · {{ practiceCount }} 次会话
            </p>
            <ul v-if="byKind.length" class="u-learn-posts">
              <li v-for="k in byKind" :key="k.kind" class="u-learn-posts__row">
                <span class="u-learn-posts__title">{{ KIND_LABELS[k.kind] ?? k.kind }} · {{ k.count }} 次</span>
                <span class="u-learn-posts__when">{{ k.minutes }} 分钟</span>
              </li>
            </ul>
            <p v-else class="u-learn-detail__note">近 30 天还没有练习会话。</p>
          </section>

          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">酒馆剧本推进度</div>
            <ul v-if="campaigns.length" class="u-learn-scenes">
              <li v-for="c in campaigns" :key="c.id" class="u-learn-scenes__row">
                <span class="u-learn-scenes__name">{{ c.name }}</span>
                <span class="u-learn-scenes__track" aria-hidden="true">
                  <span class="u-learn-scenes__fill" :class="band(turnRatio(c))" :style="{ width: `${turnRatio(c)}%` }" />
                </span>
                <span class="u-learn-scenes__score u-learn-scenes__score--wide">{{ c.user_turns }}/{{ c.turns }}</span>
              </li>
            </ul>
            <p v-else class="u-learn-detail__note">还没有酒馆剧本——去酒馆开一局吧。</p>
            <p class="u-learn-detail__note">进度 = 玩家发起回合数 / 总回合数；最多展示最近 8 个剧本。</p>
          </section>
        </template>

        <!-- 我的单词：生词本（词典首义）+ 管理入口 -->
        <template v-else-if="moduleKey === 'words'">
          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">生词本 · 最近 50 词</div>
            <ul v-if="words.length" class="u-learn-words">
              <li v-for="w in words" :key="w.word" class="u-learn-words__row">
                <span class="u-learn-words__word">{{ w.word }}</span>
                <span class="u-learn-words__meaning">{{ w.translation ?? wordMeta(w) }}</span>
                <span class="u-learn-words__score" :class="w.status === 'new' ? 'low' : ''">
                  {{ STATUS_LABELS[w.status] ?? w.status }}
                </span>
              </li>
            </ul>
            <p v-else class="u-learn-detail__note">生词本还是空的——阅读时点词即收，就会出现在这里。</p>
            <p v-if="words.length" class="u-learn-detail__note">释义取词典首义；未收录词显示来源与日期（scene · created_at）。</p>
          </section>

          <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="router.push('/m/vocab')">
            <MobileIcon name="bookmark" :size="16" /> 去生词本管理（改状态 / 删除）
          </button>
        </template>

        <!-- 社区足迹：常逛页面 + 互动类型 -->
        <template v-else>
          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">常逛页面（近 30 天）</div>
            <ul v-if="pages.length" class="u-learn-pref">
              <li v-for="p in pages" :key="p.page" class="u-learn-pref__row">
                <span class="u-learn-pref__label">{{ pageLabel(p.page) }}</span>
                <span class="u-learn-pref__track" aria-hidden="true">
                  <span class="u-learn-pref__fill" :style="{ width: `${Math.round((p.count / pageMax) * 100)}%` }" />
                </span>
                <span class="u-learn-pref__pct">{{ p.count }}</span>
              </li>
            </ul>
            <p v-else class="u-learn-detail__note">近 30 天还没有浏览记录。</p>
          </section>

          <section class="u-learn-detail__card">
            <div class="u-learn-detail__sub">互动类型（共 {{ communityTotal }} 次）</div>
            <ul v-if="events.length" class="u-learn-posts">
              <li v-for="e in events" :key="e.event_type" class="u-learn-posts__row">
                <span class="u-learn-posts__title">{{ EVENT_LABELS[e.event_type] ?? e.event_type }}</span>
                <span class="u-learn-posts__when">{{ e.count }} 次</span>
              </li>
            </ul>
            <p v-else class="u-learn-detail__note">还没有社区足迹——看看英语新闻，或去社区逛逛吧。</p>
            <p class="u-learn-detail__note">来自埋点事实表 events；发帖/点赞数据由社区服务单独统计。</p>
          </section>
        </template>
      </template>
    </div>
  </div>
</template>
