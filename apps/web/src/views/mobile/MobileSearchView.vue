<script setup lang="ts">
/**
 * 移动端 · 搜索（2026-09-05 组长拍板 4：X 式底部搜索 tab → 搜索页；docs/53 P5 接真）
 * 三 tab 真源 = Python `GET /api/v1/search?type=posts|users|tutorials&q=`：
 * 帖子（可见帖标题/正文）/ 用户（active 用户昵称/@handle）/ 教程（published 听力素材）。
 * 输入 250ms 防抖 + 请求序号防串（旧响应不覆盖新结果）；空关键词显示本地搜索历史 + 热门话题。
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { searchPosts, searchTutorials, searchUsers } from '@/api/search'
import type { SearchPostItem, SearchTutorialItem, SearchUserItem } from '@/api/search'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()

type SearchTab = '帖子' | '用户' | '教程'
const TABS: { tab: SearchTab; type: 'posts' | 'users' | 'tutorials' }[] = [
  { tab: '帖子', type: 'posts' },
  { tab: '用户', type: 'users' },
  { tab: '教程', type: 'tutorials' },
]
const activeTab = ref<SearchTab>('帖子')
const activeType = computed(() => TABS.find((t) => t.tab === activeTab.value)!.type)

const keyword = ref('')
const kw = computed(() => keyword.value.trim())

const posts = ref<SearchPostItem[]>([])
const users = ref<SearchUserItem[]>([])
const tutorials = ref<SearchTutorialItem[]>([])
const loading = ref(false)
const error = ref('')

const DOMAIN_LABELS: Record<string, string> = { news: '英语新闻', teaching: '学习分享', overseas: '海外生活' }
const SOURCE_LABELS: Record<string, string> = { public_domain: '公有领域', original: '原创', demo_only: '演示素材' }

/** 请求序号：快速输入/切 tab 时旧响应必须作废（不覆盖新关键词的结果） */
let seq = 0
let timer: ReturnType<typeof setTimeout> | null = null

async function runSearch() {
  const q = kw.value
  if (!q) {
    posts.value = []
    users.value = []
    tutorials.value = []
    error.value = ''
    loading.value = false
    return
  }
  const mySeq = ++seq
  loading.value = true
  error.value = ''
  try {
    if (activeType.value === 'posts') posts.value = await searchPosts(q)
    else if (activeType.value === 'users') users.value = await searchUsers(q)
    else tutorials.value = await searchTutorials(q)
    if (mySeq !== seq) return
  } catch (e) {
    if (mySeq !== seq) return
    error.value = (e as Error).message || '搜索失败'
  } finally {
    if (mySeq === seq) loading.value = false
  }
}

watch([kw, activeType], () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => void runSearch(), 250)
})

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})

/* ---------- 最近搜索（真实本地历史）+ 热门话题（运营策展） ---------- */
const HISTORY_KEY = 'vv_search_history'
const history = ref<string[]>(readHistory())
const HOT = ['#Shadowing', '#EnglishLearning', '#BonfireNight']

function readHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : []
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === 'string').slice(0, 8) : []
  } catch {
    return []
  }
}

function remember(k: string) {
  const word = k.trim()
  if (!word) return
  history.value = [word, ...history.value.filter((x) => x !== word)].slice(0, 8)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value))
}

function pick(k: string) {
  remember(k)
  keyword.value = k
}

function clearHistory() {
  history.value = []
  localStorage.removeItem(HISTORY_KEY)
}

/* ---------- 结果渲染 ---------- */
const currentCount = computed(() => {
  if (!kw.value) return 0
  if (activeType.value === 'posts') return posts.value.length
  if (activeType.value === 'users') return users.value.length
  return tutorials.value.length
})

function openPost(id: number) {
  void router.push(`/m/post/${id}`)
}

function postMeta(p: SearchPostItem) {
  return [p.author.nickname, p.author.handle ? `@${p.author.handle}` : '', DOMAIN_LABELS[p.domain ?? ''] ?? '']
    .filter(Boolean)
    .join(' · ')
}
</script>

