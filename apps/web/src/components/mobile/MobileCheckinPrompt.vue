<script setup lang="ts">
/**
 * 今日打卡 · 侧边提示（2026-09-21 组长反馈：今日首次进入 App 提示打卡）
 *
 * - 只在移动端真形态（/m/*）且已登录时出现；
 * - 当天首次进入出现一次（localStorage 记录展示日，不在一天内反复打扰）；
 * - 点一下 → /m/checkin；已打卡 / 状态加载失败都不显示。
 */
import { onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { useAuthStore } from '@/stores/auth'
import { useCheckinStore } from '@/stores/checkin'
import '@/styles/mobile-uic.css'

/** 当天已提示过的日期（同一天只提示一次） */
const PROMPT_DATE_KEY = 'vv.checkin.prompt.date'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const checkin = useCheckinStore()

const visible = ref(false)

function shownToday(): boolean {
  try {
    return localStorage.getItem(PROMPT_DATE_KEY) === checkin.today
  } catch {
    return true // 存储不可用（隐私模式）：宁可少提示，不反复打扰
  }
}

function markShown() {
  try {
    localStorage.setItem(PROMPT_DATE_KEY, checkin.today)
  } catch {
    /* 记录失败只影响「下次不再提示」，不阻塞 */
  }
}

function evaluate() {
  if (route.path === '/m/checkin') {
    visible.value = false
    return
  }
  if (visible.value) return
  if (!route.path.startsWith('/m/') || !auth.me) return
  if (!checkin.loaded || checkin.failed || checkin.checkedIn) return
  if (shownToday()) return
  visible.value = true
  markShown()
}

function dismiss() {
  visible.value = false
}

function goCheckin() {
  visible.value = false
  void router.push('/m/checkin')
}

onMounted(() => {
  if (auth.me) void checkin.refresh().then(evaluate)
})

watch(
  () => [route.path, auth.me?.userId, checkin.loaded, checkin.checkedIn, checkin.failed] as const,
  () => evaluate(),
)

watch(
  () => auth.me?.userId,
  (id) => {
    if (id) void checkin.refresh().then(evaluate)
  },
)
</script>

<template>
  <Transition name="u-checkin-prompt">
    <aside v-if="visible" class="u-checkin-prompt" aria-label="今日打卡提示">
      <button class="u-checkin-prompt__go" type="button" @click="goCheckin">
        <MobileIcon name="flame" :size="16" />
        <span class="u-checkin-prompt__text">今日还没打卡</span>
        <strong class="u-checkin-prompt__cta">去打卡</strong>
      </button>
      <button
        class="u-checkin-prompt__close"
        type="button"
        title="关闭"
        aria-label="关闭打卡提示"
        @click="dismiss"
      >
        ×
      </button>
    </aside>
  </Transition>
</template>
