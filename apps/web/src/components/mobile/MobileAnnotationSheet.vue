<script setup lang="ts">
/**
 * 移动端 · 批注弹层（docs/45 §6）。
 * mode=create：划选文本 → 高亮 4 色 + 可选笔记；
 * mode=highlight：只选高亮色（2026-09-09 修复组长实测「点高亮这句不等选色就默认第一个颜色」——
 *   必须用户明确点色才能保存，未选色时「保存」禁用）；
 * mode=list：批注列表（本章 / 本句两种 scope，点跳转/删除）。
 */
import { computed, ref, watch } from 'vue'

import MobileIcon from './MobileIcon.vue'
import { ANNOTATION_COLORS, safeAnnColor } from '@/audio/annotation-colors'
import type { AnnotationItem } from '@/api/reading'

const COLORS = ANNOTATION_COLORS

const props = defineProps<{
  open: boolean
  mode: 'create' | 'highlight' | 'list'
  snippet?: string
  annotations?: AnnotationItem[]
  /** list 模式标题（本章批注 / 本句批注） */
  title?: string
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  save: [{ note: string; color: string }]
  delete: [number]
  jump: [AnnotationItem]
}>()

const note = ref('')
/**
 * null = 尚未选色（两种模式都要求用户明确点一个色再保存）。
 * 2026-09-09：create 模式此前会静默落色板首色（用户没点过任何色块），一并改为必须选色。
 */
const color = ref<string | null>(null)

const heading = computed(() => {
  if (props.mode === 'list') return props.title ?? '本章批注'
  return props.mode === 'highlight' ? '选择高亮颜色' : '添加批注'
})

const canSave = computed(() => color.value !== null)

watch(
  () => props.open,
  (v) => {
    if (v) {
      note.value = ''
      color.value = null
    }
  },
)

function submit() {
  if (!canSave.value) return
  emit('save', { note: props.mode === 'highlight' ? '' : note.value, color: color.value as string })
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <div class="u-sheet u-rd-ann" role="dialog" aria-modal="true">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">{{ heading }}</h2>
            <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('update:open', false)">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>

          <template v-if="props.mode !== 'list'">
            <p class="u-rd-ann__snippet">{{ props.snippet ?? '' }}</p>
            <div class="u-rd-ann__colors" role="radiogroup" aria-label="高亮颜色">
              <button
                v-for="c in COLORS"
                :key="c.id"
                type="button"
                class="u-rd-ann__color"
                :class="{ 'is-active': color === c.value }"
                :style="{ background: c.value }"
                role="radio"
                :aria-checked="color === c.value"
                :aria-label="`高亮${c.label}色`"
                @click="color = c.value"
              />
            </div>
            <textarea
              v-if="props.mode === 'create'"
              v-model="note"
              class="u-rd-ann__note"
              rows="3"
              placeholder="写点笔记（可留空，纯高亮）…"
            />
            <p v-else class="u-comm-empty__sub">先选一个颜色，再点「高亮」。</p>
            <div class="u-rd-ann__actions">
              <button
                class="u-btn u-btn--primary"
                type="button"
                :disabled="!canSave"
                @click="submit"
              >
                {{ props.mode === 'highlight' ? '高亮' : '保存' }}
              </button>
              <button class="u-btn" type="button" @click="emit('update:open', false)">取消</button>
            </div>
          </template>

          <template v-else>
            <ul v-if="props.annotations?.length" class="u-rd-annlist">
              <li v-for="a in props.annotations" :key="a.id" class="u-rd-annlist__row">
                <span
                  class="u-rd-annlist__chip"
                  :style="{ background: safeAnnColor(a.color) }"
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
