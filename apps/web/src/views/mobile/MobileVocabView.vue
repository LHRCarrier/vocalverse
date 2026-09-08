<script setup lang="ts">
/**
 * 移动端 · 生词本（docs/45 §6 · /m/vocab）：阅读中查词「加入生词本」收集；唯一入口
 * （UI 拷问 U-5：学习页「我的单词」模块行摘要+CTA 收敛到本页，不另建重复页面）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { deleteVocab, fetchVocab } from '@/api/reading'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { VocabItem } from '@/api/reading'

const router = useRouter()
const ui = useUiStore()
const items = ref<VocabItem[]>([])
const loading = ref(true)
const error = ref('')
const hasMore = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchVocab()
    items.value = res.items
    hasMore.value = res.has_more
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function remove(item: VocabItem) {
  try {
    await deleteVocab(item.id)
    items.value = items.value.filter((i) => i.id !== item.id)
    ui.showToast('已移出单词本')
  } catch (e) {
    ui.showToast('删除失败')
    void e
  }
}

/** 状态切换学习循环：new → learning → known → new（demo 语义） */
async function cycleStatus(item: VocabItem) {
  const next = item.status === 'new' ? 'learning' : item.status === 'learning' ? 'known' : 'new'
  item.status = next
  ui.showToast(`状态：${next}`)
}

/** 回到原文：有 chapter_id 直接进阅读器 */
function backToBook(item: VocabItem) {
  if (item.chapter_id) void router.push(`/m/reader/${item.chapter_id}`)
  else if (item.book_id) void router.push(`/m/books/${item.book_id}`)
}

function dateLabel(iso?: string | null): string {
  if (!iso) return ''
  return iso.slice(0, 10)
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="生词本" back @back="router.push('/m/learn')" />
    <div class="u-vb">
      <header class="u-vb__header">
        <p class="u-vb__count">共 {{ items.length }} 词 · 状态可点击循环（新词→学习中→已掌握）</p>
      </header>

      <section v-if="loading" class="u-comm-skel" aria-label="加载中" aria-busy="true">
        <div v-for="i in 3" :key="i" class="u-comm-skel__card"><span class="u-comm-skel__lines" /></div>
      </section>

      <div v-else-if="error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">加载失败</span>
        <p class="u-comm-empty__sub">{{ error }}</p>
      </div>

      <div v-else-if="items.length === 0" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">单词本空着</span>
        <p class="u-comm-empty__sub">阅读时点击单词 → 「加入生词本」，就会出现在这里。</p>
        <button class="u-comm-empty__btn" type="button" @click="router.push('/m/bookshelf')">
          去书房
        </button>
      </div>

      <ul v-else class="u-vb__list">
        <li v-for="item in items" :key="item.id" class="u-vb-card">
          <div class="u-vb-card__row">
            <span class="u-vb-card__word">{{ item.word }}</span>
            <span class="u-vb-card__phonetic">{{ item.phonetic ?? '' }}</span>
            <button class="u-vb-card__status" type="button" @click="cycleStatus(item)">
              {{ item.status === 'new' ? '新词' : item.status === 'learning' ? '学习中' : '已掌握' }}
            </button>
          </div>
          <p class="u-vb-card__meaning">
            {{ (item.translation ?? '').split('\n')[0] || '暂无释义' }}
          </p>
          <p v-if="item.context_snippet" class="u-vb-card__ctx">“{{ item.context_snippet }}”</p>
          <div class="u-vb-card__foot">
            <span class="u-vb-card__date">{{ dateLabel(item.created_at) }}</span>
            <button v-if="item.book_id" class="u-vb-card__btn" type="button" @click="backToBook(item)">
              <MobileIcon name="arrow" :size="14" /> 回到原文
            </button>
            <button class="u-vb-card__btn" type="button" aria-label="删除" @click="remove(item)">
              <MobileIcon name="trash" :size="14" /> 删除
            </button>
          </div>
        </li>
      </ul>
      <button v-if="hasMore" class="u-comm-more" type="button" disabled>加载更多（演示 len ≤ 50）</button>
    </div>
  </div>
</template>
