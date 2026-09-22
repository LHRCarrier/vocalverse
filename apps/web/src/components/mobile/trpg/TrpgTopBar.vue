<script setup lang="ts">
/**
 * 酒馆 · 顶栏（封装 MobileTopBar 的按钮编排，控制酒馆页文件行数 fe-08）：
 * 2026-09-21 组长反馈「标题居中 + 功能项可放左」+ 2026-09-22 设计稿新增「角色立绘」入口。
 * 游玩态：左 酒馆印章（= 立绘入口，设计稿 tavern-seal）/ 设置 · 右 切换剧本 / 主持台 / 离开；
 * 其余态：左 设置 · 右 场景卡 / 离开（无剧本时无角色可看，立绘钮不渲染）。
 * 2026-09-22 组长复验：印章一度去掉、后按组长要求加回（图标与页内「酒馆跑团」tab 同源 stack-2）。
 * 场景卡在游玩态收敛进「切换剧本」抽屉的「＋ 用场景卡开新局」（docs/35 规则 5 唯一入口）。
 * 出口固定在右侧末位「离开」钮（docs/35 硬规则 3）。
 */
import IconAdjustments from '~icons/tabler/adjustments'
import IconSettings from '~icons/tabler/settings'
import IconStack2 from '~icons/tabler/stack-2'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'

const props = defineProps<{ stage: 'loading' | 'onboarding' | 'play' | 'error' }>()

const emit = defineEmits<{
  leave: []
  settings: []
  cards: []
  picker: []
  console: []
  standee: []
}>()
</script>

<template>
  <MobileTopBar title="酒馆" back @back="emit('leave')">
    <template #left>
      <!-- 酒馆印章（设计稿 tavern-seal）：暗茶圆 + 琥珀环 + 三层图标 + 在线点，点击开立绘 -->
      <button
        v-if="props.stage === 'play'"
        class="u-topbar__act"
        type="button"
        title="角色立绘"
        aria-label="角色立绘"
        @click="emit('standee')"
      >
        <span class="t-seal">
          <IconStack2 />
          <span class="t-seal__dot" aria-hidden="true" />
        </span>
      </button>
      <button
        class="u-topbar__act"
        type="button"
        title="酒馆设置"
        aria-label="酒馆设置"
        @click="emit('settings')"
      >
        <IconSettings />
      </button>
    </template>
    <template #actions>
      <button
        v-if="props.stage !== 'play'"
        class="u-topbar__act"
        type="button"
        title="场景卡"
        aria-label="场景卡"
        @click="emit('cards')"
      >
        <MobileIcon name="star" :size="20" />
      </button>
      <template v-if="props.stage === 'play'">
        <button
          class="u-topbar__act"
          type="button"
          title="切换剧本"
          aria-label="切换剧本"
          @click="emit('picker')"
        >
          <MobileIcon name="book" :size="20" />
        </button>
        <button
          class="u-topbar__act"
          type="button"
          title="主持台"
          aria-label="主持台"
          @click="emit('console')"
        >
          <IconAdjustments />
        </button>
      </template>
    </template>
  </MobileTopBar>
</template>
