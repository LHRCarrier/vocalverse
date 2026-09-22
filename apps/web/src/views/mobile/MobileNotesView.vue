<script setup lang="ts">
/**
 * 移动端 · 笔记（2026-09-05 组长拍板：练习组中央按钮 = 笔记）
 * docs/53 P5 接真：跨章批注列表来自 `GET /api/v1/reading/notes`（阅读器划词高亮/批注落库后的汇总），
 * 点一行跳回原文所在章节；不再使用演示数据。
 */
import { onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { fetchNotes } from '@/api/reading'
import type { NoteItem } from '@/api/reading'
import '@/styles/mobile-uic.css'

const router = useRouter()

type NoteCat = '全部' | '高亮' | '笔记'
const CATS: NoteCat[] = ['全部', '高亮', '笔记']
const activeCat = ref<NoteCat>('全部')

const notes = ref<NoteItem[]>([])
const loading = ref(true)
const error = ref('')

function kindOf(cat: NoteCat): 'highlight' | 'note' | undefined {
  if (cat === '高亮') return 'highlight'
  if (cat === '笔记') return 'note'
  return undefined
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await fetchNotes(kindOf(activeCat.value))
    notes.value = res.items
  } catch (e) {
    error.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}
onMounted(load)
watch(activeCat, () => void load())

function openNote(n: NoteItem) {
  void router.push(`/m/reader/${n.chapter_id}`)
}

function dateLabel(iso?: string | null) {
  return iso ? iso.slice(0, 10) : ''
}
</script>

<template>
  <div class="u-phone">
    <!-- 顶栏 + 分类标签行 → 同一吸顶区：长笔记列表里也能随时切分类（2026-09-21 组长反馈） -->
    <div class="u-head">
      <MobileTopBar title="笔记" back @back="router.push('/m/learn')" />

      <!-- 分类标签行（X 式）；过滤走服务端 kind 参数 -->
      <nav class="u-x-tabs u-head__row" aria-label="笔记分类">
        <button
          v-for="c in CATS"
          :key="c"
          class="u-x-tab"
          :class="{ active: activeCat === c }"
          type="button"
          :aria-selected="activeCat === c"
          @click="activeCat = c"
        >
          {{ c }}
        </button>
      </nav>
    </div>

    <div class="u-notes">
      <section v-if="loading" class="u-comm-skel" aria-label="加载中" aria-busy="true">
        <div v-for="i in 3" :key="i" class="u-comm-skel__card"><span class="u-comm-skel__lines" /></div>
      </section>

      <div v-else-if="error" class="u-comm-empty" role="status">
        <span class="u-comm-empty__title">加载失败</span>
        <p class="u-comm-empty__sub">{{ error }}</p>
        <button class="u-comm-empty__btn" type="button" @click="load">重试</button>
      </div>

      <ul v-else-if="notes.length" class="u-notes__list">
        <li v-for="n in notes" :key="n.id">
          <button class="u-notes__card" type="button" @click="openNote(n)">
            <span class="u-notes__body">
              <span class="u-notes__word">{{ n.kind === 'note' ? (n.note || n.text_snippet || '（无内容）') : (n.text_snippet || '（高亮）') }}</span>
              <span v-if="n.kind === 'note' && n.note" class="u-notes__meaning">{{ n.text_snippet }}</span>
              <span class="u-notes__source">{{ n.book_title }} · {{ n.chapter_title }} · {{ dateLabel(n.created_at) }}</span>
            </span>
            <span class="u-notes__badge" :class="n.kind === 'note' ? 'is-note' : 'is-hl'">
              {{ n.kind === 'note' ? '批注' : '高亮' }}
            </span>
            <MobileIcon name="chevron" :size="16" />
          </button>
        </li>
      </ul>

      <div v-else class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="book" :size="26" /></span>
        <p class="u-comm-empty__title">这个分类还没有笔记</p>
        <p class="u-comm-empty__sub">阅读时长按选中文字即可高亮或写批注，自动收进这里。</p>
        <button class="u-comm-empty__btn" type="button" @click="router.push('/m/bookshelf')">去书房</button>
      </div>
    </div>
  </div>
</template>
