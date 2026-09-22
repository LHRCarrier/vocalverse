<script setup lang="ts">
/**
 * 酒馆 · 尾声卡（docs/56 §6）：结局标题 + 档位徽标 + 正文 + 后日谈。
 * 系统卡分支渲染（`trpg_sys="ending"`）：同回合走 SSE，刷新后从消息 payload 恢复。
 */
import { computed } from 'vue'

import { readEndingPayload } from '@/composables/useTavernQuest'

const props = defineProps<{ payload?: Record<string, unknown> | null }>()

const ending = computed(() => readEndingPayload(props.payload ?? null))
const OUTCOME_LABELS = { strong: '圆满结局', weak: '尘埃落定', miss: '遗憾收场' } as const
</script>

<template>
  <section v-if="ending" class="t-ending" :class="`t-ending--${ending.outcome}`" aria-label="尾声">
    <div class="t-ending__kicker">✦ 尾声 · {{ ending.quest }}</div>
    <div class="t-ending__head">
      <span class="t-ending__badge">{{ OUTCOME_LABELS[ending.outcome] }}</span>
      <span class="t-ending__title">{{ ending.title }}</span>
    </div>
    <p class="t-ending__text">{{ ending.text }}</p>
    <p v-if="ending.epilogue" class="t-ending__epilogue">{{ ending.epilogue }}</p>
  </section>
  <div v-else class="t-scene-line">—— 尾声 · {{ payload?.quest ?? '未知任务' }} ——</div>
</template>
