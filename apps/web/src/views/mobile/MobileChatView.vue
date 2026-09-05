<script setup lang="ts">
/**
 * 移动端 · 私信会话（演示帧：气泡 + 本地收发；发送 1.2s 后对方演示自动回复）
 * M3 接真实消息流（只换数据源，组件层不返工）。
 */
import { nextTick, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { createDemoConversations, type DemoMessage } from '@/data/messages-demo'
import '@/styles/mobile-uic.css'

const route = useRoute()
const convId = Number(route.params.id)
const conv = createDemoConversations().find((c) => c.id === convId)

const title = conv?.name ?? '私信'
const tint = conv?.tint ?? '#1c1c1a'
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
      <RouterLink to="/m/messages" class="u-back" title="返回私信" aria-label="返回私信">
        <MobileIcon name="back" :size="18" />
      </RouterLink>
      <span class="u-chat__ava" :style="{ background: tint }">{{ title.slice(0, 1) }}</span>
      <strong class="u-chat__name">{{ title }}</strong>
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
