<script setup lang="ts">
/**
 * 移动端 · 阅读设置弹层（docs/45 §6）：字号/行距/主题（localStorage）+ 音色选择。
 * 纯展示：状态由阅读器持有，本组件只转发。
 */
import MobileIcon from './MobileIcon.vue'
import type { ReadingVoice } from '@/api/reading'

const props = defineProps<{
  open: boolean
  theme: 'paper' | 'cream' | 'night'
  fontSize: number
  lineHeight: number
  voices: ReadingVoice[]
  currentVoice: string
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  patch: [{ theme?: 'paper' | 'cream' | 'night'; fontSize?: number; lineHeight?: number }]
  voice: [string]
  next: []
}>()

function shortId(id: string): string {
  return id.split('-').slice(0, 2).join('-')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <div class="u-sheet u-rd-settings" role="dialog" aria-modal="true">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">阅读设置</h2>
            <button class="u-sheet__close" type="button" :aria-label="'关闭'" @click="emit('update:open', false)">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>
          <div class="u-rd-settings__row">
            <span class="u-rd-settings__label">字号</span>
            <div class="u-rd-settings__chips">
              <button
                v-for="f in [16, 19, 22]"
                :key="f"
                class="u-rd-settings__chip"
                :class="{ 'is-active': props.fontSize === f }"
                type="button"
                @click="emit('patch', { fontSize: f })"
              >
                {{ f }}
              </button>
            </div>
          </div>
          <div class="u-rd-settings__row">
            <span class="u-rd-settings__label">行距</span>
            <div class="u-rd-settings__chips">
              <button
                v-for="l in [1.7, 1.85, 2.0]"
                :key="l"
                class="u-rd-settings__chip"
                :class="{ 'is-active': props.lineHeight === l }"
                type="button"
                @click="emit('patch', { lineHeight: l })"
              >
                {{ l }}
              </button>
            </div>
          </div>
          <div class="u-rd-settings__row">
            <span class="u-rd-settings__label">主题</span>
            <div class="u-rd-settings__chips">
              <button class="u-rd-settings__chip" :class="{ 'is-active': props.theme === 'paper' }" type="button" @click="emit('patch', { theme: 'paper' })">纸白</button>
              <button class="u-rd-settings__chip" :class="{ 'is-active': props.theme === 'cream' }" type="button" @click="emit('patch', { theme: 'cream' })">米黄</button>
              <button class="u-rd-settings__chip" :class="{ 'is-active': props.theme === 'night' }" type="button" @click="emit('patch', { theme: 'night' })">暗黑</button>
            </div>
          </div>
          <div class="u-rd-settings__row">
            <span class="u-rd-settings__label">音色</span>
            <div class="u-rd-settings__chips">
              <button
                v-for="v in props.voices"
                :key="v.id"
                class="u-rd-settings__chip"
                :class="{ 'is-active': props.currentVoice === v.id }"
                type="button"
                @click="emit('voice', v.id)"
              >
                {{ shortId(v.id) }}
              </button>
            </div>
          </div>
          <button class="u-btn u-btn--ghost" type="button" @click="emit('next')">换一章（返回详情）</button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
