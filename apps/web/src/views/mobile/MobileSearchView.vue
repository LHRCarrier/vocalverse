<script setup lang="ts">
/**
 * 移动端 · 搜索（2026-09-05 组长拍板 4：X 式底部搜索 tab → 搜索页；演示帧）
 * 结果源 = 社区演示帖 + 演示用户/教程；输入即过滤；空态展示历史/热门 chips。
 * M3 接真实搜索接口（帖子/用户/教程索引）；词汇速记「划词即查」预留挂点（docs/34 §3）。
 */
import { computed, ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { DEMO_FEED } from '@/data/community-demo'
import { createDemoConversations } from '@/data/messages-demo'
import '@/styles/mobile-uic.css'

type SearchTab = '帖子' | '用户' | '教程'
const tabs: SearchTab[] = ['帖子', '用户', '教程']
const activeTab = ref<SearchTab>('帖子')
const keyword = ref('')

const HISTORY = ['phrasal verbs', 'BBC 6 minute', 'MIT dorm life']
const HOT = ['#Shadowing', '#EnglishLearning', '#BonfireNight']

const users = createDemoConversations().map((c) => ({ name: c.name, handle: c.handle, tint: c.tint }))
const tutorials = [
  { title: '影子跟读法入门 · 10 分钟中文教程', tag: '口语' },
  { title: '5 个让口语更自然的连接词组', tag: '词汇' },
]

/** 三个结果集分开（模板按分类引用，避免 union 类型收窄问题） */
const kw = computed(() => keyword.value.trim().toLowerCase())
const posts = computed(() =>
  kw.value
    ? DEMO_FEED.filter((p) => `${p.author} ${p.title} ${p.desc ?? ''}`.toLowerCase().includes(kw.value)).slice(0, 10)
    : [],
)
const foundUsers = computed(() =>
  kw.value ? users.filter((u) => `${u.name} ${u.handle}`.toLowerCase().includes(kw.value)).slice(0, 10) : [],
)
const foundTutorials = computed(() =>
  kw.value ? tutorials.filter((t) => t.title.toLowerCase().includes(kw.value)).slice(0, 10) : [],
)
const currentCount = computed(() => {
  if (!kw.value) return 0
  if (activeTab.value === '帖子') return posts.value.length
  if (activeTab.value === '用户') return foundUsers.value.length
  return foundTutorials.value.length
})

function pick(k: string) {
  keyword.value = k
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="搜索" />

    <div class="u-search">
      <!-- 搜索输入条（X 式：放大镜 + 圆角大输入） -->
      <div class="u-searchbar">
        <MobileIcon name="search" :size="16" />
        <input
          v-model="keyword"
          class="u-searchbar__input"
          type="search"
          maxlength="60"
          placeholder="搜索帖子、用户、教程"
          aria-label="搜索关键词"
        >
      </div>

      <!-- 无关键词：历史 + 热门（演示 chips，点击回填） -->
      <template v-if="!keyword.trim()">
        <section class="u-search__section">
          <h2 class="u-search__label">最近搜索</h2>
          <div class="u-search__chips">
            <button v-for="h in HISTORY" :key="h" class="u-chip u-chip--ink u-search__chip" type="button" @click="pick(h)">
              {{ h }}
            </button>
          </div>
        </section>
        <section class="u-search__section">
          <h2 class="u-search__label">热门话题</h2>
          <div class="u-search__chips">
            <button v-for="h in HOT" :key="h" class="u-chip u-chip--accent u-search__chip" type="button" @click="pick(h.slice(1))">
              {{ h }}
            </button>
          </div>
        </section>
      </template>

      <!-- 有关键词：分类标签行（X 式）+ 结果列表 -->
      <template v-else>
        <nav class="u-x-tabs u-search__tabs" aria-label="搜索分类">
          <button
            v-for="t in tabs"
            :key="t"
            class="u-x-tab"
            :class="{ active: activeTab === t }"
            type="button"
            :aria-selected="activeTab === t"
            @click="activeTab = t"
          >
            {{ t }}
          </button>
        </nav>

        <div v-if="currentCount" class="u-search__list">
          <!-- 帖子结果 -->
          <template v-if="activeTab === '帖子'">
            <div v-for="p in posts" :key="p.id" class="u-search__row">
              <span class="u-search__ava" :style="{ background: p.tint }">{{ p.author.slice(0, 1) }}</span>
              <span class="u-search__body">
                <span class="u-search__title">{{ p.title }}</span>
                <span class="u-search__sub">{{ p.author }} · {{ p.handle }} · {{ p.domain }}</span>
              </span>
            </div>
          </template>
          <!-- 用户结果 -->
          <template v-else-if="activeTab === '用户'">
            <div v-for="u in foundUsers" :key="u.handle" class="u-search__row">
              <span class="u-search__ava" :style="{ background: u.tint }">{{ u.name.slice(0, 1) }}</span>
              <span class="u-search__body">
                <span class="u-search__title">{{ u.name }}</span>
                <span class="u-search__sub">{{ u.handle }}</span>
              </span>
            </div>
          </template>
          <!-- 教程结果 -->
          <template v-else>
            <div v-for="t in foundTutorials" :key="t.title" class="u-search__row">
              <span class="u-search__ava u-search__ava--tutorial"><MobileIcon name="book" :size="16" /></span>
              <span class="u-search__body">
                <span class="u-search__title">{{ t.title }}</span>
                <span class="u-search__sub">{{ t.tag }} · 教程</span>
              </span>
            </div>
          </template>
        </div>

        <!-- 无结果（复用社区空态语言） -->
        <div v-else class="u-comm-empty" role="status">
          <span class="u-comm-empty__icon"><MobileIcon name="search" :size="26" /></span>
          <p class="u-comm-empty__title">没找到相关内容</p>
          <p class="u-comm-empty__sub">换个关键词试试，或看看热门话题～</p>
        </div>
      </template>
    </div>
  </div>
</template>
