<script setup lang="ts">
/**
 * 移动端 · 书详情（docs/45 §6 · /m/books/:bookId）：封面卡 + 简介 + 章节目录 + 开始/继续 CTA。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileBookCover from '@/components/mobile/MobileBookCover.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { fetchBookDetail } from '@/api/reading'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { ReadingBookDetail } from '@/api/reading'

const route = useRoute()
const router = useRouter()
const bookId = Number(route.params.bookId)

const book = ref<ReadingBookDetail | null>(null)
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    book.value = await fetchBookDetail(bookId)
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(load)

function startReading() {
  const b = book.value
  if (!b) return
  const target = b.progress?.chapter_id ?? b.chapters[0]?.id
  if (target) void router.push({ path: `/m/reader/${target}`, query: { book: String(b.id) } })
}

function openChapter(id: number) {
  void router.push({ path: `/m/reader/${id}`, query: { book: String(bookId) } })
}

function chapterLabel(no: number): string {
  const names = ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ', 'Ⅶ', 'Ⅷ', 'Ⅸ', 'Ⅹ']
  if (no <= 10) return names[no - 1]
  return String(no)
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="书籍详情" back @back="router.back()" />
    <div class="u-bd">
      <section v-if="loading" class="u-bd__hero">
        <p class="u-comm-empty__sub">加载中…</p>
      </section>
      <div v-else-if="error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">加载失败</span>
        <p class="u-comm-empty__sub">{{ error }}</p>
      </div>
      <template v-else-if="book">
        <section class="u-bd__hero">
          <div class="u-bd__cover-row">
            <div class="u-bd__left">
              <MobileBookCover
                :title="book.title"
                :author="book.author"
                :color="book.cover_color"
                :emoji="book.cover_emoji"
              />
            </div>
            <div class="u-bd__meta">
              <h2 class="u-bd__title">{{ book.title }}</h2>
              <p class="u-bd__author">{{ book.author }}</p>
              <div class="u-bd__badges">
                <span class="u-bd__badge">{{ book.level }}</span>
                <span class="u-bd__badge">{{ book.chapter_count }} 章</span>
                <span class="u-bd__badge">{{ Math.round(book.word_count / 1000) }}k 词</span>
                <span class="u-bd__badge">公版书</span>
              </div>
            </div>
          </div>
          <p class="u-bd__desc">{{ book.description }}</p>
        </section>

        <div class="u-bd__cta">
          <button class="u-btn u-btn--primary u-btn--block" type="button" @click="startReading">
            {{ book.progress ? '继续阅读' : '开始阅读' }}
          </button>
        </div>

        <section class="u-bd__chapters" aria-label="章节目录">
          <button
            v-for="c in book.chapters"
            :key="c.id"
            class="u-bd__chapter"
            :class="{ 'is-current': c.current }"
            type="button"
            @click="openChapter(c.id)"
          >
            <span class="u-bd__chapter-no">{{ chapterLabel(c.chapter_no) }}</span>
            <span class="u-bd__chapter-title">{{ c.title }}</span>
            <MobileIcon name="chevron" :size="16" class="u-learn-module__go" />
          </button>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.u-bd__left :deep(.u-bs-card__cover) {
  border-radius: 14px;
}
</style>
