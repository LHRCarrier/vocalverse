<script setup lang="ts">
/**
 * 跟唱评分报告（2026-09-22 从 `MobileSingView.vue` 抽出，深色录唱页的一部分）。
 *
 * 抽出的原因：视图受 eslint `max-lines 350` 门禁，深色重做要在面板里加不少标记；
 * 顺带把「D3 对齐图怎么挂」收敛到组件内部——**P1-8 的模板 ref 口径不变**
 * （不用 `document.getElementById` + 定时器：面板关闭时结果落地曾导致图表区永久空盒）。
 */
import { nextTick, onMounted, ref, watch } from 'vue'

import type { SongDetail, SingAttemptResult } from '@/api/sing'
import { renderSingChart } from '@/lib/sing-chart'

const props = defineProps<{
  detail: SongDetail | null
  result: SingAttemptResult
  /** 有效句数（v4 口径：未评测句不计入综合） */
  evaluatedCount: number
  expectedCount: number
}>()

const emit = defineEmits<{ (e: 'back'): void }>()

/** 报告图容器（模板 ref：结果落地时元素必须已经存在） */
const chartEl = ref<HTMLElement | null>(null)

const scoreColor = (v: number | null | undefined) =>
  v == null ? '#999' : v >= 85 ? '#18a058' : v >= 60 ? '#f2a43a' : '#d03050'

async function drawChart() {
  if (!chartEl.value || !props.detail) return
  await nextTick()
  await new Promise((r) => setTimeout(r, 60))
  if (chartEl.value) renderSingChart(chartEl.value, props.detail, props.result)
}

onMounted(drawChart)
watch(() => [props.result, props.detail], drawChart, { flush: 'post' })
</script>

<template>
  <div class="m-sing-report">
    <div class="m-sing-report__score">
      <span class="m-sing-report__num">{{ result.overall?.toFixed(1) ?? '—' }}</span>
      <span class="m-sing-report__label">综合分</span>
    </div>
    <div class="m-sing-report__sub">
      <span>音准 {{ result.pitch?.toFixed(1) ?? '—' }}</span>
      <span>节奏 {{ result.rhythm?.toFixed(1) ?? '—' }}</span>
      <span>发音 {{ result.pron?.toFixed(1) ?? '—' }}</span>
    </div>
    <div ref="chartEl" class="m-sing-chart" />
    <div class="m-sing-report__lines">
      <div v-for="(l, i) in result.lines" :key="l.seq" class="m-sing-line">
        <span class="m-sing-line__text">
          {{ i + 1 }}.
          <template v-if="l.skipped">未评测（{{ l.reason ?? 'skipped' }}）</template>
          <template v-else-if="l.onset_dev_ms != null">起唱偏差 {{ Math.round(l.onset_dev_ms) }}ms</template>
          <template v-else>✓</template>
        </span>
        <span class="m-sing-line__score">
          <b :style="{ color: scoreColor(l.pitch_score) }">{{ l.pitch_score?.toFixed(0) ?? '—' }}</b>
          <i :style="{ color: scoreColor(l.rhythm_score) }">{{ l.rhythm_score?.toFixed(0) ?? '—' }}</i>
        </span>
      </div>
    </div>
    <!-- 有效句 + v3/v4 提示（音域/在调音符/覆盖率置信度；docs/06 §9.4） -->
    <div class="m-sing-sheet__hint" style="margin: 8px 0">
      有效句 {{ evaluatedCount }}/{{ expectedCount }}
      <template v-if="evaluatedCount < expectedCount">
        · 未评测 {{ expectedCount - evaluatedCount }} 句（无音高/参考缺失/有效帧不足），综合按有效句均分（docs/06 §9.4 D5）
      </template>
      <template v-if="result.alignment?.range_hint"> · {{ result.alignment.range_hint }}</template>
      <template v-if="result.alignment?.note_hit_rate != null">
        · 在调音符 {{ Math.round((result.alignment.note_hit_rate ?? 0) * 100) }}%（未唱到的音符按比例扣减音准分）
      </template>
    </div>
    <div v-if="result.alignment?.coverage_note" class="m-sing-sheet__hint" style="color: #ff8fa3; margin: 8px 0">
      {{ result.alignment.coverage_note }}
    </div>
    <button class="u-btn u-btn--ghost m-sing-report__back" type="button" @click="emit('back')">
      返回歌单
    </button>
  </div>
</template>
