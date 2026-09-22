<script setup lang="ts">
/**
 * 移动端 · 生词本（docs/45 §6 · /m/vocab）：阅读中查词「加入生词本」收集；唯一入口
 * （UI 拷问 U-5：学习页「我的单词」模块行摘要+CTA 收敛到本页，不另建重复页面）。
 * 状态循环（docs/53 P5）：new → learning → known → new 走 PATCH /vocab/{id} 落库，
 * 失败回滚本地状态（不假装成功）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileSkeleton from '@/components/mobile/MobileSkeleton.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { deleteVocab, fetchVocab, patchVocab } from '@/api/reading'
import { useDelayedLoading } from '@/composables/useDelayedLoading'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { VocabItem } from '@/api/reading'

const router = useRouter()
const ui = useUiStore()
const items = ref<VocabItem[]>([])
const loading = ref(true)
const loadingMore = ref(false)
const error = ref('')
const nextCursor = ref<string | null>(null)
const hasMore = computed(() => nextCursor.value !== null)
const savingIds = ref<Set<number>>(new Set())

/** 骨架防抖（docs/31 硬规则 3）：<300ms 完成不闪骨架；pending 先占位防 CLS */
const { visible: skelVisible, pending: skelPending } = useDelayedLoading(loading)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchVocab()
    items.value = res.items
    nextCursor.value = res.next_cursor
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function loadMore() {
  if (loadingMore.value || !nextCursor.value) return
  loadingMore.value = true
  try {
    const res = await fetchVocab(undefined, nextCursor.value)
    items.value = [...items.value, ...res.items]
    nextCursor.value = res.next_cursor
  } catch {
    ui.showToast('加载更多失败')
  } finally {
    loadingMore.value = false
  }
}

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

const STATUS_LABELS: Record<string, string> = { new: '新词', learning: '学习中', known: '已掌握' }

/** 状态切换学习循环：new → learning → known → new（PATCH 落库，失败回滚） */
async function cycleStatus(item: VocabItem) {
  if (savingIds.value.has(item.id)) return
  const prev = item.status
  const next = prev === 'new' ? 'learning' : prev === 'learning' ? 'known' : 'new'
  item.status = next
  savingIds.value = new Set(savingIds.value).add(item.id)
  try {
    const saved = await patchVocab(item.id, { status: next })
    item.status = saved.status
    ui.showToast(`状态：${STATUS_LABELS[saved.status] ?? saved.status}`)
  } catch {
    item.status = prev
    ui.showToast('状态保存失败，请重试')
  } finally {
    const set = new Set(savingIds.value)
    set.delete(item.id)
    savingIds.value = set
  }
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

      <MobileSkeleton
        v-if="skelPending"
        :class="{ 'is-pending': !skelVisible }"
        variant="lines"
        :count="3"
        label="加载中"
      />

      <div v-else-if="!loading && error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">加载失败</span>
        <p class="u-comm-empty__sub">{{ error }}</p>
      </div>

      <div v-else-if="!loading && items.length === 0" class="u-comm-empty" role="status">
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
            <button
              class="u-vb-card__status"
              type="button"
              :disabled="savingIds.has(item.id)"
              :aria-busy="savingIds.has(item.id)"
              @click="cycleStatus(item)"
            >
              {{ savingIds.has(item.id) ? '保存中…' : (STATUS_LABELS[item.status] ?? item.status) }}
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
      <button v-if="hasMore" class="u-comm-more" type="button" :disabled="loadingMore" @click="loadMore">
        {{ loadingMore ? '加载中…' : '加载更多' }}
      </button>
    </div>
  </div>
</template>
