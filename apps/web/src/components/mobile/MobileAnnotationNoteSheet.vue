<script setup lang="ts">
/**
 * 移动端 · 单条批注查看 / 编辑弹层。
 * 2026-09-10 新建（修复组长实测 bug2：批注列表点跳转后只能滚动定位，看不到批注内容）。
 * 2026-09-09 改为「查看即编辑」（修复组长实测 Bug1：已批注句子颜色改不了、批注内容改不了，
 * 只能删除）：色板可改色、笔记可改字，保存走 PATCH；删除保留。
 * 触发方式：点正文里带批注的文本 / 点句首批注角标 / 点段尾笔记角标 / 批注列表点跳转。
 */
import { ref, watch } from 'vue'

import MobileIcon from './MobileIcon.vue'
import { ANN_FALLBACK_COLOR, ANNOTATION_COLORS, safeAnnColor } from '@/audio/annotation-colors'
import type { AnnotationItem } from '@/api/reading'

const COLORS = ANNOTATION_COLORS

const props = defineProps<{
  open: boolean
  item: AnnotationItem | null
  /** 父级正在提交（PATCH 在飞）——按钮禁用由父级状态驱动，避免失败后永久卡死 */
  busy?: boolean
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  save: [{ id: number; note: string; color: string }]
  delete: [number]
}>()

const note = ref('')
const color = ref<string>(ANN_FALLBACK_COLOR)

/** 打开/换条时把服务端值灌进编辑态（颜色过白名单，色板外/非法值回退默认色） */
watch(
  () => [props.open, props.item?.id] as const,
  ([open]) => {
    if (!open || !props.item) return
    note.value = props.item.note ?? ''
    color.value = safeAnnColor(props.item.color)
  },
  { immediate: true },
)

function kindLabel(kind: AnnotationItem['kind']): string {
  return kind === 'note' ? '批注' : '高亮'
}

function when(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function save() {
  if (!props.item || props.busy) return
  emit('save', { id: props.item.id, note: note.value, color: color.value })
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open && props.item" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <div class="u-sheet u-rd-ann" role="dialog" aria-modal="true" aria-label="批注详情">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">
              <span class="u-rd-ann__dot" :style="{ background: color }" aria-hidden="true" />
              {{ kindLabel(props.item.kind) }}
            </h2>
            <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('update:open', false)">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>

          <blockquote v-if="props.item.text_snippet" class="u-rd-ann__snippet">
            {{ props.item.text_snippet }}
          </blockquote>

          <!-- 改色（修复 Bug1：已批注句子颜色用户无方式修改） -->
          <div class="u-rd-ann__colors" role="radiogroup" aria-label="批注颜色">
            <button
              v-for="c in COLORS"
              :key="c.id"
              type="button"
              class="u-rd-ann__color"
              :class="{ 'is-active': color === c.value }"
              :style="{ background: c.value }"
              role="radio"
              :aria-checked="color === c.value"
              :aria-label="`改为${c.label}色`"
              @click="color = c.value"
            />
          </div>

          <!-- 改笔记（修复 Bug1：批注内容无法修改） -->
          <textarea
            v-model="note"
            class="u-rd-ann__note"
            rows="3"
            placeholder="写点笔记（可留空，纯高亮）…"
            aria-label="批注内容"
          />
          <p v-if="!note.trim()" class="u-comm-empty__sub">留空则这条批注只保留高亮色。</p>

          <p v-if="when(props.item.updated_at ?? props.item.created_at)" class="u-rd-ann__time">
            {{ when(props.item.updated_at ?? props.item.created_at) }}
          </p>

          <div class="u-rd-ann__actions">
            <button class="u-btn u-btn--primary" type="button" :disabled="props.busy" @click="save">保存修改</button>
            <button class="u-btn u-btn--danger" type="button" @click="emit('delete', props.item.id)">删除批注</button>
            <button class="u-btn" type="button" @click="emit('update:open', false)">关闭</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