<template>
  <div class="u-phone">
    <!-- 顶栏 + 搜索条（+ 结果分类行）→ 同一吸顶区：翻长结果时也能随时改词/切分类（2026-09-21 组长反馈） -->
    <div class="u-head">
      <MobileTopBar title="搜索" />

      <!-- 搜索输入条（X 式：放大镜 + 圆角大输入） -->
      <div class="u-head__search">
        <div class="u-searchbar">
          <MobileIcon name="search" :size="16" />
          <input
            v-model="keyword"
            class="u-searchbar__input"
            type="search"
            maxlength="60"
            placeholder="搜索帖子、用户、教程"
            aria-label="搜索关键词"
            @keyup.enter="remember(keyword)"
          >
        </div>
      </div>

      <!-- 有关键词：分类标签行（X 式，跟随吸顶） -->
      <nav v-if="kw" class="u-x-tabs u-search__tabs u-head__row" aria-label="搜索分类">
        <button
          v-for="t in TABS"
          :key="t.tab"
          class="u-x-tab"
          :class="{ active: activeTab === t.tab }"
          type="button"
          :aria-selected="activeTab === t.tab"
          @click="activeTab = t.tab"
        >
          {{ t.tab }}
        </button>
      </nav>
    </div>

    <div class="u-search">
      <!-- 无关键词：最近搜索（本地真实历史）+ 热门话题（运营策展） -->
      <template v-if="!kw">
        <section v-if="history.length" class="u-search__section">
          <div class="u-search__head">
            <h2 class="u-search__label">最近搜索</h2>
            <button class="u-search__clear" type="button" @click="clearHistory">清空</button>
          </div>
          <div class="u-search__chips">
            <button v-for="h in history" :key="h" class="u-chip u-chip--ink u-search__chip" type="button" @click="pick(h)">
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

      <!-- 有关键词：结果列表 -->
      <template v-else>
        <section v-if="loading" class="u-comm-skel" aria-label="搜索中" aria-busy="true">
          <div v-for="i in 3" :key="i" class="u-comm-skel__card"><span class="u-comm-skel__lines" /></div>
        </section>

        <div v-else-if="error" class="u-comm-empty" role="status">
          <span class="u-comm-empty__title">搜索失败</span>
          <p class="u-comm-empty__sub">{{ error }}</p>
        </div>

        <div v-else-if="currentCount" class="u-search__list">
          <!-- 帖子结果（点击进详情） -->
          <template v-if="activeType === 'posts'">
            <button v-for="p in posts" :key="p.id" class="u-search__row" type="button" @click="openPost(p.id)">
              <span class="u-search__ava" :style="{ background: p.author.tint ?? '#37546e' }">
                {{ p.author.nickname.slice(0, 1) }}
              </span>
              <span class="u-search__body">
                <span class="u-search__title">{{ p.title }}</span>
                <span class="u-search__sub">{{ postMeta(p) }}</span>
              </span>
            </button>
          </template>
          <!-- 用户结果 -->
          <template v-else-if="activeType === 'users'">
            <div v-for="u in users" :key="u.user_id" class="u-search__row">
              <span class="u-search__ava" :style="{ background: u.tint ?? '#37546e' }">{{ u.nickname.slice(0, 1) }}</span>
              <span class="u-search__body">
                <span class="u-search__title">{{ u.nickname }}</span>
                <span class="u-search__sub">{{ u.handle ? `@${u.handle}` : '—' }} · {{ u.cefr_level ?? '—' }}</span>
              </span>
            </div>
          </template>
          <!-- 教程结果（听力素材） -->
          <template v-else>
            <div v-for="t in tutorials" :key="t.id" class="u-search__row">
              <span class="u-search__ava u-search__ava--tutorial"><MobileIcon name="book" :size="16" /></span>
              <span class="u-search__body">
                <span class="u-search__title">{{ t.title }}</span>
                <span class="u-search__sub">
                  Lv{{ t.level }}<template v-if="t.duration_s"> · {{ Math.round(t.duration_s / 60) }} 分钟</template>
                  <template v-if="t.source"> · {{ SOURCE_LABELS[t.source] ?? t.source }}</template>
                  <template v-if="t.tags.length"> · {{ t.tags.join('/') }}</template>
                </span>
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
