<script setup lang="ts">
/**
 * 唱吧 · 顶部区（搜索胶囊 + 图标工具 + 横滑分类）—— 2026-09-23 用户原型 1:1 复刻。
 *
 * 为什么抽组件：本页视图受 `max-lines` 门禁约束（eslint max 350），且这块与页面状态无关
 * （纯展示 + 三个事件），抽出后页面只保留业务绑定。
 *
 * 原型对照：搜索胶囊（`search-capsule`）+ 两颗图标工具（原型的「听歌识曲/福利中心」无对应能力，
 * 换成真实入口：选曲 / 分享）；分类行 6 项横滑、激活态绿色药丸。整块 sticky 常驻（原型同款）。
 */
import IconShare from '~icons/tabler/share'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

export interface SingCat {
  key: string
  label: string
  real: boolean
}

defineProps<{
  /** 胶囊文案里的「猜你想唱」曲名（null → 占位文案） */
  songTitle: string | null
  cats: readonly SingCat[]
  /** 当前激活分类 key（仅 real 项会亮） */
  activeKey: string
  /** 是否已有选中曲目（图标工具的高亮态） */
  picked: boolean
}>()

const emit = defineEmits<{
  (e: 'pick'): void
  (e: 'share'): void
  (e: 'cat', cat: SingCat): void
}>()
</script>

<template>
  <div class="m-sing-toparea">
    <header class="m-sing-head">
      <button class="m-sing-search" type="button" aria-label="选择跟唱曲目" @click="emit('pick')">
        <span class="m-sing-search__icon"><MobileIcon name="search" :size="13" /></span>
        <span class="m-sing-search__text">猜你想唱：{{ songTitle ?? '选一首歌' }}</span>
      </button>
      <button
        class="m-sing-head__tool m-sing-pick-entry"
        :class="{ 'is-on': picked }"
        type="button"
        title="选择跟唱曲目"
        aria-label="选择跟唱曲目"
        @click="emit('pick')"
      >
        <MobileIcon name="music" :size="20" />
      </button>
      <button class="m-sing-head__tool" type="button" title="分享歌曲" aria-label="分享歌曲" @click="emit('share')">
        <IconShare />
      </button>
    </header>

    <nav class="m-sing-cats" role="tablist" aria-label="曲库分类">
      <button
        v-for="t in cats"
        :key="t.key"
        class="m-sing-cat"
        :class="{ active: t.real && activeKey === t.key }"
        type="button"
        role="tab"
        :aria-selected="t.real && activeKey === t.key"
        @click="emit('cat', t)"
      >
        {{ t.label }}
      </button>
    </nav>
  </div>
</template>
