<script setup lang="ts">
/**
 * 练习入口 hub（docs/18 §3-F4）：预置场景选卡 + 自定义答辩入口。
 * docs/14 §3.7：/practice 无参 = 入口；/practice/:sceneId = 进入对话。
 * 未定档引导（stage E）：无等级 → 去 /placement（可跳过）；有等级 → 显示档位 + 复测入口。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { NAlert, NButton, NCard, NTag } from 'naive-ui'

import { errorCopy } from '@/api/errorCopy'
import { fetchScenarios, type ScenarioItem } from '@/api/practice'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()
const scenes = ref<ScenarioItem[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const status = ref<{ has_completed: boolean; can_retest: boolean } | null>(null)

const hasLevel = computed(() => Boolean(auth.me?.level))
const currentLevel = computed(() => auth.me?.level ?? null)

/** C4/C6：场景难度按入学档过滤——只显示 [L, L+1] 档（建档→难度衔接；preferred_difficulty 可进一步覆盖）。 */
const LEVEL_TO_DIFF: Record<string, number> = { L1: 1, L2: 2, L3: 3, L4: 4 }
const levelDiff = computed(() => (currentLevel.value ? LEVEL_TO_DIFF[currentLevel.value] : null))
const visibleScenes = computed(() => {
  const d = levelDiff.value
  return d ? scenes.value.filter((s) => s.difficulty >= d && s.difficulty <= d + 1) : scenes.value
})

const SCENE_EMOJI: Record<string, string> = {
  cafe: '☕',
  airport: '✈️',
  interview: '💼',
  library: '📚',
}

onMounted(async () => {
  try {
    scenes.value = await fetchScenarios()
  } catch (e) {
    error.value = errorCopy(e)
  } finally {
    loading.value = false
  }
  try {
    const { fetchPlacementStatus } = await import('@/api/placement')
    status.value = await fetchPlacementStatus()
  } catch {
    /* 状态不可得则跳过复测入口（不阻断页面） */
  }
})

function enter(scene: ScenarioItem) {
  router.push(`/practice/${scene.id}`)
}

function goPlacement() {
  router.push('/placement')
}
</script>

<template>
  <div class="mx-auto max-w-[1080px]">
    <header class="mb-4">
      <h1 class="text-2xl font-bold">今天练什么？</h1>
      <p class="mt-1 text-sm text-[#667085]">
        欢迎，{{ auth.me?.nickname ?? (auth.me?.username ?? '学习者') }}
        <span class="ml-1 inline-flex items-center gap-2">
          <NTag v-if="currentLevel" round :bordered="false" :color="{ color: '#ECFDF5', textColor: '#15803D' }">
            水平 {{ currentLevel }}
          </NTag>
          <NButton v-if="currentLevel && status?.can_retest" size="tiny" text type="primary" @click="goPlacement">
            🔁 重新测试
          </NButton>
        </span>
        · AI 角色扮演 + 语言点覆盖度 + 逐轮评分
      </p>
    </header>

    <!-- 未定档引导 -->
    <NAlert v-if="!hasLevel" type="warning" class="mb-5" :bordered="false">
      <template #default>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <span>你还没有水平档：先做一次入学测试（或直接跳过，先拿 L2 入门套）就能开始练习。</span>
          <NButton round type="primary" size="small" @click="goPlacement">去入学测试 →</NButton>
        </div>
      </template>
    </NAlert>

    <p v-if="error" class="mb-4 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      {{ error }}（无后端时请先 seed：uv run python -m app.db.seed）
    </p>

    <section v-if="loading" class="py-20 text-center text-sm text-[#667085]">加载场景中…</section>

    <section v-else class="grid grid-cols-1 gap-4 md:grid-cols-2">
      <NCard
        v-for="scene in visibleScenes"
        :key="scene.id"
        hoverable
        class="cursor-pointer transition-shadow hover:shadow-lg"
        @click="enter(scene)"
      >
        <div class="flex items-start justify-between">
          <div>
            <div class="text-lg font-semibold">
              {{ SCENE_EMOJI[scene.scene_type] ?? '🗨' }} {{ scene.title }}
            </div>
            <p class="mt-1 min-h-[2.5rem] text-sm text-[#667085]">{{ scene.description }}</p>
          </div>
          <NTag round :bordered="false" :color="{ color: '#FEF3C7', textColor: '#B45309' }">
            难度 L{{ scene.difficulty }}{{ scene.difficulty <= 2 ? ' 入门' : ' 进阶' }}
          </NTag>
        </div>
        <div class="mt-3 flex items-center justify-between text-xs text-[#667085]">
          <span>约 {{ scene.estimated_turns ?? 6 }} 轮 · 目标表达 5 个 · 含发音/语法/流利度评分</span>
          <NButton size="small" round type="primary">开始 →</NButton>
        </div>
      </NCard>
    </section>

    <section class="mt-6 rounded-[12px] border border-[#0EA5E9]/30 bg-[#F0F9FF] p-5">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-base font-semibold">🎓 自定义答辩导师</div>
          <p class="mt-1 text-sm text-[#667085]">
            粘贴论文摘要/大纲/创新点 → AI 评委英文提问（附提问依据）→ 等级反馈 + 薄弱类型报告
          </p>
        </div>
        <NButton round type="info" @click="router.push('/defense')">开始答辩练习 →</NButton>
      </div>
    </section>
  </div>
</template>

