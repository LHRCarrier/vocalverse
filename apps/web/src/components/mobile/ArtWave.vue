<script setup lang="ts">
/**
 * 登录页品牌插画（自绘 · 参考 BREAKOUT 线稿语言：2.5px 圆头线稿 + 单色填涂 + 星芒点缀）
 * 构图：柔和蓝底椭圆 → 三条声波线稿 → 星芒（1 黄 1 蓝）→ 底部描边弧线
 */
defineProps<{ size?: number }>()
</script>

<template>
  <svg
    :width="size ?? 200"
    :height="size ?? 176"
    viewBox="0 0 220 176"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    aria-hidden="true"
  >
    <!-- 底：柔和蓝椭圆 -->
    <ellipse cx="110" cy="88" rx="96" ry="74" fill="#D6EFFC" />
    <!-- 声波线稿（2.5px 圆头） -->
    <path
      d="M28 92 Q66 52 104 92 T180 92"
      stroke="#0284C7"
      stroke-width="4"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M44 112 Q82 76 120 112 T196 112"
      stroke="#0284C7"
      stroke-opacity="0.45"
      stroke-width="4"
      stroke-linecap="round"
      fill="none"
    />
    <path
      d="M60 70 Q98 34 136 70 T196 70"
      stroke="#0284C7"
      stroke-opacity="0.25"
      stroke-width="4"
      stroke-linecap="round"
      fill="none"
    />
    <!-- 星芒（参考图 sparkle：四角星）+ 小圆点 -->
    <path
      d="M158 44 l4 10 10 4 -10 4 -4 10 -4 -10 -10 -4 10 -4 Z"
      fill="#FBBF24"
    />
    <path d="M52 44 l3 7 7 3 -7 3 -3 7 -3 -7 -7 -3 7 -3 Z" fill="#38BDF8" />
    <circle cx="188" cy="140" r="5" fill="#38BDF8" opacity="0.7" />
    <circle cx="34" cy="132" r="3.5" fill="#9B8FBB" opacity="0.8" />
  </svg>
</template>
