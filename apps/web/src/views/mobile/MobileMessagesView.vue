<script setup lang="ts">
/**
 * 移动端 · 私信列表（真实 IM · docs/49 §2/§4 · 2026-09-10）
 * 会话列表来自 Java `/api/v1/community/messages/conversations`（对端 + 最后一条 + 未读）；
 * 点击进 /m/messages/:id。下拉刷新；长连（SSE）在通知中心私信 tab / 会话页建立，本页只读列表。
 */
import { onMounted } from 'vue'

import IconMail from '~icons/tabler/mail'
import IconSettings from '~icons/tabler/settings'

import { authorDisplay, timeAgo } from '@/api/community'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useMessagesStore } from '@/stores/messages'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const messages = useMessagesStore()
const ui = useUiStore()

onMounted(() => {
  void messages.loadConversations()
})

function newMessage() {
  // 发起会话入口登记 S4（docs/49 §4.4）：本轮只能从关注/通知侧进入已有会话
  ui.showToast('发起新会话 · 后续版本')
}

function messageSettings() {
  ui.showToast('私信设置 · 后续版本')
}

function unreadText(n: number): string {
  return n > 99 ? '99+' : String(n)
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="私信">
      <template #actions>
        <button class="u-topbar__act" type="button" title="新消息" aria-label="新消息" @click="newMessage">
          <IconMail />
        </button>
        <button class="u-topbar__act" type="button" title="私信设置" aria-label="私信设置" @click="messageSettings">
          <IconSettings />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-msg">
      <p v-if="messages.listError" class="u-note u-notif__demo">{{ messages.listError }}</p>
      <p v-else-if="!messages.loadingList && !messages.conversations.length" class="u-note u-notif__demo">
        还没有私信。在「关注」里找到同学，互动后即可开始聊天。
      </p>
      <RouterLink
        v-for="c in messages.conversations"
        :key="c.peer.id"
        :to="`/m/messages/${c.peer.id}`"
        class="u-msg__row"
        :aria-label="`与 ${c.peer.nickname} 的对话`"
      >
        <span class="u-msg__ava" :style="{ background: c.peer.tint ?? '#37546e' }">
          {{ c.peer.nickname.slice(0, 1) }}
        </span>
        <span class="u-msg__body">
          <span class="u-msg__who">
            <strong>{{ c.peer.nickname }}<span class="u-msg__lv">LV{{ c.peer.level.slice(1) }}</span></strong>
            <time class="u-msg__time">{{ timeAgo(c.lastCreatedAt) }}</time>
          </span>
          <span class="u-msg__last">
            <template v-if="c.lastMine">我：</template>{{ c.lastBody }}
          </span>
          <span v-if="authorDisplay(c.peer.handle)" class="u-msg__last">{{ authorDisplay(c.peer.handle) }}</span>
        </span>
        <span v-if="c.unreadCount > 0" class="u-msg__unread" :aria-label="`${c.unreadCount} 条未读`">
          {{ unreadText(c.unreadCount) }}
        </span>
      </RouterLink>
    </div>
  </div>
</template>
