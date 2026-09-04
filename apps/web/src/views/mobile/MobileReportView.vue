<script setup lang="ts">
/**
 * 移动端评分报告页（真形态 · 原型 app-report，深紫评分卡 + 四维统计 + 逐句点线时间轴）。
 * 数据：?reportId= 时接真实口语报告（docs/14 §3.1 metrics：summary/coverage/suggestions）；
 * 无 reportId（或 M3 唱歌报告未建设时）→ 形态演示数据（页面内明示）。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchReport, type ReportPayload } from '@/api/practice'

const route = useRoute()
const router = useRouter()

const report = ref<ReportPayload | null>(null)
const loaded = ref<'idle' | 'loading' | 'ok' | 'demo' | 'error'>('idle')
const error = ref<string | null>(null)

onMounted(async () => {
  const id = Number(route.query.reportId)
  if (!id) {
    loaded.value = 'demo'
    return
  }
  loaded.value = 'loading'
  try {
    report.value = await fetchReport(id)
    loaded.value = 'ok'
  } catch (e) {
    error.value = (e as Error).message
    loaded.value = 'error'
  }
})
</script>

<template>
  <div class="u-phone">
    <div class="u-content">
      <header class="u-head" style="margin-bottom: 20px">
        <button class="u-back" type="button" title="返回" @click="router.back()">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M15 5l-7 7 7 7" />
          </svg>
        </button>
        <div style="flex: 1">
          <h1 style="font-size: 22px; font-weight: 700">
            {{ loaded === 'demo' ? 'Singing Report' : 'Report' }}
          </h1>
          <div style="font-size: 13px; color: var(--u-weak); margin-top: 3px">
            {{ loaded === 'demo' ? 'Perfect Night · 形态演示（M3 唱歌接入后替换）' : `会话 #${route.query.reportId ?? ''}` }}
          </div>
        </div>
      </header>

      <!-- 深色评分卡 -->
      <section class="u-hero">
        <div class="art" aria-hidden="true">
          <svg viewBox="0 0 320 340" fill="none" stroke="rgba(255,255,255,.85)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M196 28 L 196 184" /><path d="M196 28 C 196 28 232 40 252 60 C 262 70 264 92 250 102" />
            <ellipse cx="186" cy="196" rx="34" ry="26" /><ellipse cx="250" cy="118" rx="30" ry="24" />
            <path d="M110 96 L 88 128 M96 72 L 70 96" stroke-width="2" />
          </svg>
        </div>
        <span class="u-chip">{{ loaded === 'demo' ? 'New record' : '完成' }}</span>
        <span class="time">{{ loaded === 'demo' ? '107s · full song' : '口语对话 · 已评分' }}</span>
        <h2>{{ report?.metrics.summary ? '对话报告' : 'Perfect Night' }}</h2>
        <p>
          {{
            loaded === 'demo'
              ? 'Beat 82% of learners. Keep it up.'
              : report?.metrics.summary ?? '复盘一下这一轮会话的表现吧。'
          }}
        </p>
        <RouterLink to="/m/home" style="text-decoration: none; display: inline-block">
          <button class="u-btn-ghost" type="button" style="border: 1.5px solid rgba(255,255,255,.6); background: transparent; color: #fff">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M4 13a8 8 0 0 1 16 0" /><rect x="3.5" y="13" width="4" height="6" rx="2" /><rect x="16.5" y="13" width="4" height="6" rx="2" />
            </svg>
            Back home
          </button>
        </RouterLink>
        <div class="score">
          <div class="label">Total</div>
          <div class="num">{{ loaded === 'ok' ? '—' : '92.4' }}</div>
        </div>
      </section>

      <!-- 统计行 -->
      <section class="u-metrics">
        <div class="u-m"><div class="u-m-label">Pitch</div><div class="u-m-value accent">93</div></div>
        <div class="u-m"><div class="u-m-label">Rhythm</div><div class="u-m-value">91</div></div>
        <div class="u-m"><div class="u-m-label">Pronun</div><div class="u-m-value">88</div></div>
        <div class="u-m"><div class="u-m-label">Full</div><div class="u-m-value">100%</div></div>
      </section>

      <!-- 真实数据区：口语报告正文 -->
      <template v-if="loaded === 'ok' && report">
        <div class="u-section-title">Coverage</div>
        <div class="u-task" style="cursor: default">
          <div class="u-task-main">
            <div class="u-task-title" style="color: var(--u-success)">
              ✓ 已覆盖 {{ report.metrics.coverage?.covered?.length ?? 0 }} 个表达
            </div>
            <div class="u-task-sub">{{ report.metrics.coverage?.covered?.join('、') || '—' }}</div>
          </div>
        </div>
        <div v-if="report.metrics.coverage?.needs_fix?.length" class="u-dotline"><span class="dot" /><span class="line" /></div>
        <div v-if="report.metrics.coverage?.needs_fix?.length" class="u-task" style="cursor: default">
          <div class="u-task-main">
            <div class="u-task-title" style="color: #b45309">🔧 待优化 {{ report.metrics.coverage.needs_fix.length }} 个</div>
            <div class="u-task-sub">{{ report.metrics.coverage.needs_fix.join('、') }}</div>
          </div>
        </div>
      </template>

      <!-- 逐句/建议列表 -->
      <div class="u-section-title" style="margin-top: 24px">Line by line</div>
      <template v-for="(s, i) in (report?.metrics.suggestions ?? []).slice(0, 6)" :key="i">
        <div class="u-task" style="cursor: default">
          <span class="u-icon-block" :style="{ background: ['#1E2B26', '#232044', '#16303A'][i % 3] }">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M9 18V6l10-2v12" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="16.5" cy="16" r="2.5" />
            </svg>
          </span>
          <div class="u-task-main">
            <div class="u-task-title">{{ s }}</div>
            <div class="u-task-sub">建议</div>
          </div>
        </div>
        <div v-if="i < Math.min((report?.metrics.suggestions?.length ?? 0), 6) - 1" class="u-dotline">
          <span class="dot" /><span class="line" />
        </div>
      </template>
      <div v-if="loaded === 'demo'" class="u-hint" style="margin-left: 0">
        本页为<b>形态演示</b>：M3 唱歌评分（音准/节奏/发音，docs/06 §9.4）接入后替换为真实数据；
        口语会话报告走真实数据（?reportId=）。当前评分卡数字为占位。
      </div>
      <div v-if="loaded === 'error'" class="u-error">{{ error }}</div>
    </div>
  </div>
</template>
