<script setup lang="ts">
/**
 * 酒馆 · 底部控制区（设计稿 dock-control + bottom-nav 一体的页脚）：
 * 推荐行动 chips / 骰钮 / 文本 / 语音（ASR）/ 发送 + 页内 4 项导航。
 * 页内底栏的占位项（大堂/角色卡/纪事）在此用全局 toast 提示；「酒馆跑团」= 滚到最新消息。
 * 沉浸页：全局底栏已移出（MobileTabBar group=null），本区贴 .u-phone 底边。
 */
import { useUiStore } from '@/stores/ui'

import TrpgActionDock from './TrpgActionDock.vue'
import TrpgGameNav from './TrpgGameNav.vue'

defineProps<{ sending: boolean; recording: boolean }>()

const emit = defineEmits<{
  send: [text: string]
  'toggle-mic': []
  roll: []
}>()

const ui = useUiStore()
const NAV_LABELS = { hall: '大堂', card: '角色卡', chronicle: '纪事' } as const

function onNav(key: 'hall' | 'tavern' | 'card' | 'chronicle') {
  if (key === 'tavern') {
    window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'smooth' })
    return
  }
  ui.showToast(`「${NAV_LABELS[key]}」后续版本开放`)
}
</script>

<template>
  <div class="u-chat-dock">
    <TrpgActionDock
      :sending="sending"
      :recording="recording"
      :max-seconds="30"
      @send="emit('send', $event)"
      @toggle-mic="emit('toggle-mic')"
      @roll="emit('roll')"
    />
  </div>
  <TrpgGameNav @nav="onNav" />
</template>
