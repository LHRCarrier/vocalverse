<script setup lang="ts">
/**
 * 社区卡片 · 单媒体兼容层（docs/34 §4；S1 调用点不破）
 *
 * 2026-09-09（社区 S3）：真正的渲染已下沉到 `MobileMediaGrid`（多图宫格 + 视频封面），
 * 本组件保留原 props 形状（`media` / `kind` / `durationS`）作为兼容壳：
 * 老调用点无需改，新代码直接用 `MobileMediaGrid`。
 *
 * `normalizeMedia()` 兼容三种历史形状（S1 种子 `duration_s` / S1 真实 `url` / S3 `items[]`，
 * docs/48 B8）——修复前前端只读 `durationS`，种子视频的时长角标一直是空的。
 */
import { computed } from 'vue'

import MobileMediaGrid from '@/components/mobile/MobileMediaGrid.vue'
import { useUiStore } from '@/stores/ui'
import { normalizeMedia } from '@/types/community'

import type { CommunityPostView, PostMedia } from '@/types/community'

const props = withDefaults(
  defineProps<{
    media: PostMedia | null
    kind: CommunityPostView['kind']
    tintGradient: string
    durationS?: number | null
    /** 列表卡：只渲首图 + 「+N」角标 */
    compact?: boolean
  }>(),
  { compact: false, durationS: null },
)

const ui = useUiStore()

const normalized = computed(() => {
  const m = normalizeMedia(props.media, props.kind)
  // 兼容旧调用点传入的 durationS 覆盖（S1 的 MobilePostCard 曾显式传它）
  return props.durationS != null ? { ...m, durationS: props.durationS } : m
})

/** 列表卡点视频：进详情页播放（不再弹「S3 上线」占位 toast） */
function onPlay() {
  if (props.compact) ui.showToast('打开内容即可播放')
}
</script>

<template>
  <MobileMediaGrid
    :media="normalized"
    :compact="props.compact"
    :tint-gradient="props.tintGradient"
    @play="onPlay"
  />
</template>
