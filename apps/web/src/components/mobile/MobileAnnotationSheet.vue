<script setup lang="ts">
/**
 * 移动端 · 批注编辑/本章批注列表弹层（docs/45 §6）。
 * mode=create：划选文本 → 高亮 4 色 + 可选笔记；mode=list：本章批注列表（点跳转/删除）。
 */
import { ref, watch } from 'vue'

import MobileIcon from './MobileIcon.vue'
import type { AnnotationItem } from '@/api/reading'

const COLORS = [
  { id: 'yellow', value: '#fde68a', label: '黄' },
  { id: 'green', value: '#bbf7d0', label: '绿' },
  { id: 'blue', value: '#bfdbfe', label: '蓝' },
  { id: 'pink', value: '#fbcfe8', label: '粉' },
]

const props = defineProps<{
  open: boolean
  mode: 'create' | 'list'
  snippet?: string
  annotations?: AnnotationItem[]
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  save: [{ note: string; color: string }]
  delete: [number]
  jump: [AnnotationItem]
}>()

const note = ref('')
const color = ref(COLORS[0].value)

watch(
  () => props.open,
  (v) => {
    if (v) {
      note.value = ''
      color.value = COLORS[0].value
    }
  },
)
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <div class="u-sheet u-rd-ann" role="dialog" aria-modal="true">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">{{ props.mode === 'create' ? '添加批注' : '本章批注' }}</h2>
            <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('update:open', false)">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>

          <template v-if="props.mode === 'create'">
            <p class="u-rd-ann__snippet">{{ props.snippet ?? '' }}</p>
            <div class="u-rd-ann__colors" aria-label="高亮颜色">
              <button
                v-for="c in COLORS"
                :key="c.id"
                type="button"
                class="u-rd-ann__color"
                :class="{ 'is-active': color === c.value }"
                :style="{ background: c.value }"
                :aria-label="c.label"
                @click="color = c.value"
              />
            </div>
            <textarea
              v-model="note"
              class="u-rd-ann__note"
              rows="3"
              placeholder="写点笔记（可留空，纯高亮）…"
            />
            <div class="u-rd-ann__actions">
              <button class="u-btn u-btn--primary" type="button" @click="emit('save', { note: note, color: color })">
                保存
              </button>
              <button class="u-btn" type="button" @click="emit('update:open', false)">取消</button>
            </div>
          </template>

          <template v-else>
            <ul v-if="props.annotations?.length" class="u-rd-annlist">
              <li v-for="a in props.annotations" :key="a.id" class="u-rd-annlist__row">
                <span
                  class="u-rd-annlist__chip"
                  :style="{ background: a.color ?? '#fde68a' }"
                  aria-hidden="true"
                />
                <button class="u-rd-annlist__main" type="button" @click="emit('jump', a)">
                  <span class="u-rd-annlist__text">{{ a.note || a.text_snippet || '高亮' }}</span>
                </button>
                <button class="u-vb-card__btn" type="button" @click="emit('delete', a.id)">
                  <MobileIcon name="trash" :size="15" /> 删除
                </button>
              </li>
            </ul>
            <p v-else class="u-comm-empty__sub">本章还没有批注——划过文字试试。</p>
          </template>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
