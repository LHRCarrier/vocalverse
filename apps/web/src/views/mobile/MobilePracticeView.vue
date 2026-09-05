<script setup lang="ts">
/**
 * 移动端 · 练习 Hub（2026-09-05 组长拍板：底部 5 位对称，口语/唱吧合并入口）
 * 三张入口卡：场景对话（/m/chat）· 自由对话（/m/free-chat）· 唱吧（/m/sing）——
 * 均从本 Hub 进入（tab 栏自动隐藏为二级页）；docs/14 §12 口语 Hub 思路的合并版。
 * 样式复用既有 u-hub-card 系（原口语 Hub）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="练习" />

    <div class="u-content">
      <RouterLink to="/m/chat" class="u-hub-card">
        <span class="u-hub-card__icon u-hub-card__icon--scene"><MobileIcon name="coffee" :size="18" /></span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">场景对话</span>
          <span class="u-hub-card__desc">8 套预置场景 · AI 实时对聊 · 三维评分</span>
        </span>
        <MobileIcon name="chevron" :size="18" class="u-hub-card__go" />
      </RouterLink>

      <RouterLink to="/m/free-chat" class="u-hub-card">
        <span class="u-hub-card__icon" style="background: var(--u-dark-purple)">
          <MobileIcon name="wave" :size="18" />
        </span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">自由对话</span>
          <span class="u-hub-card__desc">麦克风或打字 · 想聊就聊 · TTS 语音播报</span>
        </span>
        <MobileIcon name="chevron" :size="18" class="u-hub-card__go" />
      </RouterLink>

      <RouterLink to="/m/sing" class="u-hub-card">
        <span class="u-hub-card__icon" style="background: var(--u-dark-navy)">
          <MobileIcon name="note" :size="18" />
        </span>
        <span class="u-hub-card__body">
          <span class="u-hub-card__title">唱吧</span>
          <span class="u-hub-card__desc">英文歌跟唱 · 音准 / 节奏 / 发音逐句评分</span>
        </span>
        <MobileIcon name="chevron" :size="18" class="u-hub-card__go" />
      </RouterLink>

      <p class="u-note" style="text-align: center; margin-top: 24px">
        口语与跟唱引擎 M3 接入后开放真实链路。
      </p>
    </div>
  </div>
</template>
