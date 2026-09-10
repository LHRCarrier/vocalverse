<script setup lang="ts">
/**
 * 唱吧歌单行（MobileSingView 专用 · 2026-09-10）：
 * 主点击区（图标块 + 歌名/副文 + 就绪状态）+ **收藏按钮**（点一下收藏，再点一次取消）。
 *
 * - 两颗独立 button（原来的整行 button 无法内嵌按钮——嵌套 button 是无效 HTML，
 *   且触摸端无法区分「点行去跟唱」与「点收藏」）；
 * - 收藏态/就绪状态由父组件透传（`song.favorited` 来自服务端），点击经 emit 回父级，
 *   本组件不持状态（单一数据源在 useSingPlay.songs）。
 */
import { computed } from 'vue'

import MobileIcon from './MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

const props = defineProps<{ song: SongSummary }>()
const emit = defineEmits<{ open: [number]; favorite: [SongSummary] }>()

/** 就绪状态徽标（success/star/neutral 与 u-badge 变体同源） */
const badge = computed(() => {
  const map: Record<string, { text: string; variant: 'success' | 'star' | 'neutral' }> = {
    ready: { text: '就绪', variant: 'success' },
    building: { text: '提取中', variant: 'neutral' },
    invalid: { text: '提取失败', variant: 'neutral' },
  }
  return map[props.song.pitch_ref_status] ?? { text: '未就绪', variant: 'neutral' }
})

/** 右侧关键值（跟唱可用性一句话口径；`missing` 等未列状态回落「未就绪」） */
const VERDICTS: Record<string, string> = {
  ready: '可跟唱',
  building: '提取中',
  invalid: '提取失败',
}
const verdict = computed(() => VERDICTS[props.song.pitch_ref_status] ?? '未就绪')
</script>

<template>
  <div class="u-item m-sing-row">
    <button class="m-sing-row__hit" type="button" @click="emit('open', song.id)">
      <span class="u-icon-block" :style="{ background: song.level <= 2 ? '#1E2B26' : '#16303A' }">
        <MobileIcon :name="song.level <= 2 ? 'headphone' : 'note'" :size="22" />
      </span>
      <span class="u-item__main">
        <span class="u-item__title">{{ song.title }}</span>
        <span class="u-item__sub">
          {{ song.artist ?? '歌单' }} · {{ song.expected_lines }} 句 · 难度 L{{ song.level }}
        </span>
      </span>
      <span class="u-item__right">
        <span class="u-item__value" :class="{ 'u-item__value--ink': song.pitch_ref_status !== 'ready' }">
          {{ verdict }}
        </span>
        <span class="u-badge" :class="`u-badge--${badge.variant}`">{{ badge.text }}</span>
      </span>
    </button>
    <button
      class="m-sing-fav"
      :class="{ 'is-on': song.favorited }"
      type="button"
      :aria-pressed="song.favorited"
      :aria-label="song.favorited ? `取消收藏 ${song.title}` : `收藏 ${song.title}`"
      :title="song.favorited ? '取消收藏' : '收藏'"
      @click="emit('favorite', song)"
    >
      <MobileIcon name="heart" :size="20" />
    </button>
  </div>
</template>
