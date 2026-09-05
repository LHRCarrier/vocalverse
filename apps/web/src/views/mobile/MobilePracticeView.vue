<script setup lang="ts">
/**
 * 移动端 · 练习首页（2026-09-05 组长拍板 5→6：与社区 home 同级设计语言）
 * 结构：顶栏（练习 + 报告入口）→ 今日练习暗卡 → 统计行 → 场景推荐 → 自由对话卡 → 唱吧精选暗卡。
 * 与社区 home 一致：X 式顶栏 + 卡片流 + 深色焦点卡（每屏 ≤1 深色卡规则保证：本页仅一深卡——唱吧精选，
 * 今日目标用浅色 u-plan 卡替代深卡（避免两张深卡）。
 * 场景数据：fetchScenarios 真实接口（登录后）；失败 fallback 演示场景（无后端可看）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchScenarios, type ScenarioItem } from '@/api/practice'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()

/* ---------- 场景推荐（真实接口；失败 → 演示 fallback） ---------- */
const fallbackScenes: ScenarioItem[] = [
  { id: 0, title: '机场 · 值机', scene_type: 'journey', description: '值机柜台日常对话', difficulty: 1, estimated_turns: 4 },
  { id: 0, title: '咖啡馆 · 点单', scene_type: 'daily', description: '点咖啡与闲聊开场', difficulty: 1, estimated_turns: 5 },
  { id: 0, title: '面试 · 自我介绍', scene_type: 'career', description: '职场英语高频问答', difficulty: 2, estimated_turns: 6 },
]
const sceneTints = ['var(--u-dark-teal)', 'var(--u-dark-purple)', 'var(--u-dark-navy)']
const scenes = ref<ScenarioItem[]>(fallbackScenes)
const scenesLive = ref(false)

onMounted(async () => {
  try {
    const list = await fetchScenarios()
    if (list.length) {
      scenes.value = list.slice(0, 3)
      scenesLive.value = true
    }
  } catch {
    /* 演示 fallback 已就位（无后端 mock 场景） */
  }
})

function diffLabel(d: number): string {
  return { 1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4' }[d] ?? `L${d}`
}

/* ---------- 统计（演示帧；M3 学习画像聚合后替换） ---------- */
const stats = [
  { label: '连续天数', value: '12' },
  { label: '累计轮数', value: '38' },
  { label: '平均分', value: '86.4' },
]
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="练习">
      <template #actions>
        <button
          class="u-topbar__act"
          type="button"
          title="评分报告"
          aria-label="评分报告"
          @click="router.push('/m/report')"
        >
          <MobileIcon name="chart" :size="16" />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content">
      <!-- 今日目标卡（浅色焦点卡：今日行动 + 主 CTA；深色卡留给唱吧精选，遵守每屏 ≤1 深卡） -->
      <section class="u-plan" style="margin-bottom: 20px">
        <div class="u-plan__art" aria-hidden="true"><MobileArt name="mic" :size="96" /></div>
        <div class="u-plan__body">
          <div class="u-plan__title">今日目标 · 再开口 1 轮</div>
          <div class="u-plan__sub">连续 12 天 · 温故「机场 · 值机」</div>
          <div class="u-plan__cta">
            <button class="u-btn u-btn--primary" type="button" @click="router.push('/m/chat')">
              <MobileIcon name="mic" :size="16" />
              开始练习
            </button>
          </div>
        </div>
      </section>

      <!-- 统计行（Stat 32px；演示帧 · M3 学习画像替换） -->
      <section class="u-stats">
        <div v-for="s in stats" :key="s.label">
          <div class="u-stat-label">{{ s.label }}</div>
          <div class="u-stat-value">{{ s.value }}</div>
        </div>
      </section>

      <!-- 场景对话 · 推荐（真实接口 / fallback） -->
      <div class="u-section-title">场景对话 · 推荐</div>
      <RouterLink
        v-for="(s, i) in scenes"
        :key="`${s.title}-${i}`"
        :to="s.id ? `/m/chat/${s.id}` : '/m/chat'"
        class="u-hub-card"
      >
        <span class="u-hub-card__icon" :style="{ background: sceneTints[i % sceneTints.length] }">
          <MobileIcon name="coffee" :size="18" />
        </span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">
            {{ s.title }}
            <span class="u-hub-scene__meta" style="display: inline-block; vertical-align: 1px">
              {{ diffLabel(s.difficulty) }}
            </span>
          </span>
          <span class="u-hub-card__desc">{{ s.description }}</span>
        </span>
        <MobileIcon name="chevron" :size="18" class="u-hub-card__go" />
      </RouterLink>
      <p v-if="!scenesLive" class="u-note" style="margin-top: 2px">演示场景（登录后展示真实推荐）。</p>

      <!-- 自由对话 -->
      <RouterLink to="/m/free-chat" class="u-hub-card" style="margin-top: 14px">
        <span class="u-hub-card__icon" style="background: var(--u-dark-purple)">
          <MobileIcon name="wave" :size="18" />
        </span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">AI 自由对话</span>
          <span class="u-hub-card__desc">麦克风或打字 · 想聊就聊 · TTS 语音播报</span>
        </span>
        <MobileIcon name="chevron" :size="18" class="u-hub-card__go" />
      </RouterLink>

      <!-- 唱吧精选（每屏唯一深色卡 · 线稿锚点 + 幽灵按钮） -->
      <section class="u-dark-card u-dark-card--navy" style="margin-top: 20px">
        <div class="u-dark-card__art" aria-hidden="true"><MobileArt name="note" :size="104" /></div>
        <span class="u-chip u-chip--navy">本周精选 · 107s · 全曲跟唱</span>
        <h2 class="u-dark-card__title">Perfect Night</h2>
        <p class="u-dark-card__desc">上次 88.1 分 · 音准 93 · 节奏 91，稳住节奏就能破 90。</p>
        <button class="u-btn u-btn--ghost" type="button" style="margin-top: 16px" @click="router.push('/m/sing')">
          <MobileIcon name="note" :size="16" />
          去跟唱
        </button>
      </section>

      <p class="u-note" style="text-align: center; margin-top: 20px">
        口语与跟唱引擎 M3 接入后开放真实链路。
      </p>
    </div>
  </div>
</template>
