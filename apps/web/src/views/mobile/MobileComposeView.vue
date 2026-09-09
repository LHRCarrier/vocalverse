<script setup lang="ts">
/**
 * 移动端 · 发帖（2026-09-05 组长拍板 4：底部中央 ＋ = 发帖，X 式内容闭环）
 *
 * 2026-09-09（社区 S3）：支持图片（≤9 张）/ 视频（1 个）上传 —— 先经 Python 媒体服务落库拿 URL，
 * 再随发帖请求带 `media`（Java 只校验 URL 前缀与形状，docs/47 §4.3）。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileMediaPicker from '@/components/mobile/MobileMediaPicker.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { createPost } from '@/api/community'
import { mediaUrl } from '@/api/media'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

import type { MediaAssetView } from '@/api/media'
import type { PostMediaInput } from '@/api/community'

const router = useRouter()
const ui = useUiStore()

const text = ref('')
const MAX = 280
const domains = [
  { id: 'news', label: '新闻稿' },
  { id: 'teaching', label: '教学分享' },
  { id: 'overseas', label: '海外生活' },
]
const domain = ref<string | null>('teaching')
const submitting = ref(false)

/* ---------- 媒体（图片/视频二选一；kind 随媒体类型定） ---------- */
const images = ref<MediaAssetView[]>([])
const videos = ref<MediaAssetView[]>([])
const pickerKind = ref<'image' | 'video'>('image')
const pickerOpen = ref(false)

const kind = computed<'article' | 'video'>(() => (videos.value.length ? 'video' : 'article'))
const canPost = computed(
  () => text.value.trim().length > 0 && domain.value !== null && !submitting.value,
)

function openPicker(k: 'image' | 'video') {
  pickerKind.value = k
  pickerOpen.value = true
}

function onSelected(list: MediaAssetView[]) {
  if (pickerKind.value === 'video') videos.value = list.slice(-1)
  else images.value = list
}

function removeImage(id: string) {
  images.value = images.value.filter((m) => m.id !== id)
}

function buildMedia(): PostMediaInput | null {
  if (videos.value.length) {
    const v = videos.value[0]
    return {
      type: 'video',
      items: [{ id: v.id, url: v.url, width: v.width, height: v.height, size: v.size, mimeType: v.mimeType }],
      durationS: v.durationS,
    }
  }
  if (images.value.length) {
    return {
      type: 'image',
      items: images.value.map((m) => ({
        id: m.id,
        url: m.url,
        width: m.width,
        height: m.height,
        size: m.size,
        mimeType: m.mimeType,
      })),
    }
  }
  return null
}

async function post() {
  if (!canPost.value) return
  submitting.value = true
  try {
    await createPost({
      body: text.value.trim(),
      kind: kind.value,
      domain: domain.value as string,
      media: buildMedia(),
    })
    ui.showToast('已发布')
    void router.push('/m/home')
  } catch (e) {
    ui.showToast(e instanceof Error ? e.message : '发布失败')
  } finally {
    submitting.value = false
  }
}

function attach(kind: string) {
  ui.showToast(`「${kind}」暂未开放`)
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

      <!-- 已选媒体预览 -->
      <ul v-if="images.length || videos.length" class="u-compose__media">
        <li v-for="m in [...images, ...videos]" :key="m.id" class="u-compose__media-cell">
          <img v-if="m.kind !== 'video'" class="u-compose__media-img" :src="mediaUrl(m.url)" alt="待发布图片" decoding="async">
          <span v-else class="u-compose__media-video"><MobileIcon name="play" :size="20" /></span>
          <button class="u-compose__media-del" type="button" aria-label="移除" @click="removeImage(m.id)">
            <MobileIcon name="x" :size="12" />
          </button>
        </li>
      </ul>

      <div class="u-compose__tools">
        <button class="u-compose__tool" type="button" :disabled="!!videos.length" @click="openPicker('image')">
          <MobileIcon name="chat" :size="18" />
          图片
        </button>
        <button class="u-compose__tool" type="button" :disabled="!!images.length" @click="openPicker('video')">
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

      <p class="u-note" style="margin-top: 12px">
        图片最多 9 张（≤20MB）或视频 1 个（MP4/WebM，≤64MB）；图片与视频不能同时发。
      </p>
    </div>

    <MobileMediaPicker
      :open="pickerOpen"
      :kind="pickerKind"
      :selected="pickerKind === 'video' ? videos : images"
      :max="9"
      @update:open="pickerOpen = $event"
      @update:selected="onSelected"
    />
  </div>
</template>
