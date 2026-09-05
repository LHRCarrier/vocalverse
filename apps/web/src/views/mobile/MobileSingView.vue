<script setup lang="ts">
/**
 * 移动端 · 唱吧（跟唱）——ui-concept-design skill 重制版 · M3 UI 先行演示帧
 * 功能点：英文歌跟唱（选歌 → 歌词/旋律展示 → 跟唱 → 逐句音准节奏评分，docs/06 §9.4）。
 * 当前为 UI 演示帧（后端跟唱引擎 M3 接入）：选歌/去跟唱均 toast 提示，数据为示例值。
 * 视觉：深青精选卡（同色系 chip + 幽灵按钮 + 大音符线稿锚点）→ 56px 分段 → 点线时间轴歌单。
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

import IconShare from '~icons/tabler/share'

import { shareDemoLink } from '@/composables/share'
import { useUiStore } from '@/stores/ui'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()
const ui = useUiStore()

type Tab = 'all' | 'hot' | 'fav'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: 'chart' | 'note' | 'heart' }[] = [
  { key: 'all', label: '全部', icon: 'chart' },
  { key: 'hot', label: '热门', icon: 'note' },
  { key: 'fav', label: '收藏', icon: 'heart' },
]

interface Song {
  id: number
  icon: 'note' | 'headphone'
  color: string
  title: string
  sub: string
  value: string
  valueInk?: boolean
  badge: { text: string; variant: 'success' | 'star' | 'neutral' }
  tags: Tab[]
}

/* 【占位·M3】歌单示例数据（跟唱评分接入后替换） */
const songs: Song[] = [
  {
    id: 1,
    icon: 'note',
    color: '#16303A',
    title: 'Perfect Night',
    sub: 'LE SSERAFIM · 107s · 节奏轻快',
    value: '88.1',
    badge: { text: '新纪录', variant: 'star' },
    tags: ['hot'],
  },
  {
    id: 2,
    icon: 'headphone',
    color: '#1E2B26',
    title: 'Yesterday Once More',
    sub: 'Carpenters · 150s · 慢板抒情',
    value: '91.5',
    badge: { text: '优秀', variant: 'success' },
    tags: ['hot', 'fav'],
  },
  {
    id: 3,
    icon: 'note',
    color: '#232044',
    title: 'Counting Stars',
    sub: 'OneRepublic · 132s · 中速律动',
    value: '90.2',
    badge: { text: '优秀', variant: 'success' },
    tags: ['hot'],
  },
  {
    id: 4,
    icon: 'headphone',
    color: '#3A2440',
    title: 'Blank Space',
    sub: 'Taylor Swift · 148s · 中速流行',
    value: '86.0',
    badge: { text: '收藏', variant: 'success' },
    tags: ['fav'],
  },
  {
    id: 5,
    icon: 'note',
    color: '#16303A',
    title: 'City of Stars',
    sub: 'La La Land · 124s · 慢速叙事',
    value: '79.5',
    valueInk: true,
    badge: { text: '待提升', variant: 'neutral' },
    tags: [],
  },
]

const visibleSongs = computed(() =>
  tab.value === 'all' ? songs : songs.filter((s) => s.tags.includes(tab.value)),
)

/* ---------- 演示交互 toast（跟唱引擎 M3 后替换为真实跳转） ---------- */
function demoComingSoon(feature: string) {
  ui.showToast(`「${feature}」：跟唱引擎 M3 上线后开放`)
}

/** 顶栏 · 分享歌曲（演示：系统面板 / 复制链接） */
async function shareSong() {
  const result = await shareDemoLink({
    title: 'Perfect Night · LE SSERAFIM',
    text: 'VocalVerse 跟唱 · 最佳成绩 88.1 分',
    url: 'https://vocalverse.demo/song/perfect-night',
  })
  if (result === 'shared') ui.showToast('已分享')
  else if (result === 'copied') ui.showToast('歌曲链接已复制（演示链接）')
  else if (result === 'failed') ui.showToast('复制失败，请手动复制')
}
</script>

<template>
  <div class="u-phone">
    <!-- 统一顶栏（← 回学习主页 + 全局头像 / 唱吧 / 分享歌曲） -->
    <MobileTopBar title="唱吧" back @back="router.push('/m/learn')">
      <template #actions>
        <button class="u-topbar__act" type="button" title="分享歌曲（演示）" aria-label="分享歌曲" @click="shareSong">
          <IconShare />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content">
      <p class="u-head__sub" style="margin: 0 0 16px">英文歌逐句跟唱，音准与节奏即时评分。</p>

      <!-- 本周精选（深青卡 · 每屏唯一深色卡 · 音符线稿锚点） -->
      <section class="u-dark-card u-dark-card--teal">
        <div class="u-dark-card__art" aria-hidden="true">
          <MobileArt name="note" :size="104" />
        </div>
        <span class="u-chip u-chip--teal">本周精选</span>
        <span class="u-dark-card__meta">LE SSERAFIM · 107s · 全曲跟唱</span>
        <h2 class="u-dark-card__title">Perfect Night</h2>
        <p class="u-dark-card__desc">上一遍 88.1 分 · 音准 93 · 节奏 91，稳住节奏就能破 90。</p>
        <button class="u-btn u-btn--ghost" type="button" style="margin-top: 16px" @click="demoComingSoon('去跟唱')">
          <MobileIcon name="mic" :size="16" /> 去跟唱
        </button>
        <div class="u-dark-card__score">
          <div class="label">最佳成绩</div>
          <div class="num">88.1</div>
        </div>
      </section>

      <!-- 分段筛选（56px） -->
      <div class="u-segment" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          role="tab"
          :aria-selected="tab === t.key"
          :class="{ active: tab === t.key }"
          @click="tab = t.key"
        >
          <MobileIcon :name="t.icon" />{{ t.label }}
        </button>
      </div>

      <!-- 歌单（点线时间轴） -->
      <div class="u-section-title">歌曲库</div>
      <template v-for="(s, i) in visibleSongs" :key="s.id">
        <button class="u-item" type="button" style="width: 100%; text-align: left" @click="demoComingSoon(s.title)">
          <span class="u-icon-block" :style="{ background: s.color }">
            <MobileIcon :name="s.icon" :size="22" />
          </span>
          <span class="u-item__main">
            <span class="u-item__title">{{ s.title }}</span>
            <span class="u-item__sub">{{ s.sub }}</span>
          </span>
          <span class="u-item__right">
            <span class="u-item__value" :class="{ 'u-item__value--ink': s.valueInk }">{{ s.value }}</span>
            <span class="u-badge" :class="`u-badge--${s.badge.variant}`">{{ s.badge.text }}</span>
          </span>
        </button>
        <div v-if="i < visibleSongs.length - 1" class="u-dotline" aria-hidden="true">
          <span class="dot" /><span class="line" />
        </div>
      </template>
      <div v-if="!visibleSongs.length" class="u-empty">
        <div class="u-empty__art"><MobileArt name="note" :size="96" /></div>
        <div class="u-empty__title">这个分类还没有歌</div>
        <div class="u-empty__sub">M3 跟唱引擎接入后，这里会展示给你的推荐歌单。</div>
      </div>

      <p class="u-note" style="margin-top: 24px">
        当前为 UI 演示帧（M3 接入基频提取 + DTW 对齐评分），歌曲与成绩为示例数据。
      </p>
    </div>
  </div>
</template>
