<script setup lang="ts">
/**
 * 移动端 · 笔记（2026-09-05 组长拍板：练习组中央按钮 = 笔记；演示帧）
 * 词汇速记演进方向（docs/02：划词即查 → 个人词汇本）的入口页；
 * 演示数据：口语/阅读/文化 三类词汇笔记 + 分类 chips + 收藏。
 * M3 接真实词汇本（划词采集 + 复习调度）。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import IconPlus from '~icons/tabler/plus'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'

const router = useRouter()
const ui = useUiStore()

type NoteCat = '口语' | '阅读' | '文化'
interface NoteItem {
  id: number
  word: string
  meaning: string
  cat: NoteCat
  source: string
  time: string
  starred: boolean
}

const notes = ref<NoteItem[]>([
  { id: 1, word: 'pick up', meaning: '学会 / 顺便买 / 接人', cat: '口语', source: 'Emma · 咖啡店俚语', time: '今天', starred: true },
  { id: 2, word: 'run out of', meaning: '用光，耗尽', cat: '口语', source: 'Emma · 咖啡店俚语', time: '今天', starred: false },
  { id: 3, word: 'shadowing', meaning: '影子跟读法', cat: '口语', source: 'Teacher Lee', time: '昨天', starred: true },
  { id: 4, word: 'procrastinate', meaning: '拖延，耽搁', cat: '阅读', source: 'BBC 6 Minute English', time: '昨天', starred: false },
  { id: 5, word: 'kyushoku', meaning: '（日本）学校供餐', cat: '文化', source: 'Saki 在京都', time: '周三', starred: false },
  { id: 6, word: 'slow travel', meaning: '慢旅行（长住慢游）', cat: '阅读', source: 'Global Post', time: '周二', starred: true },
])

const cats = ['全部', '口语', '阅读', '文化'] as const
const activeCat = ref<(typeof cats)[number]>('全部')
const visible = computed(() =>
  activeCat.value === '全部' ? notes.value : notes.value.filter((n) => n.cat === activeCat.value),
)

function toggleStar(id: number) {
  const n = notes.value.find((x) => x.id === id)
  if (n) n.starred = !n.starred
}

function addNote() {
  ui.showToast('添加笔记 · M3 上线')
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="笔记" back @back="router.push('/m/learn')">
      <template #actions>
        <button class="u-topbar__act" type="button" title="添加笔记（演示）" aria-label="添加笔记" @click="addNote">
          <IconPlus />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-notes">
      <!-- 分类标签行（X 式） -->
      <nav class="u-x-tabs" aria-label="笔记分类">
        <button
          v-for="c in cats"
          :key="c"
          class="u-x-tab"
          :class="{ active: activeCat === c }"
          type="button"
          :aria-selected="activeCat === c"
          @click="activeCat = c"
        >
          {{ c }}
        </button>
      </nav>

      <ul v-if="visible.length" class="u-notes__list">
        <li v-for="n in visible" :key="n.id" class="u-notes__card">
          <span class="u-notes__body">
            <span class="u-notes__word">{{ n.word }}</span>
            <span class="u-notes__meaning">{{ n.meaning }}</span>
            <span class="u-notes__source">{{ n.source }} · {{ n.time }}</span>
          </span>
          <button
            class="u-notes__star"
            :class="{ 'is-starred': n.starred }"
            type="button"
            :aria-pressed="n.starred"
            :aria-label="n.starred ? '取消收藏' : '收藏'"
            @click="toggleStar(n.id)"
          >
            <MobileIcon name="star" :size="18" />
          </button>
        </li>
      </ul>

      <div v-else class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="book" :size="26" /></span>
        <p class="u-comm-empty__title">这个分类还没有笔记</p>
        <p class="u-comm-empty__sub">阅读/练习时划词即查，自动收进词汇本（M3）。</p>
      </div>
    </div>
  </div>
</template>
