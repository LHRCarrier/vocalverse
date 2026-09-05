<script setup lang="ts">
/**
 * 移动端 · 口语 Hub（docs/14 §12；2026-09-05）
 * 口语 = ① 场景对话（固定出题，M2 已有）/ ② 自由对话（LLM + TTS，MVP 新增）。
 * 本页是 Tab 入口：两个模式卡 + 预置场景列表（点击直奔 /m/chat/:sceneId）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { fetchScenarios, type ScenarioItem } from '@/api/practice'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()

const scenes = ref<ScenarioItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    scenes.value = await fetchScenarios()
  } catch {
    scenes.value = []
  } finally {
    loading.value = false
  }
})

const DIFF_LABEL: Record<number, string> = { 1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4' }
</script>

<template>
  <div class="u-phone">
    <div class="u-content" style="padding-top: 72px">
      <!-- 顶部只留返回按钮（与其它移动页一致） -->
      <button class="u-back u-back--float" type="button" title="返回" @click="router.back()">
        <MobileIcon name="back" />
      </button>

      <header class="u-hub__head">
        <h1 class="u-hub__title">口语</h1>
        <p class="u-hub__sub">场景对话 · 固定出题跟练 ｜ 自由对话 · AI 实时对聊</p>
      </header>

      <!-- 两个模式卡 -->
      <RouterLink to="/m/chat" class="u-hub-card">
        <span class="u-hub-card__icon u-hub-card__icon--scene">
          <MobileIcon name="coffee" :size="22" />
        </span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">场景对话</span>
          <span class="u-hub-card__desc">固定题目 · 8 轮引导 · 发音/流利/语法评分</span>
        </span>
        <span class="u-hub-card__go"><MobileIcon name="chevron" :size="18" /></span>
      </RouterLink>

      <RouterLink to="/m/free-chat" class="u-hub-card u-hub-card--free">
        <span class="u-hub-card__icon u-hub-card__icon--free">
          <MobileIcon name="wave" :size="22" />
        </span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">自由对话</span>
          <span class="u-hub-card__desc">随心说 · AI 对聊（语音/打字 + 实时 TTS）</span>
        </span>
        <span class="u-hub-card__go"><MobileIcon name="chevron" :size="18" /></span>
      </RouterLink>

      <!-- 预置场景列表 -->
      <section class="u-hub-scenes">
        <h2 class="u-hub-scenes__title">预置场景</h2>
        <p v-if="loading" class="u-hub-scenes__sub">加载中…</p>
        <p v-else-if="!scenes.length" class="u-hub-scenes__sub">
          暂无场景，请先执行 seed 初始化演示数据（docs/14 §3.1）。
        </p>
        <RouterLink
          v-for="s in scenes"
          :key="s.id"
          :to="`/m/chat/${s.id}`"
          class="u-hub-scene"
        >
          <span class="u-hub-scene__meta">{{ DIFF_LABEL[s.difficulty] ?? `L${s.difficulty}` }}</span>
          <span class="u-hub-scene__body">
            <span class="u-hub-scene__title">{{ s.title }}</span>
            <span class="u-hub-scene__sub">
              {{ s.description || '与场景角色多轮对话' }}
              <template v-if="s.estimated_turns"> · {{ s.estimated_turns }} 轮</template>
            </span>
          </span>
          <span class="u-hub-card__go"><MobileIcon name="chevron" :size="18" /></span>
        </RouterLink>
      </section>
    </div>
  </div>
</template>
