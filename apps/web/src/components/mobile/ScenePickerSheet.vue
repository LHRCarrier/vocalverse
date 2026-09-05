<script setup lang="ts">
/**
 * 场景选择弹层（2026-09-05：口语 Hub 已收敛删除，预置场景列表并入此处）
 * 底部 sheet：遮罩 + 场景列表；选择后 emit select(sceneId)，由调用方决定去向。
 * 场景列表懒加载（首次打开才 fetch；失败静默，空态提示 seed）。
 */
import { onMounted, ref } from 'vue'

import { fetchScenarios, type ScenarioItem } from '@/api/practice'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'select', sceneId: number): void
}>()

const scenes = ref<ScenarioItem[]>([])
const loading = ref(false)

const DIFF_LABEL: Record<number, string> = { 1: 'L1', 2: 'L2', 3: 'L3', 4: 'L4' }

onMounted(() => {
  if (props.open) void load()
})

async function load() {
  if (scenes.value.length) return
  loading.value = true
  try {
    scenes.value = await fetchScenarios()
  } catch {
    scenes.value = []
  } finally {
    loading.value = false
  }
}

function pick(sceneId: number) {
  emit('update:open', false)
  emit('select', sceneId)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <section class="u-sheet" role="dialog" aria-label="选择场景" @keydown.esc="emit('update:open', false)">
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">选择场景</h2>
            <button
              class="u-sheet__close"
              type="button"
              title="关闭"
              aria-label="关闭"
              @click="emit('update:open', false)"
            >
              <MobileIcon name="plus" :size="18" />
            </button>
          </header>
          <p class="u-sheet__sub">
            {{ loading ? '加载中…' : scenes.length ? '选一个预置场景，开始固定题目的场景对话' : '暂无场景，请先执行 seed 初始化演示数据。' }}
          </p>
          <div class="u-sheet__list">
            <button
              v-for="s in scenes"
              :key="s.id"
              class="u-sheet__item"
              type="button"
              :title="s.title"
              @click="pick(s.id)"
            >
              <span class="u-hub-scene__meta">{{ DIFF_LABEL[s.difficulty] ?? `L${s.difficulty}` }}</span>
              <span class="u-hub-scene__body">
                <span class="u-hub-scene__title">{{ s.title }}</span>
                <span class="u-hub-scene__sub">
                  {{ s.description || '与场景角色多轮对话' }}
                  <template v-if="s.estimated_turns"> · {{ s.estimated_turns }} 轮</template>
                </span>
              </span>
              <span class="u-hub-card__go"><MobileIcon name="chevron" :size="18" /></span>
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
