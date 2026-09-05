<script setup lang="ts">
/**
 * 深色焦点卡装饰插画（自绘 · 参考图日历涂鸦：线稿日历 + 大对勾 + 星芒，微旋转）
 * 白色系线稿（深蓝渐变卡上用），弱存在不抢文字（opacity 由外层控制）
 */
defineProps<{ size?: number }>()
</script>

<template>
  <svg
    :width="size ?? 116"
    :height="size ?? 116"
    viewBox="0 0 116 116"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <g transform="rotate(-10 58 58)">
      <!-- 日历线稿 -->
      <rect x="26" y="26" width="62" height="60" rx="10" stroke="#fff" stroke-width="2.5" />
      <path d="M26 44 h62" stroke="#fff" stroke-width="2.5" />
      <path d="M40 20 v14 M74 20 v14" stroke="#fff" stroke-width="3" stroke-linecap="round" />
      <!-- 大对勾 -->
      <path d="M40 58 l10 12 24 -28" stroke="#fff" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" />
      <!-- 星芒 -->
      <path d="M92 36 l2.5 6.5 6.5 2.5 -6.5 2.5 -2.5 6.5 -2.5 -6.5 -6.5 -2.5 6.5 -2.5 Z" fill="#fff" opacity="0.85" />
      <path d="M14 66 l2 5 5 2 -5 2 -2 5 -2 -5 -5 -2 5 -2 Z" fill="#fff" opacity="0.5" />
    </g>
  </svg>
</template>
