<script setup lang="ts">
/**
 * 移动端 · 发帖（2026-09-05 组长拍板 4：底部中央 ＋ = 发帖，X 式内容闭环；S1 真实流）
 * 正文 280 字（纯文本发帖，D-Q7）+ 领域选择（后端必填）；发布成功 → 回社区（发布后上游可见）。
 * 图片/视频/话题/表情维持「未接入」占位（S1 不发媒体；图片/视频按钮 S2 上传后接）。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import { createPost } from '@/api/community'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const router = useRouter()
const ui = useUiStore()

const text = ref('')
const MAX = 280
const canPost = computed(() => text.value.trim().length > 0 && domain.value !== null)

const domains = [
  { id: 'news', label: '新闻稿' },
  { id: 'teaching', label: '教学分享' },
  { id: 'overseas', label: '海外生活' },
]
const domain = ref<string | null>('teaching')
const submitting = ref(false)

function attach(kind: string) {
  ui.showToast(`「${kind}」S2 上传接入`)
}

async function post() {
  if (!canPost.value || submitting.value) return
  submitting.value = true
  try {
    await createPost({ body: text.value.trim(), kind: 'article', domain: domain.value! })
    ui.showToast('已发布')
    void router.push('/m/home')
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '发布失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="u-phone u-compose">
    <MobileTopBar title="发帖" back @back="router.push('/m/home')">
      <template #actions>
        <button class="u-topbar__btn" type="button" :disabled="!canPost || submitting" aria-label="发布" @click="post">
          发帖
        </button>
      </template>
    </MobileTopBar>

    <div class="u-compose__body">
      <textarea
        v-model="text"
        class="u-compose__textarea"
        :maxlength="MAX"
        placeholder="分享你的英语学习心得、提问或好内容…"
        aria-label="帖子正文"
      />

      <p class="u-compose__count" :class="{ busy: text.length >= MAX * 0.9 }">{{ text.length }}/{{ MAX }}</p>

      <!-- 领域选择（后端必填：news/teaching/overseas） -->
      <div class="u-compose__domains" aria-label="选择领域">
        <button
          v-for="d in domains"
          :key="d.id"
          class="u-compose__domain"
          :class="{ active: domain === d.id }"
          type="button"
          :aria-pressed="domain === d.id"
          @click="domain = d.id"
        >
          {{ d.label }}
        </button>
      </div>

      <div class="u-compose__tools">
        <button class="u-compose__tool" type="button" @click="attach('图片')">
          <MobileIcon name="chat" :size="18" />
          图片
        </button>
        <button class="u-compose__tool" type="button" @click="attach('视频')">
          <MobileIcon name="play" :size="18" />
          视频
        </button>
        <button class="u-compose__tool" type="button" @click="attach('话题')">
          <MobileIcon name="hash" :size="18" />
          话题
        </button>
        <button class="u-compose__tool" type="button" @click="attach('表情')">
          <MobileIcon name="star" :size="18" />
          表情
        </button>
      </div>

      <p class="u-note" style="margin-top: 12px">真实发布：纯文本 + 领域；媒体上传 S2 接入（按钮暂未启用）。</p>
    </div>
  </div>
</template>
