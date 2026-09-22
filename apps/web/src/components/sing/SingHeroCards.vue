<script setup lang="ts">
/**
 * 唱吧 · 双英雄卡（QQ 音乐式横滑推荐位 · 2026-09-23 用户原型照搬，内容接真）。
 *
 * 原型（用户提供 index.html）里是「For You / Daily 30」两张渐变卡；此处映射为**真实入口**：
 * - 卡 1（粉）= **本周精选**：列表第一首（`songs[0]`，与旧精选卡同一数据源）；
 * - 卡 2（紫）= **我的收藏**：收藏第一首；没有收藏时整卡不渲染（不放假数据、不留空卡）。
 *
 * 交互：点卡片 = 打开跟唱面板（`open`）——与列表行「试听」区分：卡片是「去唱」入口。
 * 封面经 `mediaUrl()`（打包壳相对路径会 404，docs/48 B5），图裂退音符图标。
 */
import { ref } from 'vue'

import { mediaUrl } from '@/api/media'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

defineProps<{
  /** 本周精选（列表第一首） */
  featured: SongSummary | null
  /** 我的收藏（收藏第一首；无则卡 2 不渲染） */
  favorite: SongSummary | null
}>()
const emit = defineEmits<{ (e: 'open', id: number): void }>()

/** 署名：只取 `·` 前第一段（与列表行/精选卡同口径） */
function artistOf(song: SongSummary): string {
  return (song.artist ?? '').split('·')[0].trim() || '歌单'
}
function coverOf(song: SongSummary): string {
  return mediaUrl(song.cover_url)
}
/** 图裂标记（按卡记：一张裂不牵连另一张） */
const failed = ref<Record<number, boolean>>({})
function coverShown(song: SongSummary | null): boolean {
  return !!song && !!coverOf(song) && !failed.value[song.id]
}
function markFailed(id: number) {
  failed.value = { ...failed.value, [id]: true }
}
</script>

<template>
  <div class="m-sing-hero" role="list" aria-label="推荐">
    <!-- 卡 1 · 本周精选（粉） -->
    <button
      v-if="featured"
      class="m-sing-hero__card m-sing-hero__card--pink"
      type="button"
      role="listitem"
      @click="emit('open', featured.id)"
    >
      <span class="m-sing-hero__top">
        <span class="m-sing-hero__label">
          For<br>You
          <span class="m-sing-hero__label-sub">唱吧本周精选</span>
        </span>
        <span class="m-sing-hero__cover">
          <img
            v-if="coverShown(featured)"
            :src="coverOf(featured)"
            alt=""
            loading="lazy"
            decoding="async"
            @error="markFailed(featured.id)"
          >
          <MobileIcon v-else name="note" :size="22" />
        </span>
      </span>
      <span class="m-sing-hero__bottom">
        <span class="m-sing-hero__info">
          <span class="m-sing-hero__pill">本周精选</span>
          <span class="m-sing-hero__title">{{ featured.title }}</span>
          <span class="m-sing-hero__artist">{{ artistOf(featured) }}</span>
        </span>
        <span class="m-sing-hero__play" aria-hidden="true"><MobileIcon name="play" :size="14" /></span>
      </span>
    </button>

    <!-- 卡 2 · 我的收藏（紫；无收藏不渲染） -->
    <button
      v-if="favorite"
      class="m-sing-hero__card m-sing-hero__card--purple"
      type="button"
      role="listitem"
      @click="emit('open', favorite.id)"
    >
      <span class="m-sing-hero__top">
        <span class="m-sing-hero__label">
          My<br>List
          <span class="m-sing-hero__label-sub">我喜欢的歌</span>
        </span>
        <span class="m-sing-hero__cover">
          <img
            v-if="coverShown(favorite)"
            :src="coverOf(favorite)"
            alt=""
            loading="lazy"
            decoding="async"
            @error="markFailed(favorite.id)"
          >
          <MobileIcon v-else name="heart" :size="22" />
        </span>
      </span>
      <span class="m-sing-hero__bottom">
        <span class="m-sing-hero__info">
          <span class="m-sing-hero__pill">已收藏</span>
          <span class="m-sing-hero__title">{{ favorite.title }}</span>
          <span class="m-sing-hero__artist">{{ artistOf(favorite) }}</span>
        </span>
        <span class="m-sing-hero__play" aria-hidden="true"><MobileIcon name="play" :size="14" /></span>
      </span>
    </button>
  </div>
</template>

<style scoped>
/* 横滑双卡（QQ 音乐式）：每张卡 50% 宽 − 间距/2；卡内两段式（上=标签+封面，下=歌曲信息+播放钮） */
.m-sing-hero {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scrollbar-width: none;
  padding-bottom: 14px;
}
.m-sing-hero::-webkit-scrollbar {
  display: none;
}
.m-sing-hero__card {
  flex: 0 0 calc(50% - 6px);
  height: 178px;
  border: none;
  border-radius: 18px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  text-align: left;
  color: #fff;
  cursor: pointer;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
  transition: transform 0.15s ease;
}
.m-sing-hero__card:active {
  transform: scale(0.98);
}
.m-sing-hero__card--pink {
  background: linear-gradient(145deg, #ff7b92 0%, #ff8fa3 50%, #ffa8ba 100%);
}
.m-sing-hero__card--purple {
  background: linear-gradient(145deg, #7f84ff 0%, #9095ff 50%, #b2b6ff 100%);
}
.m-sing-hero__top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.m-sing-hero__label {
  font-size: 17px;
  font-weight: 900;
  line-height: 1.1;
  letter-spacing: -0.5px;
}
.m-sing-hero__label-sub {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  font-weight: 500;
  letter-spacing: 0;
  opacity: 0.92;
}
.m-sing-hero__cover {
  width: 66px;
  height: 66px;
  flex-shrink: 0;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.3);
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8f959e;
}
.m-sing-hero__cover img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.m-sing-hero__bottom {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 6px;
}
.m-sing-hero__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.m-sing-hero__pill {
  align-self: flex-start;
  font-size: 10px;
  font-weight: 600;
  padding: 1.5px 6px;
  margin-bottom: 3px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.22);
}
.m-sing-hero__title {
  font-size: 12px;
  font-weight: 700;
  line-height: 1.3;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-sing-hero__artist {
  font-size: 10.5px;
  opacity: 0.88;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-sing-hero__play {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: 50%;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15);
}
.m-sing-hero__card--pink .m-sing-hero__play {
  color: #ff5e7e;
}
.m-sing-hero__card--purple .m-sing-hero__play {
  color: #6c72ff;
}
</style>
