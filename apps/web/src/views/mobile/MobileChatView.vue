<script setup lang="ts">
/**
 * 移动端 · 私信会话（演示帧：气泡 + 本地收发；发送 1.2s 后对方演示自动回复）
 * M3 接真实消息流（只换数据源，组件层不返工）。
 */
import { computed, nextTick, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { createDemoConversations, type DemoMessage } from '@/data/messages-demo'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()
const auth = useAuthStore()
const convId = Number(route.params.id)
const conv = createDemoConversations().find((c) => c.id === convId)

const title = conv?.name ?? '私信'
const avatarLetter = computed(() => (auth.me?.nickname ?? auth.me?.username ?? '同').slice(0, 1).toUpperCase())
const messages = ref<DemoMessage[]>(conv ? conv.history.map((m) => ({ ...m })) : [])
const draft = ref('')
const listEl = ref<HTMLElement | null>(null)

let replyIndex = 0
let replyTimer: ReturnType<typeof setTimeout> | undefined

function scrollBottom() {
  void nextTick(() => listEl.value?.scrollTo({ top: listEl.value.scrollHeight }))
}

function nextReply(): string | undefined {
  const pool = conv?.replies ?? []
  if (!pool.length) return undefined
  const r = pool[replyIndex % pool.length]
  replyIndex += 1
  return r
}

function send() {
  const text = draft.value.trim()
  if (!text) return
  messages.value.push({ from: 'me', text, time: '刚刚' })
  draft.value = ''
  scrollBottom()
  const reply = nextReply()
  if (reply) {
    replyTimer = setTimeout(() => {
      messages.value.push({ from: 'them', text: reply, time: '刚刚' })
      scrollBottom()
    }, 1200)
  }
}

onUnmounted(() => clearTimeout(replyTimer))
</script>

<template>
  <div class="u-phone u-chat">
    <header class="u-chat__top">
      <button class="u-topbar__back" type="button" title="返回私信" aria-label="返回私信" @click="router.push('/m/messages')">
        <MobileIcon name="back" :size="18" />
      </button>
      <button class="u-topbar__ava" type="button" title="账户菜单" aria-label="账户菜单" @click="ui.openDrawer()">
        {{ avatarLetter }}
      </button>
      <strong class="u-chat__name">{{ title }}</strong>
      <button
        class="u-topbar__act"
        type="button"
        title="会话信息（演示）"
        aria-label="会话信息"
        @click="ui.showToast('会话信息 · M3 上线')"
      >
        <MobileIcon name="info" :size="18" />
      </button>
    </header>

    <div ref="listEl" class="u-chat__list" aria-label="消息记录">
      <div v-for="(m, i) in messages" :key="i" class="u-chat__row" :class="m.from === 'me' ? 'is-me' : 'is-them'">
        <span class="u-chat__bubble">{{ m.text }}</span>
        <time class="u-chat__time">{{ m.time }}</time>
      </div>
    </div>

    <footer class="u-chat__bar">
      <input
        v-model="draft"
        class="u-chat__input"
        type="text"
        maxlength="200"
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
