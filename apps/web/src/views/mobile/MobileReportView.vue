<script setup lang="ts">
/**
 * 移动端 · 评分报告——ui-concept-design skill 重制版
 * 视觉正本：ref-dark-colored-cards（深色卡 chip + 幽灵按钮 + 光晕）+ ref-profile-card-stats（四维统计）
 *          + ref-card-light-timeline（实色图标块 + 点线时间轴）
 * 数据：?reportId= → 真实会话报告（docs/14 §3.1 metrics：逐轮 attempts / 覆盖度 / 建议 / 语义子分）；
 *       无 reportId → 演示帧（跟唱报告示例值）。两种形态共享同一套视觉。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchReport, type ReportPayload } from '@/api/practice'
import { shareDemoLink } from '@/composables/share'
import { useUiStore } from '@/stores/ui'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()

/* ---------- 真实报告（结构见 docs/14 §3.1 metrics 契约） ---------- */
interface ReportAttempt {
  transcript?: string
  pronunciation?: number | null
  fluency?: number | null
  grammar?: number | null
  overall?: number | null
}

interface ReportMetrics {
  summary?: string
  kind?: string
  assigned_turns?: number | null
  user_turn_count?: number | null
  duration_s?: number | null
  coverage?: { covered: string[]; needs_fix: string[]; to_practice: string[]; coverage_count: number }
  semantic?: { content?: { score: number | null; turns: number }; vocab?: { score: number | null; turns: number } }
  suggestions?: string[]
  attempts?: ReportAttempt[]
}

const report = ref<ReportPayload | null>(null)
const loaded = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

onMounted(async () => {
  const id = Number(route.query.reportId)
  if (!id) return // 无 reportId → 演示帧
  loaded.value = 'loading'
  try {
    report.value = await fetchReport(id)
    loaded.value = 'ok'
  } catch (e) {
    error.value = (e as Error).message
    loaded.value = 'error'
  }
})

const metrics = computed<ReportMetrics>(() => (report.value?.metrics ?? {}) as ReportMetrics)

function avg(field: keyof ReportAttempt): number | null {
  const list = metrics.value.attempts ?? []
  const vals = list
    .map((a) => a[field])
    .filter((v): v is number => typeof v === 'number')
  if (!vals.length) return null
  return Math.round(vals.reduce((s, v) => s + v, 0) / vals.length)
}

const totalScore = computed<number | null>(() => avg('overall'))

const pronAvg = computed(() => avg('pronunciation'))
const fluAvg = computed(() => avg('fluency'))
const gramAvg = computed(() => avg('grammar'))

function fmtDuration(s: number | null | undefined): string | null {
  if (s == null || s <= 0) return null
  const m = Math.floor(s / 60)
  const sec = s % 60
  return m > 0 ? `${m} 分 ${sec} 秒` : `${sec} 秒`
}

/** 顶栏 · 分享报告（演示：系统面板 / 复制链接） */
async function shareReport() {
  const r = report.value
  const result = await shareDemoLink({
    title: 'VocalVerse 评分报告',
    text: r ? `会话 #${route.query.reportId}` : 'Perfect Night · LE SSERAFIM · 12-16 20:15',
    url: r ? `https://vocalverse.demo/report/${route.query.reportId}` : 'https://vocalverse.demo/report/demo',
  })
  if (result === 'shared') ui.showToast('已分享')
  else if (result === 'copied') ui.showToast('报告链接已复制（演示链接）')
  else if (result === 'failed') ui.showToast('复制失败，请手动复制')
}

/* ---------- 演示帧（无 reportId · 跟唱报告示例值） ---------- */
const demoLines = [
  { lyric: "You know I'm just a girl...", comment: '音准优秀，连读自然', score: '95', color: '#1E2B26', accent: true },
  { lyric: 'And I will always love you...', comment: '副歌前换气略早', score: '88', color: '#232044', accent: false },
  { lyric: "I'm yours, I'm yours...", comment: '重复段略有抢拍', score: '81', color: '#16303A', accent: false },
] as const
</script>

