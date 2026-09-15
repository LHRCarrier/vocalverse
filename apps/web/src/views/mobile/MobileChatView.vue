<script setup lang="ts">
/**
 * 移动端 · 私信会话（真实 IM · docs/49 §2/§3/§4 · 2026-09-10）
 *
 * - 历史：`GET /api/v1/community/messages/{peerId}`（keyset 倒序 → 本地升序展示，向上翻页取更早）；
 * - 实时：SSE 长连（`/messages/stream`，`since` 游标断线回放）；不可用/超限自动降级 3s 轮询；
 * - 已读：进入会话 / 收到新消息 / 离开时用 `upTo`（已渲染的最后一条对端消息 id）上报，**不用请求时刻**；
 * - 气泡骨架沿用 u-chat__*（docs/35 SOP：类名不跨语义复用，容器仍为 u-chat-page）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import IconInfoCircle from '~icons/tabler/info-circle'

import { timeAgo } from '@/api/community'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useMessagesStore } from '@/stores/messages'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()
const messages = useMessagesStore()

const peerId = Number(route.params.id)
const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

const peer = computed(() => messages.conversations.find((c) => c.peer.id === peerId)?.peer ?? null)
const title = computed(() => peer.value?.nickname ?? '私信')
const level = computed(() => peer.value?.level ?? '')
const avatarLetter = computed(() =>
  (auth.me?.nickname ?? auth.me?.username ?? '同').slice(0, 1).toUpperCase(),
)

function scrollBottom(behavior: ScrollBehavior = 'auto') {
  void nextTick(() => listEl.value?.scrollTo({ top: listEl.value.scrollHeight, behavior }))
}

async function send() {
  const text = draft.value.trim()
  if (!text) return
  draft.value = ''
  const ok = await messages.send(peerId, text)
  if (ok) scrollBottom('smooth')
}

/** 新消息到达（含实时/轮询/自己发送）→ 贴底 */
watch(
  () => messages.sortedThread.length,
  () => scrollBottom('smooth'),
)

onMounted(async () => {
  if (!Number.isFinite(peerId) || peerId <= 0) {
    ui.showToast('会话不存在')
    void router.replace('/m/messages')
    return
  }
  // 列表可能未加载（直接深链进入）→ 先补一次，拿到对端昵称/等级
  if (!messages.conversations.length) await messages.loadConversations()
  await messages.openThread(peerId)
  scrollBottom()
  messages.startStream()
  await messages.markRead(peerId)
})

onUnmounted(() => {
  messages.closeThread()
})
</script>

<template>
  <div class="u-phone u-chat-page">
    <header class="u-chat__top">
      <button class="u-topbar__ava" type="button" title="账户菜单" aria-label="账户菜单" @click="ui.openDrawer()">
        {{ avatarLetter }}
      </button>
      <strong class="u-chat__name">
        {{ title }}<span v-if="level" class="u-msg__lv">LV{{ level.slice(1) }}</span>
      </strong>
      <button
        class="u-topbar__act"
        type="button"
        title="会话信息"
        aria-label="会话信息"
        @click="ui.showToast('会话信息 · 后续版本')"
      >
        <IconInfoCircle />
      </button>
    </header>

    <div ref="listEl" class="u-chat__list" aria-label="消息记录">
      <button
        v-if="messages.threadHasMore"
        class="u-note u-chat__more"
        type="button"
        :disabled="messages.threadLoading"
        @click="messages.loadMoreThread()"
      >
        {{ messages.threadLoading ? '加载中…' : '查看更早的消息' }}
      </button>
      <p v-if="messages.threadError" class="u-note u-notif__demo">{{ messages.threadError }}</p>
      <p v-else-if="!messages.thread.length && !messages.threadLoading" class="u-note u-notif__demo">
        还没有消息，打个招呼吧。
      </p>
      <div
        v-for="m in messages.sortedThread"
        :key="m.id"
        class="u-chat__row"
        :class="m.mine ? 'is-me' : 'is-them'"
      >
        <span class="u-chat__bubble">{{ m.body }}</span>
        <time class="u-chat__time">{{ timeAgo(m.createdAt) }}</time>
      </div>
    </div>

    <footer class="u-chat__bar">
      <input
        v-model="draft"
        class="u-chat__input"
        type="text"
        maxlength="1000"
        placeholder="输入消息…"
        aria-label="消息内容"
        @keydown.enter="send"
      >
      <button class="u-chat__send" type="button" :disabled="!draft.trim()" aria-label="发送消息" @click="send">
        <MobileIcon name="arrow" :size="16" />
      </button>
    </footer>
  </div>
</template>
