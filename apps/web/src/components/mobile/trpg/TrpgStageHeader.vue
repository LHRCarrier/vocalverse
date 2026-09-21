<script setup lang="ts">
/**
 * 酒馆 · 场景状态带（迁移自 ai4u StageHeader）：
 * 剧本名 + 场景氛围色条/色点 + HP/位置/持有/任务数 + AI 状态点（闲置/处理中/出错）+ 悬空徽章。
 * 纯展示组件（数据来自 TrpgState 快照事实），不做请求；样式在 mobile-uic.css §酒馆。
 */
import { computed } from 'vue'

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
    status: 'idle',
  },
)

const tone = computed(() => sceneTone(props.scene))
const atmosphere = computed(() => sceneAtmosphere(props.scene))
</script>

<template>
  <header class="t-stage" :class="`t-stage--${tone}`">
    <div class="t-stage__bar" aria-hidden="true" />
    <div class="t-stage__row">
      <div class="t-stage__title">
        <span class="t-stage__dot" :class="`t-stage__dot--${tone}`" aria-hidden="true" />
        <span class="t-stage__name">{{ campaignName }}</span>
        <span class="t-stage__scene">{{ scene || '未定场景' }}</span>
      </div>
      <div class="t-stage__meta">
        <span
          v-if="danglingCount > 0"
          class="t-chip t-chip--warn"
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
      </div>
    </div>
    <div class="t-stage__stats">
      <span v-if="hp" class="t-chip t-chip--hp">❤ HP {{ hp }}</span>
      <span v-if="activeTasks > 0" class="t-chip">⚔ 任务 {{ activeTasks }}</span>
      <span v-if="location" class="t-chip t-chip--wrap" :title="location">
        📍 {{ location }}
      </span>
      <span v-if="inventory" class="t-chip t-chip--wrap" :title="inventory">
        🎒 {{ inventory }}
      </span>
      <span class="t-stage__atmo">{{ atmosphere }}</span>
    </div>
  </header>
</template>
