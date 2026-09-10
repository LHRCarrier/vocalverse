<script setup lang="ts">
/**
 * 移动端 · 书房/书架（docs/45 §6 · /m/bookshelf）：进行中与全书目。
 * 数据：GET /reading/books（含我的进度）；卡=色块封面 + 进度条；点击进书详情。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileBookCover from '@/components/mobile/MobileBookCover.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { fetchBooks } from '@/api/reading'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { ReadingBook } from '@/api/reading'

const router = useRouter()
const books = ref<ReadingBook[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchBooks()
    books.value = res.items
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(load)

function openBook(book: ReadingBook) {
  void router.push({ path: `/m/books/${book.id}` })
}

function pct(progress: { char_offset: number; content_version: number } | null | undefined): number {
  return progress ? Math.min(100, Math.round((progress.char_offset / 5000) * 100)) : 0
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="书房" back @back="router.push('/m/learn')" />
    <div class="u-bs">
      <section v-if="loading" class="u-comm-skel" aria-label="加载中" aria-busy="true">
        <div v-for="i in 4" :key="i" class="u-comm-skel__card">
          <span class="u-comm-skel__media" />
        </div>
      </section>

      <div v-else-if="error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">加载失败</span>
        <p class="u-comm-empty__sub">{{ error }}</p>
        <button class="u-comm-empty__btn" type="button" @click="load">刷新看看</button>
      </div>

      <div v-else-if="books.length === 0" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">书架还空着</span>
        <p class="u-comm-empty__sub">在下方书架挑一本英文小说开始浸润阅读～</p>
      </div>

      <section v-else class="u-bs__list" aria-label="书架书目">
        <button
          v-for="book in books"
          :key="book.id"
          class="u-bs-card"
          type="button"
          @click="openBook(book)"
        >
          <MobileBookCover
            :title="book.title"
            :author="book.author"
            :color="book.cover_color"
            :emoji="book.cover_emoji"
          />
          <span v-if="book.progress" class="u-bs-card__track" aria-hidden="true">
            <span class="u-bs-card__fill" :style="{ width: `${pct(book.progress)}%` }" />
          </span>
          <span v-if="book.progress" class="u-bs-card__pct">{{ pct(book.progress) }}%</span>
        </button>
      </section>
    </div>
  </div>
</template>
