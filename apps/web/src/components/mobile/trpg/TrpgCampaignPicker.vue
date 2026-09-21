<script setup lang="ts">
/**
 * 酒馆 · 剧本切换抽屉（顶栏「切换剧本」入口）：
 * 列表切换 / 新建（走场景卡抽屉）/ 重开本剧本（清空对话流水，事实保留）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { TrpgCampaignItem } from '@/api/trpg'

const props = withDefaults(
  defineProps<{
    open: boolean
    campaigns: TrpgCampaignItem[]
    currentId: number | null
  }>(),
  { currentId: null },
)

const emit = defineEmits<{
  close: []
  switch: [id: number]
  'new-campaign': []
  restart: []
}>()
</script>

<template>
  <div v-if="props.open" class="t-sheet">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-sheet__panel t-sheet__panel--short" role="dialog" aria-label="选择剧本">
      <header class="t-sheet__head">
        <div class="t-sheet__title">我的剧本</div>
        <button
          class="t-sheet__close"
          type="button"
          title="关闭"
          aria-label="关闭"
          @click="emit('close')"
        >
          <MobileIcon name="x" :size="18" />
        </button>
      </header>
      <div class="t-sheet__body">
        <button
          v-for="c in props.campaigns"
          :key="c.id"
          class="t-pick"
          :class="{ 'is-on': c.id === props.currentId }"
          type="button"
          @click="emit('switch', c.id)"
        >
          {{ c.name }}
        </button>
        <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="emit('new-campaign')">
          ＋ 用场景卡开新局
        </button>
        <button class="u-btn u-btn--outline u-btn--block" type="button" @click="emit('restart')">
          重开本剧本（清空对话）
        </button>
      </div>
    </section>
  </div>
</template>
