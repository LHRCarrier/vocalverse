/**
 * 唱吧选曲真源（2026-09-21）：歌曲列表 + 「当前跟唱歌曲」的唯一状态载体。
 *
 * 背景：此前歌曲列表与选中态都只活在 `useSingPlay()` 的组件级实例里
 * （`composables/sing.ts` 的 `songs` / `detail` 两个本地 ref）——
 * 无任何跨模块通道，导航栏（桌面顶栏 / 移动顶栏）拿不到「现在在唱哪首」。
 * 现在把**列表**与**当前选中**上提到本 store：
 * - 列表只在这里 fetch（幂等），页面 / 桌面顶栏 / 移动选曲 sheet 三处共读一份，
 *   杜绝「页面一份、导航一份」的双列表漂移（收藏态也会各改各的）；
 * - `useSingPlay()` 的 `songs` / `loadSongs` 委派到这里，**公开 API 不变**；
 * - 其他模块读 `currentSong` 即可同步（例如后续「练习/报表」要按当前曲目取数）。
 *
 * 不做 localStorage 持久化（与 `stores/progress.ts` 刻意不同）：跟唱选曲是**会话内意图**，
 * 刷新后回到「未选」比记住一首可能已下架/未就绪的旧歌更安全。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { fetchSongs, singErrorMessage } from '@/api/sing'
import type { SongSummary } from '@/api/sing'

export type SingSongsStatus = 'idle' | 'loading' | 'ready' | 'failed'

export const useSingStore = defineStore('sing', () => {
  const songs = ref<SongSummary[]>([])
  const songsStatus = ref<SingSongsStatus>('idle')
  const songsError = ref<string | null>(null)
  /** 当前跟唱歌曲 id（null=未选）；只在详情与参考旋律门禁通过后写入（见 composables/sing.ts openSong） */
  const currentSongId = ref<number | null>(null)

  const currentSong = computed<SongSummary | null>(
    () => songs.value.find((s) => s.id === currentSongId.value) ?? null,
  )

  /**
   * 拉取歌曲列表（幂等）：已 ready 且非 `force` 直接返回 —— 页面挂载、顶栏挂载、
   * sheet 打开三处都会调它，只有第一次真正发请求。
   * 失败**不清空**已拿到的列表（沿用 useSingPlay 旧语义：重试失败不该把界面打回空白），
   * 只置 failed + 文案，由调用方决定怎么提示。
   */
  async function loadSongs(force = false): Promise<void> {
    if (!force && songsStatus.value === 'ready') return
    songsStatus.value = 'loading'
    songsError.value = null
    try {
      songs.value = await fetchSongs()
      songsStatus.value = 'ready'
    } catch (e) {
      songsError.value = singErrorMessage(e)
      songsStatus.value = 'failed'
    }
  }

  /** 设当前跟唱歌曲；id 由调用方保证来自 `songs`（界面只从同一份列表点选） */
  function selectSong(id: number): void {
    currentSongId.value = id
  }

  return { songs, songsStatus, songsError, currentSongId, currentSong, loadSongs, selectSong }
})