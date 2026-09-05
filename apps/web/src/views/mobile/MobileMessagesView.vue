<script setup lang="ts">
/**
 * 移动端 · 私信列表（2026-09-05 组长拍板：底部 tab「我的」→「私信」；演示帧）
 * 会话列表（演示数据，本地收发）；点击进 /m/messages/:id；M3 接真实消息流。
 */
import { ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import { createDemoConversations } from '@/data/messages-demo'
import '@/styles/mobile-uic.css'

const conversations = ref(createDemoConversations())

const toastText = ref('')
let toastTimer: ReturnType<typeof setTimeout> | null = null

function newMessage() {
  toastText.value = '新消息 · M3 上线'
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastText.value = ''
  }, 2200)
}
</script>

<template>
  <div class="u-phone">
    <div class="u-msg">
      <header class="u-msg__top">
        <h1 class="u-msg__title">私信</h1>
        <button class="u-x-act" type="button" title="新消息（演示）" aria-label="新消息" @click="newMessage">
          <MobileIcon name="mail" :size="18" />
        </button>
      </header>

      <RouterLink
        v-for="c in conversations"
        :key="c.id"
        :to="`/m/messages/${c.id}`"
        class="u-msg__row"
        :aria-label="`与 ${c.name} 的对话`"
      >
        <span class="u-msg__ava" :style="{ background: c.tint }">{{ c.name.slice(0, 1) }}</span>
        <span class="u-msg__body">
          <span class="u-msg__who">
            <strong>{{ c.name }}</strong>
            <time class="u-msg__time">{{ c.time }}</time>
          </span>
          <span class="u-msg__last">{{ c.lastMsg }}</span>
        </span>
        <span v-if="c.unread" class="u-msg__dot" aria-label="未读" />
      </RouterLink>
    </div>

    <div v-if="toastText" class="u-toast show"><span class="dot" aria-hidden="true" />{{ toastText }}</div>

    <MobileTabBar />
  </div>
</template>
