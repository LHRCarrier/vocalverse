<script setup lang="ts">
/**
 * 唱吧 · 曲库区（英雄卡 / 骨架 / 错误态 / 歌单 / 空态）—— 2026-09-23 从视图抽出。
 *
 * 抽出理由：本页视图受 `max-lines` 门禁（eslint max 350），且这块是「数据进、事件出」的纯展示段，
 * 页面只保留业务绑定（加载/打开/试听/收藏）。
 *
 * 三个既有口径原样保留：
 * - 加载态骨架（docs/31 硬规则 3：>300ms 才出现；防抖在页面侧 `useDelayedLoading`）；
 * - 错误态 `u-comm-empty`（「歌曲库加载失败」是既有测试锚点，必须保留）；
 * - 区块标题与空态在加载中/失败时不渲染（防「共 0 首」与骨架/错误态自相矛盾）。
 */
import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileSkeleton from '@/components/mobile/MobileSkeleton.vue'
import MobileSongList from '@/components/mobile/MobileSongList.vue'
import SingHeroCards from '@/components/sing/SingHeroCards.vue'
import type { SongSummary } from '@/api/sing'

const props = defineProps<{
  featured: SongSummary | null
  favorite: SongSummary | null
  songs: SongSummary[]
  /** 'songs' = 推荐（全部）；'fav' = 收藏 */
  tab: string
  activeId: number | null
  skelPending: boolean
  skelVisible: boolean
  loadFailed: boolean
  errorText: string | null
}>()

const emit = defineEmits<{
  (e: 'open', id: number): void
  (e: 'preview', song: SongSummary): void
  (e: 'favorite', song: SongSummary): void
  (e: 'retry'): void
}>()

/** 列表的 `preview` 只带 (id, index) → 在这里还原成曲目对象再上抛（页面侧要整首做试听） */
function onListPreview(id: number) {
  const song = props.songs.find((s) => s.id === id)
  if (song) emit('preview', song)
}
</script>

<template>
  <div>
    <!-- 双英雄卡（2026-09-23 用户原型：QQ 音乐式横滑双卡）——版式见 components/sing/SingHeroCards.vue -->
    <MobileSkeleton
      v-if="!featured && skelPending"
      :class="{ 'is-pending': !skelVisible }"
      variant="feed"
      :count="3"
      label="歌曲库加载中"
    />
    <SingHeroCards
      v-else-if="featured"
      :featured="featured"
      :favorite="favorite"
      @open="emit('open', $event)"
    />
    <!-- 错误态（P1-6）：与兄弟页同款 u-comm-empty（原来用深青内容卡承载错误，与内容态同形、语义混淆） -->
    <div v-else-if="loadFailed" class="u-comm-empty" role="status">
      <span class="u-comm-empty__icon"><MobileIcon name="info" :size="28" /></span>
      <p class="u-comm-empty__title">歌曲库加载失败</p>
      <p class="u-comm-empty__sub">{{ errorText ?? '网络异常，请重试' }}</p>
      <button class="u-comm-empty__btn" type="button" @click="emit('retry')">
        <MobileIcon name="refresh" :size="15" />
        重试
      </button>
    </div>

    <!-- 歌单（滚动动画列表 · 真实数据 + 每首歌收藏按钮）。2026-09-22 起收进定高滚动区，
         页面高度与曲库规模无关；标题/空态在加载中、失败时不渲染。 -->
    <div v-if="!skelPending && !loadFailed" class="u-section-title">
      歌曲库 · 共 {{ songs.length }} 首
    </div>
    <MobileSongList
      v-if="songs.length"
      :songs="songs"
      :active-id="activeId"
      @preview="onListPreview($event)"
      @open="emit('open', $event)"
      @favorite="emit('favorite', $event)"
    />
    <div v-if="!skelPending && !loadFailed && !songs.length" class="u-empty">
      <div class="u-empty__art"><MobileArt name="note" :size="96" /></div>
      <div class="u-empty__title">
        {{ tab === 'fav' ? '还没有收藏的歌曲' : '歌曲库还没有歌' }}
      </div>
      <div class="u-empty__sub">
        {{
          tab === 'fav'
            ? '点歌曲右侧的心形按钮收藏，再点一次取消。'
            : '参考旋律离线提取完成后即可跟唱。'
        }}
      </div>
    </div>
  </div>
</template>
