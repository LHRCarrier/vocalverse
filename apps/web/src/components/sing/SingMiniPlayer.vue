<script setup lang="ts">
/**
 * 唱吧 · 悬浮试听播放条（QQ 音乐式 · 2026-09-23 用户原型照搬，内容接真）。
 *
 * 原型里是「转盘 + 歌名 + 红心 + 播放/暂停 + 队列」；此处映射为**真实能力**：
 * - 转盘 = 当前曲目封面，播放时旋转（`animation-play-state` 切换；动效分级 off 档不转）；
 * - 播放/暂停 = **参考旋律试听**（真音频，由页面侧 `useReferenceAudio` 驱动）；
 * - 红心 = 收藏（服务端 `favorited` 真源，页面侧 toggleFavorite）；
 * - 队列 = 打开选曲弹层（本页 SingSongPickerSheet）。
 *
 * 本组件**纯展示**：不持有播放状态、不直接调接口（数据与动作都由页面传入/回抛）。
 */
import { computed, ref } from 'vue'

import { mediaUrl } from '@/api/media'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

const props = defineProps<{
  song: SongSummary
  /** 参考旋律是否在播（转盘转动/按钮图标） */
  playing: boolean
}>()
const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'open', id: number): void
  (e: 'queue'): void
  (e: 'favorite', song: SongSummary): void
}>()

const coverSrc = computed(() => mediaUrl(props.song.cover_url))
const coverFailed = ref(false)
/** 署名：`·` 前第一段（与列表/英雄卡同口径） */
const artist = computed(() => (props.song.artist ?? '').split('·')[0].trim() || '歌单')
const stateText = computed(() => (props.playing ? '正在试听参考旋律' : '点击试听参考旋律'))
</script>

<template>
  <div class="m-sing-mini" role="group" aria-label="试听播放条">
    <button class="m-sing-mini__disc" type="button" :class="{ 'is-on': playing }" :aria-label="`打开 ${song.title} 跟唱`" @click="emit('open', song.id)">
      <img
        v-if="coverSrc && !coverFailed"
        :src="coverSrc"
        alt=""
        loading="lazy"
        decoding="async"
        @error="coverFailed = true"
      >
      <MobileIcon v-else name="note" :size="16" />
    </button>

    <button class="m-sing-mini__info" type="button" @click="emit('open', song.id)">
      <strong class="m-sing-mini__title">{{ song.title }}</strong>
      <span class="m-sing-mini__sub">{{ artist }} · {{ stateText }}</span>
    </button>

    <button
      class="m-sing-mini__act"
      type="button"
      :class="{ 'is-fav': song.favorited }"
      :aria-pressed="song.favorited"
      :aria-label="song.favorited ? '取消收藏' : '收藏'"
      @click="emit('favorite', song)"
    >
      <MobileIcon name="heart" :size="18" />
    </button>
    <button
      class="m-sing-mini__act m-sing-mini__act--play"
      type="button"
      :aria-label="playing ? '暂停试听' : '播放试听'"
      @click="emit('toggle')"
    >
      <MobileIcon :name="playing ? 'pause' : 'play'" :size="18" />
    </button>
    <button class="m-sing-mini__act" type="button" aria-label="选曲" @click="emit('queue')">
      <MobileIcon name="music" :size="18" />
    </button>
  </div>
</template>

<style scoped>
/* 悬浮条：固定在底部 Tab 栏之上（Tab 栏 56px，见 mobile-uic.css .u-tabbar） */
.m-sing-mini {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  width: calc(100% - 20px);
  max-width: 460px;
  bottom: calc(66px + env(safe-area-inset-bottom));
  height: 48px;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px 0 5px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(25px);
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}
/* 转盘：封面圆形 + 播放时旋转（8s/圈，linear）；暂停/未播放时停在当前角度 */
.m-sing-mini__disc {
  width: 38px;
  height: 38px;
  flex: none;
  border: none;
  padding: 0;
  border-radius: 50%;
  overflow: hidden;
  background: var(--u-track, #eef1f4);
  color: var(--u-weak, #8f959e);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 8px rgba(0, 0, 0, 0.2);
  animation: m-sing-disc 8s linear infinite;
  animation-play-state: paused;
}
.m-sing-mini__disc.is-on {
  animation-play-state: running;
}
.m-sing-mini__disc img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
@keyframes m-sing-disc {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
/* 动效分级（docs/31 §2 规则 4）：系统「减少动效」/手动 off → 不转（静态封面仍在） */
html[data-motion='off'] .m-sing-mini__disc {
  animation: none;
}
html[data-motion='low'] .m-sing-mini__disc {
  animation-duration: 14s;
}

.m-sing-mini__info {
  flex: 1;
  min-width: 0;
  border: none;
  background: none;
  padding: 0 4px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 1px;
  text-align: left;
  cursor: pointer;
}
.m-sing-mini__title {
  max-width: 100%;
  font-size: 13px;
  font-weight: 700;
  color: var(--u-ink, #1f2329);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-sing-mini__sub {
  max-width: 100%;
  font-size: 10.5px;
  color: var(--u-sub, #646a73);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-sing-mini__act {
  width: 34px;
  height: 34px;
  flex: none;
  border: none;
  background: none;
  border-radius: 50%;
  color: #2f3742;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
.m-sing-mini__act:active {
  background: rgba(0, 0, 0, 0.06);
}
/* 收藏态：星黄实心（与列表行同一语义色 --u-star） */
.m-sing-mini__act.is-fav {
  color: var(--u-star, #f5a623);
}
</style>
