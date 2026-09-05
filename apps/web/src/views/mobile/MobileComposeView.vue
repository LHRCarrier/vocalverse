<script setup lang="ts">
/**
 * 移动端 · 发帖（2026-09-05 组长拍板 4：底部中央 ＋ = 发帖，X 式内容闭环；演示帧）
 * X compose 同款：顶栏右「发帖」按钮 + 正文文本域 + 工具行（图片/视频/话题/表情）。
 * 发布 = toast 演示 + 回社区；M3 接真实发布接口（帖子+视频双形态入流）。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const router = useRouter()
const ui = useUiStore()

const text = ref('')
const MAX = 280
const canPost = computed(() => text.value.trim().length > 0)

function attach(kind: string) {
  ui.showToast(`「${kind}」接入 M3 上线`)
}

function post() {
  if (!canPost.value) return
  ui.showToast('已发布（演示）')
  void router.push('/m/home')
}
</script>

<template>
  <div class="u-phone u-compose">
    <MobileTopBar title="发帖" back @back="router.push('/m/home')">
      <template #actions>
        <button class="u-topbar__btn" type="button" :disabled="!canPost" aria-label="发布" @click="post">
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

      <p class="u-note" style="margin-top: 12px">
        演示帧：发布后回社区流（M3 接入真实发布，帖子+视频双形态）。
      </p>
    </div>
  </div>
</template>
