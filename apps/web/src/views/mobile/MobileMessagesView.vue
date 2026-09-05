<script setup lang="ts">
/**
 * 移动端 · 私信列表（2026-09-05 组长拍板：底部 tab「我的」→「私信」；演示帧）
 * 会话列表（演示数据，本地收发）；点击进 /m/messages/:id；M3 接真实消息流。
 * 顶栏 = MobileTopBar（全局头像/「私信」/新消息 + 私信设置）。
 */
import { ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { createDemoConversations } from '@/data/messages-demo'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const conversations = ref(createDemoConversations())
const ui = useUiStore()

function newMessage() {
  ui.showToast('新消息 · M3 上线')
}

function messageSettings() {
  ui.showToast('私信设置 · M3 上线')
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="私信">
      <template #actions>
        <button class="u-topbar__act" type="button" title="新消息（演示）" aria-label="新消息" @click="newMessage">
          <MobileIcon name="mail" :size="18" />
        </button>
        <button class="u-topbar__act" type="button" title="私信设置（演示）" aria-label="私信设置" @click="messageSettings">
          <MobileIcon name="settings" :size="18" />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-msg">
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

    <MobileTabBar />
  </div>
</template>
