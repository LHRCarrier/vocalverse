<script setup lang="ts">
/**
 * 社区卡片 · 评论面板（S1 真实流：docs/37 §8）
 *
 * 复用 u-sheet 弹层体系；打开时服务端拉首页（keyset 游标，ASC），发表后顶部插入并
 * emit update-count（父级同步卡片计数，A-05 以后端 total 为准）；嵌套评论楼 = S3。
 */
import { ref, watch } from 'vue'
import IconX from '~icons/tabler/x'

import { addComment, fetchComments, timeAgo } from '@/api/community'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import { useUiStore } from '@/stores/ui'

import type { CommentView } from '@/types/community'

const props = defineProps<{
  open: boolean
  postId: number
  title: string
  commentCount: number
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'update-count': [value: number]
}>()

const ui = useUiStore()
const list = ref<CommentView[]>([])
const cursor = ref<string | null>(null)
const hasMore = ref(false)
const loading = ref(false)
const loadingMore = ref(false)
const added = ref(0)
const draft = ref('')

/** 展示计数 = 服务端总数 + 本次会话新增（父级按此同步卡片） */
const total = () => props.commentCount + added.value

/**
 * 打开即拉取（immediate：面板由父级 v-if 挂载——关闭=卸载、重开=重挂载，open 值无"变化"
 * 不会触发普通 watch，必须 immediate 才能在每次打开时重新请求；postId 监听防切帖残留）。
 */
watch(
  () => [props.open, props.postId] as const,
  async ([open]) => {
    if (!open) {
      list.value = []
      added.value = 0
      return
    }
    draft.value = ''
    await loadFirst()
  },
  { immediate: true },
)

async function loadFirst() {
  loading.value = true
  try {
    const page = await fetchComments(props.postId, null)
    list.value = page.items
    cursor.value = page.nextCursor
    hasMore.value = page.hasMore
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '评论加载失败')
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !hasMore.value || !cursor.value) return
  loadingMore.value = true
  try {
    const page = await fetchComments(props.postId, cursor.value)
    list.value = list.value.concat(page.items)
    cursor.value = page.nextCursor
    hasMore.value = page.hasMore
  } finally {
    loadingMore.value = false
  }
}

async function submit() {
  const text = draft.value.trim()
  if (!text) return
  try {
    const comment = await addComment(props.postId, text)
    list.value = [comment, ...list.value]
    added.value += 1
    emit('update-count', total())
    draft.value = ''
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '发表失败')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <section
          class="u-sheet u-comments"
          role="dialog"
          aria-label="评论"
          @keydown.esc="emit('update:open', false)"
        >
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">评论 <span class="u-comments__count">· {{ total() }}</span></h2>
            <button
              class="u-sheet__close"
              type="button"
              title="关闭"
              aria-label="关闭评论"
              @click="emit('update:open', false)"
            >
              <IconX />
            </button>
          </header>
          <p class="u-sheet__sub">{{ props.title }}</p>

          <p v-if="loading" class="u-comments__empty">评论加载中…</p>
          <ul v-else-if="list.length" class="u-comments__list">
            <li v-for="c in list" :key="c.id" class="u-comments__item">
              <span class="u-comments__ava" :style="{ background: c.author.tint ?? '#37546e' }">{{
                c.author.nickname.slice(0, 1)
              }}</span>
              <span class="u-comments__body">
                <span class="u-comments__who">
                  {{ c.author.nickname }}
                  <time class="u-comments__time">{{ timeAgo(c.createdAt) }}</time>
                </span>
                <span class="u-comments__text">{{ c.body }}</span>
              </span>
            </li>
            <li v-if="hasMore" class="u-comments__more">
              <button type="button" :disabled="loadingMore" @click="loadMore">加载更多评论</button>
            </li>
          </ul>
          <p v-else class="u-comments__empty">还没有评论，来抢沙发～</p>

          <footer class="u-comments__bar">
            <input
              v-model="draft"
              class="u-comments__input"
              type="text"
              maxlength="500"
              placeholder="写下你的评论…"
              aria-label="评论内容"
              @keydown.enter="submit"
            >
            <button
              class="u-comments__send"
              type="button"
              :disabled="!draft.trim()"
              aria-label="发表评论"
              @click="submit"
            >
              <MobileIcon name="arrow" :size="16" />
            </button>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