<template>
  <div class="u-phone">
    <!-- 统一顶栏（返回 + 全局头像 / 评分报告 / 分享报告） -->
    <MobileTopBar title="评分报告" back @back="router.back()">
      <template #actions>
        <button class="u-topbar__act" type="button" title="分享报告（演示）" aria-label="分享报告" @click="shareReport">
          <MobileIcon name="share" :size="18" />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content u-content--free">
      <p class="u-head__sub" style="margin: 0 0 16px">
        {{ report ? `会话 #${route.query.reportId}` : 'Perfect Night · LE SSERAFIM · 12-16 20:15' }}
      </p>

      <!-- 深紫评分卡（同色系 chip + 大数值 + 音符线稿锚点 + 幽灵按钮） -->
      <section class="u-dark-card u-dark-card--purple">
        <div class="u-dark-card__art" aria-hidden="true">
          <MobileArt name="note" :size="104" />
        </div>
        <span class="u-chip u-chip--purple">{{ report ? '已完成' : '新纪录' }}</span>
        <span class="u-dark-card__meta">{{ report ? (metrics.kind === 'dialog' ? '口语对话 · 已评分' : '会话 · 已评分') : '107s · 全曲跟唱' }}</span>
        <h2 class="u-dark-card__title">{{ report ? (metrics.kind === 'dialog' ? '口语对话' : '会话报告') : 'Perfect Night' }}</h2>
        <p class="u-dark-card__desc">
          <template v-if="report">{{ metrics.summary ?? '会话完成。' }}（{{ fmtDuration(metrics.duration_s) ?? `${metrics.user_turn_count ?? '—'} 轮` }}）</template>
          <template v-else>Beat 82% of learners. Keep it up.</template>
        </p>
        <button
          class="u-btn u-btn--ghost"
          type="button"
          style="margin-top: 16px"
          @click="report ? router.push('/m/home') : router.push('/m/sing')"
        >
          <MobileIcon name="music" :size="16" />
          {{ report ? '回到首页' : '再唱一遍' }}
        </button>
        <div class="u-dark-card__score">
          <div class="label">{{ report ? '综合分' : 'Total' }}</div>
          <div class="num">{{ report ? (totalScore ?? '—') : 92.4 }}</div>
        </div>
      </section>

      <!-- 四维统计（Caption weak 在上 + 大数字在下；真实值优先） -->
      <section class="u-metrics">
        <div class="u-m">
          <div class="u-m-label">发音</div>
          <div class="u-m-value u-m-value--accent">{{ report ? (pronAvg ?? '—') : 93 }}</div>
        </div>
        <div class="u-m">
          <div class="u-m-label">语法</div>
          <div class="u-m-value">{{ report ? (gramAvg ?? '—') : 91 }}</div>
        </div>
        <div class="u-m">
          <div class="u-m-label">流利</div>
          <div class="u-m-value">{{ report ? (fluAvg ?? '—') : 88 }}</div>
        </div>
        <div class="u-m">
          <div class="u-m-label">覆盖</div>
          <div class="u-m-value">{{ report ? `${metrics.coverage?.coverage_count ?? 0}` : '100%' }}</div>
        </div>
      </section>

      <!-- ================= 真实数据分支 ================= -->
      <template v-if="report">
        <!-- 语义子分（LLM 判定 · 进展示不进总分 · docs/14 §3.4） -->
        <div v-if="metrics.semantic?.content?.score != null || metrics.semantic?.vocab?.score != null" class="u-card" style="padding: 20px; margin-bottom: 24px">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px">
            <div class="u-section-title" style="margin: 0">语义表现</div>
            <span class="u-caption">LLM 判定 · 不计入总分</span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px">
            <div class="u-stat-label">内容相关度</div>
            <div class="u-stat-label">词汇多样性</div>
            <div class="u-stat-value">{{ metrics.semantic?.content?.score ?? '—' }}</div>
            <div class="u-stat-value">{{ metrics.semantic?.vocab?.score ?? '—' }}</div>
          </div>
        </div>

        <!-- 覆盖度（目标表达命中） -->
        <div style="margin-bottom: 24px">
          <div class="u-section-title">表达覆盖</div>
          <div class="u-item" style="cursor: default; align-items: flex-start">
            <span class="u-icon-block" style="background: #1e2b26">
              <MobileIcon name="check" :size="22" />
            </span>
            <div class="u-item__main">
              <div class="u-item__title" style="color: var(--u-success)">
                已覆盖 {{ metrics.coverage?.covered?.length ?? 0 }} 个表达
              </div>
              <div style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px">
                <span v-for="c in metrics.coverage?.covered ?? []" :key="c" class="u-chip u-chip--accent">{{ c }}</span>
              </div>
              <div v-if="metrics.coverage?.needs_fix?.length" style="display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px">
                <span v-for="c in metrics.coverage.needs_fix" :key="c" class="u-chip u-chip--warm">需巩固：{{ c }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 逐轮明细（点线时间轴） -->
        <div v-if="metrics.attempts?.length">
          <div class="u-section-title">逐轮评分</div>
          <template v-for="(a, i) in metrics.attempts.slice(0, 8)" :key="i">
            <div class="u-item" style="cursor: default">
              <span class="u-icon-block" :style="{ background: ['#1E2B26', '#232044', '#16303A'][i % 3] }">
                <MobileIcon name="mic" :size="22" />
              </span>
              <div class="u-item__main">
                <div class="u-item__title">{{ a.transcript?.slice(0, 40) || `第 ${i + 1} 轮回答` }}</div>
                <div class="u-item__sub">发音 {{ a.pronunciation ?? '—' }} · 流利 {{ a.fluency ?? '—' }} · 语法 {{ a.grammar ?? '—' }}</div>
              </div>
              <span class="u-item__value" :class="{ 'u-item__value--ink': (a.overall ?? 0) < 85 }">{{ a.overall ?? '—' }}</span>
            </div>
            <div v-if="i < Math.min(metrics.attempts?.length ?? 0, 8) - 1" class="u-dotline" aria-hidden="true">
              <span class="dot" /><span class="line" />
            </div>
          </template>
        </div>

        <!-- 教练建议 -->
        <div v-if="metrics.suggestions?.length" style="margin-top: 24px">
          <div class="u-section-title">教练建议</div>
          <div class="u-settings">
            <div v-for="(s, i) in metrics.suggestions.slice(0, 4)" :key="i" class="u-setting" style="cursor: default">
              <span class="u-icon-block u-icon-block--sm" style="background: #3a2440">
                <MobileIcon name="book" :size="18" />
              </span>
              <span class="u-setting__label">{{ s }}</span>
            </div>
          </div>
        </div>
      </template>

      <!-- ================= 演示帧：逐句评分（点线时间轴） ================= -->
      <template v-else>
        <div class="u-section-title">逐句评分</div>
        <template v-for="(l, i) in demoLines" :key="i">
          <div class="u-item" style="cursor: default">
            <span class="u-icon-block" :style="{ background: l.color }">
              <MobileIcon name="note" :size="22" />
            </span>
            <div class="u-item__main">
              <div class="u-item__title">{{ l.lyric }}</div>
              <div class="u-item__sub">{{ l.comment }}</div>
            </div>
            <span class="u-item__value" :class="{ 'u-item__value--ink': !l.accent }">{{ l.score }}</span>
          </div>
          <div v-if="i < demoLines.length - 1" class="u-dotline" aria-hidden="true">
            <span class="dot" /><span class="line" />
          </div>
        </template>
      </template>

      <div v-if="loaded === 'error'" class="u-error">{{ error }}</div>
    </div>
  </div>
</template>
