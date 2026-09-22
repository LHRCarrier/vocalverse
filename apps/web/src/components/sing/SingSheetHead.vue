<script setup lang="ts">
/**
 * 跟唱面板顶栏（2026-09-22 深色录唱页重做）：关闭钮 + **实时评级条** + 模式 chip + 录音进度线。
 *
 * 参考图顶栏是「返回 + 橙色评级条（A 2.63）+ 模式（经典 ···）」；我们**不新造指标**——
 * 评级由现有实时分（`lib/live-score.ts`：近 5 秒在调率 × 出声率）经 `lib/sing-grade.ts`
 * 映射成 S/A/B/C/D，分数段与 `live-chart.scoreColorOf` 的 85/60 阈值同源，保证「同分同色」。
 * 角标文案固定「练习参考 · 以离线评分为准」：实时分不参与离线评分（docs/06 §9.4）。
 *
 * 抽组件的原因不变：视图受 eslint `max-lines 350` 门禁（与 `SingActionBar` 同款处置）。
 */
import { computed } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { formatClock } from '@/lib/sing-lyrics'
import { gradeOf, gradeProgress } from '@/lib/sing-grade'

const props = defineProps<{
  /** 歌名（仅用于无障碍名：视觉上的大标题在面板正文里） */
  title: string
  /** 实时分（0~100；null = 参考不足/未出声 → 占位） */
  score: number | null
  /** 模式 chip 文案：「跟唱」/「原唱中」/「暂停中」 */
  modeText: string
  /** 录音中（决定进度线是否显示；暂停中仍算录音中） */
  recording: boolean
  /** 暂停中（chip 变色） */
  paused: boolean
  /** 已录音时长（ms，整秒量化） */
  elapsedMs: number | null
  /** 单次录音上限（ms）——与 `recorder.start()` 同源 */
  maxMs: number
}>()

const emit = defineEmits<{ (e: 'close'): void }>()

const grade = computed(() => gradeOf(props.score))
const progress = computed(() => gradeProgress(props.score))
/** 无障碍/长按：把「这是什么分」讲清楚（练习参考口径） */
const gradeTitle = computed(
  () => `实时分 ${props.score ?? '—'}（近 5 秒在调率×出声率 · 练习参考，最终以离线分析为准）`,
)
/** 录音进度（0~1）：已录 / 上限 */
const recProgress = computed(() => {
  const cap = props.maxMs
  if (!cap || cap <= 0 || props.elapsedMs == null) return 0
  return Math.min(1, Math.max(0, props.elapsedMs / cap))
})
const elapsedText = computed(() => formatClock(props.elapsedMs ?? 0))
</script>

<template>
  <header class="m-sing-top">
    <button class="m-sing-top__back" type="button" aria-label="关闭" @click="emit('close')">
      <MobileIcon name="chevron" :size="20" style="transform: rotate(90deg)" />
    </button>

    <!-- 评级条：字母 + 进度（宽度 = 实时分/100；不是歌曲进度） -->
    <div class="m-sing-grade" :title="gradeTitle" :aria-label="gradeTitle" role="img">
      <span
        class="m-sing-grade__letter"
        :style="{ color: grade ? grade.color : 'rgba(255,255,255,.42)' }"
      >{{ grade ? grade.letter : '—' }}</span>
      <span class="m-sing-grade__track">
        <span
          class="m-sing-grade__fill"
          :style="{ transform: `scaleX(${progress})`, background: grade ? grade.color : '#f5a524' }"
        />
      </span>
      <span class="m-sing-grade__num">{{ score == null ? '—' : Math.round(score) }}</span>
    </div>

    <span
      class="m-sing-top__mode"
      :class="{ 'is-paused': paused, 'is-live': recording && !paused }"
    >{{ modeText }}</span>

    <!-- 录音进度线（3 分钟上限；已录时长同时显示在底部一行） -->
    <span
      v-if="recording"
      class="m-sing-top__recbar"
      :style="{ transform: `scaleX(${recProgress})` }"
      :aria-label="`已录音 ${elapsedText}`"
      aria-hidden="true"
    />
  </header>
</template>
