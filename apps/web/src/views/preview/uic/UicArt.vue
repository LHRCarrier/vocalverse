<script setup lang="ts">
/**
 * UIC 概念原型 · 手绘线稿插画（视觉锚点）
 * 规格（skill §插画/线稿）：ink #1C1C1A、2.5px 圆头线、留白呼吸感；
 * 单色填涂只允许 pop-green #A8E05F（弱化版 #C6EF8D）。母题参照 ref-landing-hero-light。
 * 鼠标停留微微飘动（≤200ms，无弹跳）。
 */
defineProps<{ name: 'balloon' | 'calendar' | 'spark' | 'mic-big' | 'note-big' }>()
</script>

<template>
  <svg
    viewBox="0 0 320 340"
    fill="none"
    stroke="#1C1C1A"
    stroke-width="2.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    class="uic-art"
  >
    <!-- 热气球：竖向肋线 + 吊篮涂绿 -->
    <template v-if="name === 'balloon'">
      <path d="M160 24 C 96 24 52 92 52 156 C 52 220 96 268 160 268 C 224 268 268 220 268 156 C 268 92 224 24 160 24 Z" />
      <path d="M160 24 C 130 84 130 220 160 268" />
      <path d="M160 24 C 194 84 194 220 160 268" />
      <path d="M82 92 C 120 140 200 140 238 92" />
      <path d="M62 168 C 110 206 210 206 258 168" />
      <path d="M160 268 L 128 292 M160 268 L 160 292 M160 268 L 192 292" />
      <path d="M128 292 L 192 292" />
      <path d="M104 292 L 104 322 C 104 330 112 336 120 336 L 200 336 C 208 336 216 330 216 322 L 216 292 Z" stroke-width="2.5" fill="#A8E05F" class="uic-art__fill" />
      <path d="M112 240 C 130 218 190 218 208 240" stroke-width="2" />
    </template>

    <!-- 日历：双环 + 网格 + 一格涂绿 + 勾 -->
    <template v-else-if="name === 'calendar'">
      <path d="M76 92 L 76 60 C 76 46 88 36 102 36 L 218 36 C 232 36 244 46 244 60 L 244 92" fill="#fff" />
      <rect x="76" y="92" width="168" height="188" rx="20" fill="#fff" />
      <rect x="92" y="112" width="136" height="14" rx="7" fill="#E8E6E0" />
      <path d="M92 168 L 228 168 L 228 252 L 92 252 Z" />
      <path d="M138 168 L 138 252 M184 168 L 184 252 M92 210 L 228 210" />
      <path d="M106 178 L 122 194 L 148 166" />
      <path d="M104 226 L 104 248 L 134 248 L 134 226 Z" fill="#A8E05F" class="uic-art__fill" />
      <circle cx="124" cy="26" r="12" fill="#fff" />
      <circle cx="196" cy="26" r="12" fill="#fff" />
      <circle cx="124" cy="26" r="5" fill="none" />
      <circle cx="196" cy="26" r="5" fill="none" />
      <path d="M60 108 L 52 98 M60 120 L 48 116" stroke-width="2" />
    </template>

    <!-- 星星（四角闪）：尖角随机歪一歪，更像手绘 -->
    <template v-else-if="name === 'spark'">
      <path d="M60 20 L 78 66 L 124 84 L 78 102 L 60 148 L 42 102 L -4 84 L 42 66 Z" fill="none" />
      <path d="M60 20 L 62 66 M60 148 L 62 102" stroke-width="1.8" />
      <path d="M232 118 L 244 146 L 272 158 L 244 170 L 232 198 L 220 170 L 192 158 L 220 146 Z" fill="none" />
    </template>

    <!-- 大麦克风（英雄区左侧备用母题） -->
    <template v-else-if="name === 'mic-big'">
      <rect x="118" y="24" width="84" height="150" rx="42" fill="#fff" />
      <path d="M150 60 L 150 138 M170 60 L 170 138" stroke-width="1.8" />
      <path d="M86 128 C 86 190 234 190 234 128" />
      <path d="M160 190 L 160 268" />
      <path d="M128 268 L 192 268" />
      <path d="M136 268 L 136 296 C 136 306 146 312 156 312 L 164 312 C 174 312 184 306 184 296 L 184 268 Z" fill="#A8E05F" class="uic-art__fill" />
    </template>

    <!-- 大音符：符头涂绿 + 飘带 -->
    <template v-else-if="name === 'note-big'">
      <path d="M196 28 L 196 184" />
      <path d="M196 28 C 196 28 232 40 252 60 C 262 70 264 92 250 102" />
      <ellipse cx="186" cy="196" rx="34" ry="26" fill="#A8E05F" class="uic-art__fill" />
      <ellipse cx="250" cy="118" rx="30" ry="24" fill="#fff" />
      <path d="M110 96 L 88 128 M96 72 L 70 96" stroke-width="2" />
      <path d="M92 236 C 120 214 200 214 232 240" stroke-width="2" />
    </template>
  </svg>
</template>

<style scoped>
.uic-art {
  display: block;
  width: 100%;
  height: auto;
  transition: transform 200ms ease-out;
}

.uic-art:hover {
  transform: translateY(-4px);
}

.uic-art__fill {
  filter: drop-shadow(0 0 0 transparent);
}
</style>
