<script setup lang="ts">
/**
 * 移动端评分报告页（UI 先行 · 逐项对齐原型源码 examples/app/report.html）
 * 默认 = 原型演示帧（report.html 逐项复制，数据字段打【占位】注释）；
 * 后置功能：?reportId= 时接真实口语报告（docs/14 §3.1 metrics），不破坏原型视觉。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchReport, type ReportPayload } from '@/api/practice'
import '@/styles/mobile-uic.css'

const route = useRoute()
const router = useRouter()

const report = ref<ReportPayload | null>(null)
const loaded = ref<'idle' | 'loading' | 'ok' | 'error'>('idle')
const error = ref<string | null>(null)

onMounted(async () => {
  const id = Number(route.query.reportId)
  if (!id) return // 无 reportId → 原型演示帧
  loaded.value = 'loading'
  try {
    report.value = await fetchReport(id)
    loaded.value = 'ok'
  } catch (e) {
    error.value = (e as Error).message
    loaded.value = 'error'
  }
})

/* ---------- 原型演示帧（report.html 逐项；接入后替换） ---------- */
// 【占位·M3】歌曲报告：Perfect Night · LE SSERAFIM · 12-16 20:15（原型演示值）
// 【占位·M3】总分 92.4 / Pitch 93 · Rhythm 91 · Pronun 88 · Full 100%（原型演示值）
// 【占位·M3】逐句：3 行评分（原型演示值）
const demoLines = [
  { lyric: 'You know I\'m just a girl...', comment: 'Pitch excellent, linking natural', score: '95', color: '#1E2B26', accent: true },
  { lyric: 'And I will always love you...', comment: 'Breath before chorus - slight early', score: '88', color: '#232044', accent: false },
  { lyric: 'I\'m yours, I\'m yours...', comment: 'Repeat section runs slightly ahead', score: '81', color: '#16303A', accent: false },
] as const
</script>

<template>
  <div class="u-phone">
    <div class="u-content">
      <!-- 头部（原型 .head） -->
      <header class="u-head" style="margin-bottom: 20px">
        <button class="u-back" type="button" title="返回" @click="router.back()">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
            <path d="M15 5l-7 7 7 7" />
          </svg>
        </button>
        <div style="flex: 1">
          <h1 style="font-size: 22px; font-weight: 700">{{ report ? 'Report' : 'Singing Report' }}</h1>
          <div style="font-size: 13px; color: var(--u-weak); margin-top: 3px">
            {{ report ? `会话 #${route.query.reportId}` : 'Perfect Night · LE SSERAFIM · 12-16 20:15' }}
          </div>
        </div>
      </header>

      <!-- 深紫评分卡（原型 .hero） -->
      <section class="u-hero">
        <div class="art" aria-hidden="true">
          <svg viewBox="0 0 320 340" fill="none" stroke="rgba(255,255,255,.85)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M196 28 L 196 184" /><path d="M196 28 C 196 28 232 40 252 60 C 262 70 264 92 250 102" />
            <ellipse cx="186" cy="196" rx="34" ry="26" /><ellipse cx="250" cy="118" rx="30" ry="24" />
            <path d="M110 96 L 88 128 M96 72 L 70 96" stroke-width="2" />
          </svg>
        </div>
        <span class="u-chip">{{ report ? '完成' : 'New record' }}</span>
        <span class="time">{{ report ? '口语对话 · 已评分' : '107s · full song' }}</span>
        <h2>{{ report ? '会话报告' : 'Perfect Night' }}</h2>
        <p>{{ report?.metrics.summary ?? 'Beat 82% of learners. Keep it up.' }}</p>
        <RouterLink to="/m/home" style="text-decoration: none; display: inline-block">
          <button class="u-btn-ghost" type="button" style="pointer-events: none">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M4 13a8 8 0 0 1 16 0" /><rect x="3.5" y="13" width="4" height="6" rx="2" /><rect x="16.5" y="13" width="4" height="6" rx="2" />
            </svg>
            {{ report ? 'Back home' : 'Sing again' }}
          </button>
        </RouterLink>
        <div class="score">
          <div class="label">Total</div>
          <div class="num">{{ report ? '—' : '92.4' }}</div>
        </div>
      </section>

      <!-- 四维统计（原型 .metrics） -->
      <section class="u-metrics">
        <div class="u-m"><div class="u-m-label">Pitch</div><div class="u-m-value accent">93</div></div>
        <div class="u-m"><div class="u-m-label">Rhythm</div><div class="u-m-value">91</div></div>
        <div class="u-m"><div class="u-m-label">Pronun</div><div class="u-m-value">88</div></div>
        <div class="u-m"><div class="u-m-label">Full</div><div class="u-m-value">100%</div></div>
      </section>

      <!-- 真实数据分支（后置功能） -->
      <template v-if="report">
        <div class="u-section-title">Coverage</div>
        <div class="u-task" style="cursor: default">
          <div class="u-task-main">
            <div class="u-task-title" style="color: var(--u-success)">
              ✓ 已覆盖 {{ report.metrics.coverage?.covered?.length ?? 0 }} 个表达
            </div>
            <div class="u-task-sub">{{ report.metrics.coverage?.covered?.join('、') || '—' }}</div>
          </div>
        </div>
        <template v-if="report.metrics.suggestions?.length">
          <div class="u-section-title" style="margin-top: 24px">Line by line</div>
          <template v-for="(s, i) in report.metrics.suggestions.slice(0, 6)" :key="i">
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
            <div v-if="i < Math.min(report.metrics.suggestions?.length ?? 0, 6) - 1" class="u-dotline">
              <span class="dot" /><span class="line" />
            </div>
          </template>
        </template>
      </template>

      <!-- 原型演示帧：逐句评分（原型 .line 三行 + 点线） -->
      <div v-else>
        <div class="u-section-title">Line by line</div>
        <template v-for="(l, i) in demoLines" :key="i">
          <div class="u-line" :style="{ background: 'var(--u-card)', borderRadius: '20px', boxShadow: 'var(--u-shadow-card)' }">
            <span class="u-icon-block" :style="{ background: l.color, width: '44px', height: '44px', borderRadius: '14px' }">
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
                <path d="M9 18V6l10-2v12" /><circle cx="6.5" cy="18" r="2.5" /><circle cx="16.5" cy="16" r="2.5" />
              </svg>
            </span>
            <span class="u-task-main">
              <span class="u-line-lyric" style="font-size: 14px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block">{{ l.lyric }}</span>
              <span class="u-line-comment" style="font-size: 12px; color: var(--u-weak); margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block">{{ l.comment }}</span>
            </span>
            <span class="u-line-score" :class="{ accent: l.accent }" style="font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; color: l.accent ? 'var(--u-accent)' : 'var(--u-ink)'">{{ l.score }}</span>
          </div>
          <div v-if="i < demoLines.length - 1" class="u-dotline">
            <span class="dot" /><span class="line" />
          </div>
        </template>
      </div>

      <div v-if="loaded === 'error'" class="u-error">{{ error }}</div>
    </div>
  </div>
</template>
