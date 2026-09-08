<script setup lang="ts">
/**
 * 移动端 · 单条批注查看/删除弹层（2026-09-10 修复组长实测 bug2：
 * 批注列表点跳转后只能滚动定位，看不到批注内容）。
 * 触发方式：点正文里带批注的文本 / 点批注角标 / 批注列表点跳转。
 */
import MobileIcon from './MobileIcon.vue'
import type { AnnotationItem } from '@/api/reading'

const props = defineProps<{
  open: boolean
  item: AnnotationItem | null
}>()

const emit = defineEmits<{
  'update:open': [boolean]
  delete: [number]
}>()

function kindLabel(kind: AnnotationItem['kind']): string {
  return kind === 'note' ? '批注' : '高亮'
}

function when(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}月${d.getDate()}日 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="props.open && props.item" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <div class="u-sheet u-rd-ann" role="dialog" aria-modal="true">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">
              <span class="u-rd-ann__dot" :style="{ background: props.item.color ?? '#fde68a' }" aria-hidden="true" />
              {{ kindLabel(props.item.kind) }}
            </h2>
            <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('update:open', false)">
              <MobileIcon name="x" :size="18" />
            </button>
          </header>

          <blockquote v-if="props.item.text_snippet" class="u-rd-ann__snippet">
            {{ props.item.text_snippet }}
          </blockquote>
          <p v-if="props.item.note" class="u-rd-ann__note-text">{{ props.item.note }}</p>
          <p v-else class="u-comm-empty__sub">这条批注只有高亮，没有写笔记。</p>

          <p v-if="when(props.item.updated_at ?? props.item.created_at)" class="u-rd-ann__time">
            {{ when(props.item.updated_at ?? props.item.created_at) }}
          </p>

          <div class="u-rd-ann__actions">
            <button class="u-btn u-btn--danger" type="button" @click="emit('delete', props.item.id)">删除批注</button>
            <button class="u-btn" type="button" @click="emit('update:open', false)">关闭</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
