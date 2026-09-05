<script setup lang="ts">
/**
 * 社区卡片 · 评论面板（2026-09-05 组长升级拍板：评论全交互，演示帧级）
 * 复用 u-sheet 弹层体系（与 ScenePickerSheet 同套）：遮罩 + 底部卡片；
 * 演示评论列表 + 发表输入条；发送本地追加（emit add-comment，父级写回 post.comments 并计数 +1）。
 * 嵌套评论楼 = M3（docs/34 §5 P1）。
 */
import { ref, watch } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { PostComment } from '@/types/community'

const props = defineProps<{
  open: boolean
  title: string
  comments: PostComment[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  'add-comment': [text: string]
}>()

const draft = ref('')

/* 每次打开清空草稿 */
watch(
  () => props.open,
  (v) => {
    if (v) draft.value = ''
  },
)

function submit() {
  const text = draft.value.trim()
  if (!text) return
  emit('add-comment', text)
  draft.value = ''
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
            <h2 class="u-sheet__title">评论</h2>
            <button
              class="u-sheet__close"
              type="button"
              title="关闭"
              aria-label="关闭评论"
              @click="emit('update:open', false)"
            >
              <MobileIcon name="plus" :size="18" />
            </button>
          </header>
          <p class="u-sheet__sub">{{ props.title }}</p>

          <ul v-if="props.comments.length" class="u-comments__list">
            <li v-for="(c, i) in props.comments" :key="i" class="u-comments__item">
              <span class="u-comments__ava">{{ c.author.slice(0, 1) }}</span>
              <span class="u-comments__body">
                <span class="u-comments__who">
                  {{ c.author }}
                  <time class="u-comments__time">{{ c.time }}</time>
                </span>
                <span class="u-comments__text">{{ c.text }}</span>
              </span>
            </li>
          </ul>
          <p v-else class="u-comments__empty">还没有评论，来抢沙发～</p>

          <footer class="u-comments__bar">
            <input
              v-model="draft"
              class="u-comments__input"
              type="text"
              maxlength="200"
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
