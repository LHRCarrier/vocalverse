<script setup lang="ts">
/**
 * 移动端 · 通知中心（2026-09-09 组长反馈：消息收敛到通知——X 式一个入口 tab 分流）
 * Tab = 私信（会话列表，原 /m/messages 内容收敛进来）/ 通知（互动通知：点赞/评论/关注/系统）。
 * 私信会话点击 → /m/messages/:id（保留）；M3 接真实通知流（埋点事件派生）。
 * 2026-09-09 v2 组长反馈：tab 均分整行居中（X 式）；通知行图标统一 Tabler（与底栏同款）。
 */
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import IconHeart from '~icons/tabler/heart'
import IconInfoCircle from '~icons/tabler/info-circle'
import IconMail from '~icons/tabler/mail'
import IconMessageCircle from '~icons/tabler/message-circle'
import IconSettings from '~icons/tabler/settings'
import IconUserPlus from '~icons/tabler/user-plus'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { createDemoConversations } from '@/data/messages-demo'
import { useFollowStore } from '@/stores/follows'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const tabs = ['私信', '通知', '关注'] as const
type Tab = (typeof tabs)[number]

const MAPPING: Record<string, Tab> = { msg: '私信', notice: '通知', follow: '关注' }

const route = useRoute()
const activeTab = ref<Tab>('私信')

/* ?tab=msg|notice|follow 直达（抽屉通知下拉子项 · 2026-09-09） */
watch(
  () => route.query.tab,
  (v) => {
    const t = MAPPING[String(v ?? '')]
    if (t) activeTab.value = t
  },
  { immediate: true },
)

const ui = useUiStore()
const conversations = ref(createDemoConversations())

const followStore = useFollowStore()
const follows = computed(() => followStore.activities)

function newMessage() {
  ui.showToast('新消息 · M3 上线')
}
function messageSettings() {
  ui.showToast('通知设置 · M3 上线')
}

/* ---------- 互动通知（演示帧 · M3 埋点事件派生；title=互动方，私信行同构） ---------- */
const notices = [
  { icon: 'heart', title: 'Momo', text: '赞了你的帖子 How I memorize 100 new words a month', when: '10:05', unread: true },
  { icon: 'chat', title: 'Kai', text: '评论了你：Great point! I will check it out tonight.', when: '10:42', unread: true },
  { icon: 'follow', title: 'Teacher Lee', text: '关注了你', when: '昨天', unread: false },
  { icon: 'info', title: '声语界', text: '「影子跟读法」素材新增 2 篇（你的收藏清单）', when: '周二', unread: false },
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

    <!-- Tab 2 · 互动通知（你收到的互动 · 与私信行同构：图标位=头像位） -->
    <div v-else-if="activeTab === '通知'" class="u-msg">
      <section v-for="(n, i) in notices" :key="i" class="u-msg__row" :class="{ 'is-unread': n.unread }">
        <span class="u-msg__ava u-msg__ava--icon">
          <component :is="noticeIcon(n.icon)" />
        </span>
        <span class="u-msg__body">
          <span class="u-msg__who">
            <strong>{{ n.title }}</strong>
            <time class="u-msg__time">{{ n.when }}</time>
          </span>
          <span class="u-msg__last">{{ n.text }}</span>
        </span>
        <span v-if="n.unread" class="u-msg__dot" aria-label="未读" />
      </section>

      <p class="u-note" style="text-align: center; margin-top: 20px">互动通知 M3 接入（埋点事件派生）；私信流同排期。</p>
    </div>

    <!-- Tab 3 · 关注（你关注的人的动态 · 与私信行同构：名字行+内容行） -->
    <div v-else class="u-msg">
      <section v-for="(f, i) in follows" :key="i" class="u-msg__row" :class="{ 'is-unread': f.unread }">
        <span class="u-msg__ava" :style="{ background: f.tint }">{{ f.name.slice(0, 1) }}</span>
        <span class="u-msg__body">
          <span class="u-msg__who">
            <strong>{{ f.name }}</strong>
            <time class="u-msg__time">{{ f.when }}</time>
          </span>
          <span class="u-msg__last">{{ f.text }}</span>
        </span>
        <span v-if="f.unread" class="u-msg__dot" aria-label="未读" />
      </section>

      <p class="u-note" style="text-align: center; margin-top: 20px">关注的动态按发文时间倒序、未读优先；M3 接真实流（帖子 JOIN 关注关系）。</p>
    </div>
  </div>
</template>
