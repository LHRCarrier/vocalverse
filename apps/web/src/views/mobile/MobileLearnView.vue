<script setup lang="ts">
/**
 * 移动端 · 学习（2026-09-05 组长拍板：原「练习首页」重建为「学习」页，内容全部清空）
 * 展示焦点 = **用户学习画像**（组长设计中：哪些数据、怎么展示、能否「扫一眼明白大量信息」）。
 * 数据源（M3 排期，docs/02 学习画像演进）：讯飞词级错误/发音分 → 薄弱音素、高频错误词、
 * 流利度趋势、场景覆盖度；本页暂为画像占位，画像方案定稿后填充。
 * 场景对话 / 唱吧 / 自由对话入口 = 学习组底栏（☕ / 🎵 / 💬），本页不再重复。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="学习" />

    <!-- 学习画像占位（画像方案定稿后填充；u-comm-empty 复用） -->
    <div class="u-comm-empty" role="status">
      <span class="u-comm-empty__icon"><MobileIcon name="chart" :size="28" /></span>
      <p class="u-comm-empty__title">学习画像 · 建设中</p>
      <p class="u-comm-empty__sub">音素 · 词级错误 · 流利度趋势 · 场景覆盖度（M3 排期）</p>
    </div>
  </div>
</template>
