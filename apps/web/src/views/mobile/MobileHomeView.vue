<script setup lang="ts">
/**
 * 移动端首页（真形态 · 原型 app-home）：
 * 问候 + 打卡徽章 + 统计卡 + 分段控件 + 今日会话列表（真实场景数据）→ 点线时间轴。
 * 统计/打卡为产品化占位（getx：docs/27 埋点聚合 M3 接入后替换），场景列表来自 /api/v1/scenarios。
 */
import { computed, onMounted, ref } from 'vue'

import { fetchScenarios, type ScenarioItem } from '@/api/practice'
import { useAuthStore } from '@/stores/auth'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import '@/styles/mobile-uic.css'

const auth = useAuthStore()
const scenes = ref<ScenarioItem[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const kind = ref<'all' | 'speaking' | 'singing'>('all')

const DIFFICULTY_LABEL: Record<number, string> = { 1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4' }

const filtered = computed(() =>
  kind.value === 'singing' ? [] : scenes.value, // 歌曲 M3 未建设，Singing 置空（docs/06 §9.4）
)

onMounted(async () => {
  auth.fetchMe().catch(() => undefined)
  try {
    scenes.value = await fetchScenarios()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
})

function initials(): string {
  const name = auth.me?.nickname ?? auth.me?.username ?? 'V'
  return name.slice(0, 1).toUpperCase()
}

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

function sceneSub(s: ScenarioItem): string {
  const turns = s.estimated_turns ?? 6
  return `${DIFFICULTY_LABEL[s.difficulty] ?? 'L?'} · 约 ${turns} 轮 · ${
    s.description?.split(/[。．.!?]/)[0] ?? ''
  }`
}

/** 场景 → 深色块 + 具象白图标（对齐设计页 app-home：咖啡=深紫 / 面试=藏青 / 学习=深青） */
function sceneVisual(s: ScenarioItem): { color: string; icon: 'coffee' | 'briefcase' | 'book' | 'mic' } {
  const key = `${s.title}${s.description ?? ''}`
  if (/咖啡|点单|餐厅|民宿|酒店/.test(key)) return { color: '#3A2440', icon: 'coffee' }
  if (/面试|职场|机场|航班|出差|旅行/.test(key)) return { color: '#232044', icon: 'briefcase' }
  if (/图书|学习|校园|课堂/.test(key)) return { color: '#16303A', icon: 'book' }
  return { color: '#1E2B26', icon: 'mic' }
}
</script>

<template>
  <div class="u-phone">
    <div class="u-content">
      <!-- 问候 + 头像 -->
      <header class="u-head">
        <div>
          <h1>{{ greeting() }}, {{ auth.me?.nickname ?? auth.me?.username ?? 'Learner' }}</h1>
          <p>One scene today keeps your 7-day streak.</p>
        </div>
        <div class="u-avatar">{{ initials() }}</div>
      </header>

      <!-- 打卡徽章（占位：M3 打卡聚合后替换） -->
      <div class="u-streak" title="打卡数据待 M3 埋点聚合接入">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <path d="M12 3.5c1 2.5 4.5 4 4.5 8.5a4.5 4.5 0 0 1-9 0c0-1.8.8-3 1.7-4.2.4 1 .9 1.6 1.8 2.2-.3-2.2.2-4.6 1-6.5z" />
        </svg>
        Streak 12 days
      </div>

      <!-- 统计卡（占位：M3 报告聚合后替换） -->
      <section class="u-stats">
        <div><div class="u-stat-label">Rounds</div><div class="u-stat-value">38</div></div>
        <div><div class="u-stat-label">Avg score</div><div class="u-stat-value accent">86.4</div></div>
        <div><div class="u-stat-label">Goal</div><div class="u-stat-value">5/7</div></div>
      </section>

      <!-- 分段控件：All / Speaking / Singing -->
      <div class="u-segment">
        <button type="button" :class="{ active: kind === 'all' }" @click="kind = 'all'">All</button>
        <button type="button" :class="{ active: kind === 'speaking' }" @click="kind = 'speaking'">Speaking</button>
        <button type="button" :class="{ active: kind === 'singing' }" @click="kind = 'singing'">Singing</button>
      </div>

      <!-- 今日会话（点线时间轴） -->
      <div class="u-section-title">Today's sessions</div>
      <div v-if="loading" class="u-empty">加载中…</div>
      <div v-else-if="error" class="u-error">{{ error }}</div>
      <div v-else-if="!filtered.length" class="u-empty">暂无会话。请到「Speaking」开始第一轮练习。</div>
      <template v-for="(s, i) in filtered" :key="s.id">
        <RouterLink :to="`/m/chat/${s.id}`" class="u-task" style="text-decoration: none">
          <span class="u-icon-block" :style="{ background: sceneVisual(s).color }">
            <svg v-if="sceneVisual(s).icon === 'coffee'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M5 9h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z" /><path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16" />
            </svg>
            <svg v-else-if="sceneVisual(s).icon === 'briefcase'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <rect x="4" y="8" width="16" height="12" rx="3" /><path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
            </svg>
            <svg v-else-if="sceneVisual(s).icon === 'book'" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M4 6a2 2 0 0 1 2-2h14v16H6a2 2 0 0 1-2-2z" /><path d="M4 6v0M20 4v16" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
              <path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 12h2" />
            </svg>
          </span>
          <span class="u-task-main">
            <span class="u-task-title">{{ s.title }}</span>
            <span class="u-task-sub">{{ sceneSub(s) }}</span>
          </span>
          <span class="u-task-value">›</span>
        </RouterLink>
        <div v-if="i < filtered.length - 1" class="u-dotline">
          <span class="dot" /><span class="line" />
        </div>
      </template>
    </div>

    <MobileTabBar />
  </div>
</template>
