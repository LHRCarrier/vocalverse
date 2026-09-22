<script setup lang="ts">
/**
 * 唱吧 · 页内底部 Tab 栏（2026-09-23 用户原型 1:1 复刻，唱吧独用一套）。
 *
 * 为什么独立：全局 `MobileTabBar` 是「社区/学习」双场景分组（docs/31），而用户口径是
 * 「上下 tab 都换掉，唱吧独用一套，按 html 一比一复刻」——本页按原型自带
 * 首页 / 视频 / 刷歌 / 星光 / 我的 五项（全局底栏在 /m/sing 不再渲染，见 MobileTabBar group）。
 *
 * 内容接真（原型点击只弹 toast，这里能接真的都接真）：
 * - 首页 → `/m/home`（社区首页）；
 * - 刷歌 → 当前页（激活态，不跳转）；
 * - 我的 → 全局账户抽屉（`ui.openDrawer()`）；
 * - 视频 / 星光 → 无对应能力，toast「后续版本」（不假装有页面）。
 */
import IconDisc from '~icons/tabler/disc'
import IconHome from '~icons/tabler/home'
import IconMovie from '~icons/tabler/movie'
import IconStar from '~icons/tabler/star'
import IconUser from '~icons/tabler/user'
import { useRouter } from 'vue-router'

import { useUiStore } from '@/stores/ui'

const router = useRouter()
const ui = useUiStore()

function goHome() {
  void router.push('/m/home')
}
function openMine() {
  ui.openDrawer()
}
function soon(label: string) {
  ui.showToast(`${label} · 后续版本`)
}
</script>

<template>
  <nav class="m-sing-tabbar" aria-label="唱吧底部导航">
    <button class="m-sing-tab" type="button" @click="goHome">
      <IconHome />
      <span>首页</span>
    </button>
    <button class="m-sing-tab" type="button" @click="soon('视频')">
      <IconMovie />
      <span>视频</span>
    </button>
    <button class="m-sing-tab active" type="button" aria-current="page" @click="soon('刷歌')">
      <IconDisc />
      <span>刷歌</span>
    </button>
    <button class="m-sing-tab" type="button" @click="soon('星光')">
      <IconStar />
      <span>星光</span>
    </button>
    <button class="m-sing-tab" type="button" @click="openMine">
      <IconUser />
      <span>我的</span>
    </button>
  </nav>
</template>

<style scoped>
/* 原型口径：白底 + 上发丝线；激活项 = 黑（未激活 = 中灰），图标 21px / 文案 10px */
.m-sing-tabbar {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: 0;
  z-index: 40;
  width: 100%;
  max-width: 480px;
  height: calc(54px + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  display: flex;
  align-items: center;
  justify-content: space-around;
  background: #fff;
  border-top: 1px solid #eceef1;
}
.m-sing-tab {
  flex: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border: none;
  background: none;
  color: #717a84;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
}
.m-sing-tab svg {
  width: 21px;
  height: 21px;
}
.m-sing-tab.active {
  color: #111;
}
</style>
