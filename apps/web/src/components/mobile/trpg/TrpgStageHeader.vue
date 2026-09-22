<script setup lang="ts">
/**
 * 酒馆 · 副本任务卡（设计稿 local/trpg-redesign.html 的置顶 mission-deck）：
 * 暗色副本横幅（当前副本徽章 + 场景氛围 + 剧本名 + 场景 + 目标）+
 * 状态条（HP/待办数/坐标/悬空徽章/行囊标签/场景色点 + AI 状态点）。
 * 纯展示组件（数据来自 TrpgState 快照事实），不做请求；样式在 mobile-uic.css §酒馆。
 */
import { computed } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

import { sceneAtmosphere, sceneTone } from './segments'

const props = withDefaults(
  defineProps<{
    campaignName: string
    scene?: string | null
    hp?: string | null
    location?: string | null
    inventory?: string | null
    activeTasks?: number
    danglingCount?: number
    /** 当前首要任务（active 首条），横幅「目标」行 */
    goal?: string | null
    /** AI 状态：idle=空闲 busy=处理中 error=出错 */
    status?: 'idle' | 'busy' | 'error'
  }>(),
  {
    scene: null,
    hp: null,
    location: null,
    inventory: null,
    activeTasks: 0,
    danglingCount: 0,
    goal: null,
    status: 'idle',
  },
)

const tone = computed(() => sceneTone(props.scene))
const atmosphere = computed(() => sceneAtmosphere(props.scene))

/** HP 事实值：`12/12` → 68%；纯数字（无上限）→ 不画条（不编造分母） */
const hpPercent = computed(() => {
  const m = /^(\d+(?:\.\d+)?)\s*\/\s*(\d+(?:\.\d+)?)$/.exec((props.hp ?? '').trim())
  if (!m) return null
  const cur = Number(m[1])
  const max = Number(m[2])
  if (!Number.isFinite(cur) || !Number.isFinite(max) || max <= 0) return null
  return Math.max(0, Math.min(100, Math.round((cur / max) * 100)))
})

/** 行囊事实值 → 标签（中英文逗号/分号/顿号通吃） */
const inventoryTags = computed(() =>
  (props.inventory ?? '')
    .split(/[,;，；、]/)
    .map((s) => s.trim())
    .filter(Boolean),
)
</script>

<template>
  <header class="t-stage" :class="`t-stage--${tone}`">
    <div class="t-quest">
      <div class="t-quest__top">
        <span class="t-quest__badge">✦ 当前副本</span>
        <span class="t-quest__atmo">
          <MobileIcon name="wave" :size="12" />
          {{ atmosphere }}
        </span>
      </div>
      <div class="t-quest__titlerow">
        <span class="t-stage__dot" :class="`t-stage__dot--${tone}`" aria-hidden="true" />
        <span class="t-quest__title">{{ campaignName }}</span>
        <span class="t-quest__scene">{{ scene ? `场景 · ${scene}` : '未定场景' }}</span>
      </div>
      <div class="t-quest__goal">
        <span class="t-quest__goal-mark" aria-hidden="true">◈</span>
        <span><b>目标：</b>{{ goal || '自由探索（在主持台可添加任务）' }}</span>
      </div>
    </div>

    <div class="t-strip">
      <span v-if="hp" class="t-strip__hp">
        <span>❤ HP {{ hp }}</span>
        <span v-if="hpPercent != null" class="t-strip__bar" aria-hidden="true">
          <span class="t-strip__bar-fill" :style="{ width: `${hpPercent}%` }" />
        </span>
      </span>
      <span v-if="activeTasks > 0" class="t-strip__pill">⚔ 待办 {{ activeTasks }}</span>
      <span v-if="location" class="t-strip__pill t-strip__pill--wrap" :title="location">
        📍 {{ location }}
      </span>
      <span
        v-if="danglingCount > 0"
        class="t-strip__pill t-strip__pill--warn"
        :title="`${danglingCount} 项悬空（超窗未推进）`"
      >
        ⚠ {{ danglingCount }} 悬空
      </span>
      <span
        class="t-stage__ai"
        :class="`t-stage__ai--${status}`"
        role="status"
        :aria-label="status === 'busy' ? 'DM 处理中' : status === 'error' ? '出错了' : 'DM 就绪'"
      />
      <div v-if="inventoryTags.length" class="t-strip__inv">
        <span class="t-strip__inv-label">🎒 行囊:</span>
        <span v-for="tag in inventoryTags" :key="tag" class="t-strip__inv-tag">{{ tag }}</span>
      </div>
    </div>
  </header>
</template>
