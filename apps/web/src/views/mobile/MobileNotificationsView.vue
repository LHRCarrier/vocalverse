<script setup lang="ts">
/**
 * 移动端 · 通知中心（2026-09-09 组长反馈：消息收敛到通知——X 式一个入口 tab 分流）
 * Tab = 私信（会话列表，原 /m/messages 内容收敛进来）/ 通知（互动通知：点赞/评论/关注/系统）。
 * 私信会话点击 → /m/messages/:id（保留）；M3 接真实通知流（埋点事件派生）。
 * 2026-09-09 v2 组长反馈：tab 均分整行居中（X 式）；通知行图标统一 Tabler（与底栏同款）。
 */
import { ref } from 'vue'

import IconHeart from '~icons/tabler/heart'
import IconInfoCircle from '~icons/tabler/info-circle'
import IconMail from '~icons/tabler/mail'
import IconMessageCircle from '~icons/tabler/message-circle'
import IconSettings from '~icons/tabler/settings'
import IconUserPlus from '~icons/tabler/user-plus'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { createDemoConversations } from '@/data/messages-demo'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const tabs = ['私信', '通知'] as const
const activeTab = ref<(typeof tabs)[number]>('私信')

const ui = useUiStore()
const conversations = ref(createDemoConversations())

function newMessage() {
  ui.showToast('新消息 · M3 上线')
}
function messageSettings() {
  ui.showToast('通知设置 · M3 上线')
}

/* ---------- 互动通知（演示帧 · M3 埋点事件派生） ---------- */
const notices = [
  { icon: 'heart', text: 'Momo 赞了你的帖子 How I memorize 100 new words a month', when: '10:05', unread: true },
  { icon: 'chat', text: 'Kai 评论了你：Great point! I will check it out tonight.', when: '10:42', unread: true },
  { icon: 'follow', text: 'Teacher Lee 关注了你', when: '昨天', unread: false },
  { icon: 'info', text: '「影子跟读法」素材新增 2 篇（你的收藏清单）', when: '周二', unread: false },
] as const

/* Tabler 图标对拍（与底栏同源 · docs/35 规则 1） */
function noticeIcon(kind: string) {
  switch (kind) {
    case 'heart':
      return IconHeart
    case 'chat':
      return IconMessageCircle
    case 'follow':
      return IconUserPlus
    default:
      return IconInfoCircle
  }
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="通知">
      <template #actions>
        <button class="u-topbar__act" type="button" title="新消息（演示）" aria-label="新消息" @click="newMessage">
          <IconMail />
        </button>
        <button class="u-topbar__act" type="button" title="通知设置（演示）" aria-label="通知设置" @click="messageSettings">
          <IconSettings />
        </button>
      </template>
    </MobileTopBar>

    <!-- X 式 tab（均分整行 · 激活加粗 + 下划线） -->
    <nav class="u-notif-tabs" aria-label="通知分类">
      <button
        v-for="t in tabs"
        :key="t"
        class="u-notif-tab"
        :class="{ active: activeTab === t }"
        type="button"
        :aria-selected="activeTab === t"
        @click="activeTab = t"
      >
        {{ t }}
      </button>
    </nav>

    <!-- Tab 1 · 私信（原 /m/messages 列表收敛） -->
    <div v-if="activeTab === '私信'" class="u-msg">
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
            <strong>{{ c.name }}<span class="u-msg__lv">LV{{ c.level.slice(1) }}</span></strong>
            <time class="u-msg__time">{{ c.time }}</time>
          </span>
          <span class="u-msg__last">{{ c.lastMsg }}</span>
        </span>
        <span v-if="c.unread" class="u-msg__dot" aria-label="未读" />
      </RouterLink>
    </div>

    <!-- Tab 2 · 互动通知 -->
    <div v-else class="u-notices">
      <section v-for="(n, i) in notices" :key="i" class="u-notices__row" :class="{ 'is-unread': n.unread }">
        <span class="u-notices__icon">
          <component :is="noticeIcon(n.icon)" />
        </span>
        <span class="u-notices__body">
          <span class="u-notices__text">{{ n.text }}</span>
          <time class="u-notices__when">{{ n.when }}</time>
        </span>
        <span v-if="n.unread" class="u-notices__dot" aria-label="未读" />
      </section>

      <p class="u-note" style="text-align: center; margin-top: 20px">互动通知 M3 接入（埋点事件派生）；私信流同排期。</p>
    </div>
  </div>
</template>
