<script setup lang="ts">
/**
 * 读书域 · 团队联调测试页（dev-only，生产构建整枝剔除——见 router/preview.ts）。
 *
 * 依赖（请先按 README 起全栈）：
 * - Python 8000 / Java 8080 / 数据库已 `uv run alembic upgrade head` + seed：
 *   `uv run python -m app.db.seed_reading`（公版书 + 词典子集）；
 * - 演示账号 demoadult/demo123456 登录后本页自动带 JWT（X-Test-User-Id 仅测试模式）；
 * - 听书引擎：默认 edge（联网）；本地 KittenTTS 可选用（docs/45 §5：
 *   `uv sync --extra local-tts` + .env `APP_VOICE_MODELS_DIR=<VoiceStudio models 目录>`）。
 *
 * 删除清单（可删无影响）：
 *   1. apps/web/src/views/preview/ReadingPreview.vue（本文件）
 *   2. apps/web/src/views/preview/registry.ts 中本页登记行
 *   3. apps/web/src/router/preview.ts 中 'reading' 子路由
 *   删除后：pnpm lint && pnpm typecheck && pnpm test:run && pnpm build 全绿；
 *   契约快照零 diff（reading 主路由为生产功能，不随本页删除）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { fetchBooks, fetchBookDetail, lookupWord } from '@/api/reading'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { ReadingBook, ReadingBookDetail, WordLookupResult } from '@/api/reading'

const router = useRouter()
const books = ref<ReadingBook[]>([])
const detail = ref<ReadingBookDetail | null>(null)
const wordQuery = ref('')
const lookupResult = ref<WordLookupResult | null>(null)
const lookupError = ref('')

onMounted(async () => {
  try {
    const res = await fetchBooks()
    books.value = res.items
  } catch {
    /* 未登录/服务未起 */
  }
})

async function openBook(id: number) {
  try {
    detail.value = await fetchBookDetail(id)
  } catch {
    /* 忽略 */
  }
}

async function doLookup() {
  lookupError.value = ''
  lookupResult.value = null
  try {
    lookupResult.value = await lookupWord(wordQuery.value)
  } catch (e) {
    lookupError.value = (e as Error).message
  }
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="读书联调台" back @back="router.push('/preview')" />
    <div class="u-comm">
      <div class="u-bd__cta">
        <button class="u-btn u-btn--primary" type="button" @click="router.push('/m/bookshelf')">
          打开移动端书架（真形态）
        </button>
      </div>

      <section class="u-bd__chapters">
        <p class="u-learn-detail__sub">① 书架数据（GET /reading/books）</p>
        <button v-for="b in books" :key="b.id" class="u-bd__chapter" type="button" @click="openBook(b.id)">
          <span class="u-bd__chapter-no">{{ b.id }}</span>
          <span class="u-bd__chapter-title">{{ b.title }} · {{ b.author }}</span>
        </button>
      </section>

      <section v-if="detail" class="u-bd__chapters">
        <p class="u-learn-detail__sub">② 章节目录（点击进阅读器）</p>
        <button
          v-for="c in detail.chapters"
          :key="c.id"
          class="u-bd__chapter"
          type="button"
          @click="router.push(`/m/reader/${c.id}`)"
        >
          <span class="u-bd__chapter-no">{{ c.chapter_no }}</span>
          <span class="u-bd__chapter-title">{{ c.title }}（{{ Math.round(c.char_count / 100) }} 百字符）</span>
        </button>
      </section>

      <section class="u-bd__chapters">
        <p class="u-learn-detail__sub">③ 查词（POST /reading/lookup；可见词形→头词解析与词卡形态）</p>
        <div style="display: flex; gap: 8px">
          <input v-model="wordQuery" class="u-rd-ann__note" style="flex: 1" placeholder="inventions / dream …" @keyup.enter="doLookup">
          <button class="u-btn u-btn--primary" type="button" @click="doLookup">查</button>
        </div>
        <p v-if="lookupResult" class="u-rd-word__meaning">
          {{ lookupResult.word }} {{ lookupResult.phonetic }} — {{ lookupResult.translation?.split('\n')[0] }}
        </p>
        <p v-if="lookupError" class="u-vb__count">{{ lookupError }}</p>
      </section>

      <p class="u-comm__note">
        联调面 = 真路由（CommunityPreview 前例 · docs/46 M-9 A 落法）；听书与 SSE 进度请在阅读器内验证。
      </p>
    </div>
  </div>
</template>
