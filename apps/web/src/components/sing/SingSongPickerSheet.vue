<script setup lang="ts">
/**
 * 移动端 · 跟唱曲目选择（底部 sheet，2026-09-21）——「导航栏内歌曲跟唱列表」的移动侧形态。
 *
 * 为什么是底部 sheet 而不是锚定下拉：本项目移动端的**所有**选择器都是这个范式
 * （`.u-sheet` + `ScenePickerSheet.vue`：遮罩 + 底部弹层 + 列表），锚定下拉在仓内无先例，
 * 且 375px 宽下贴顶平移更容易点错。需求 5 的「下拉菜单形式」= 由顶栏入口展开的可选列表。
 *
 * 数据与选中态全部来自 `stores/sing`（与桌面顶栏同一份列表、同一个 `currentSongId`）：
 * 本组件不持列表、不自己 fetch、也不自己切歌 —— 只 emit 选择，
 * 切歌动作仍由页面既有的 `openSong()` 承担（停录音 / 停原唱 / 40905 门禁都在那里）。
 */
import { watch } from 'vue'
import IconX from '~icons/tabler/x'

import { useSingStore } from '@/stores/sing'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (e: 'update:open', value: boolean): void
  (e: 'select', songId: number): void
}>()

const sing = useSingStore()

/** 署名只取 `·` 前第一段（与 MobileSongRow 同口径：`Traditional · 合成旋律（…）` → `Traditional`） */
function artistShort(artist: string | null | undefined): string {
  return (artist ?? '').split('·')[0].trim() || '歌单'
}

/** 懒加载：打开才拉（列表通常已被页面拉过 → store 幂等直接返回，不会重复请求） */
watch(
  () => props.open,
  (v) => {
    if (v) void sing.loadSongs()
  },
  { immediate: true },
)

function pick(songId: number) {
  emit('update:open', false)
  emit('select', songId)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="u-sheet">
      <div v-if="open" class="u-sheet-mask" @click.self="emit('update:open', false)">
        <section
          class="u-sheet m-sing-pick"
          role="dialog"
          aria-label="选择跟唱曲目"
          @keydown.esc="emit('update:open', false)"
        >
          <header class="u-sheet__head">
            <h2 class="u-sheet__title">选择跟唱曲目</h2>
            <button
              class="u-sheet__close"
              type="button"
              title="关闭"
              aria-label="关闭"
              @click="emit('update:open', false)"
            >
              <IconX />
            </button>
          </header>
          <p class="u-sheet__sub">
            当前跟唱：{{ sing.currentSong?.title ?? '未选曲' }}
          </p>

          <p v-if="sing.songsStatus === 'loading' && !sing.songs.length" class="u-sheet__sub">加载中…</p>
          <template v-else-if="sing.songsStatus === 'failed'">
            <p class="u-sheet__sub">{{ sing.songsError ?? '歌曲库加载失败' }}</p>
            <div class="u-sheet__retry">
              <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="sing.loadSongs(true)">
                重试
              </button>
            </div>
          </template>
          <p v-else-if="!sing.songs.length" class="u-sheet__sub">暂无曲目，等参考旋律离线提取完成后再试。</p>

          <div v-else class="m-sing-pick__list">
            <button
              v-for="s in sing.songs"
              :key="s.id"
              class="m-sing-pick__row"
              :class="{ 'is-on': s.id === sing.currentSongId }"
              type="button"
              :aria-current="s.id === sing.currentSongId ? 'true' : undefined"
              @click="pick(s.id)"
            >
              <span class="m-sing-pick__bar" aria-hidden="true" />
              <span class="m-sing-pick__title">{{ s.title }}</span>
              <span class="m-sing-pick__artist">{{ artistShort(s.artist) }}</span>
              <span class="u-badge u-badge--warn m-sing-pick__level">{{ `L${s.level}` }}</span>
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>