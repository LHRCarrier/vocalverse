<script setup lang="ts">
/**
 * UIC 概念原型 · 线性图标（1.5px 描边，currentColor）
 * 按 skill：线性图标 + 文字；图标-only 按钮必须带 Tooltip（title）。
 */
defineProps<{ name: string }>()
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    width="20"
    height="20"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 麦克风 -->
    <template v-if="name === 'mic'">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0" />
      <path d="M12 18v3" />
    </template>
    <!-- 音符 -->
    <template v-else-if="name === 'note'">
      <path d="M9 18V6l10-2v12" />
      <circle cx="6.5" cy="18" r="2.5" />
      <circle cx="16.5" cy="16" r="2.5" />
    </template>
    <!-- 日历 -->
    <template v-else-if="name === 'calendar'">
      <rect x="4" y="5" width="16" height="16" rx="4" />
      <path d="M4 10h16M9 3v4M15 3v4" />
    </template>
    <!-- 时钟 -->
    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </template>
    <!-- 星 -->
    <template v-else-if="name === 'star'">
      <path
        d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1 5.9-5.2-2.8-5.2 2.8 1-5.9L3.5 9.7l5.9-.8z"
      />
    </template>
    <!-- 火焰 -->
    <template v-else-if="name === 'flame'">
      <path d="M12 3.5c1 2.5 4.5 4 4.5 8.5a4.5 4.5 0 0 1-9 0c0-1.8.8-3 1.7-4.2.4 1 .9 1.6 1.8 2.2-.3-2.2.2-4.6 1-6.5z" />
    </template>
    <!-- 对话气泡 -->
    <template v-else-if="name === 'chat'">
      <path d="M4 6.5A3.5 3.5 0 0 1 7.5 3h9A3.5 3.5 0 0 1 20 6.5v6a3.5 3.5 0 0 1-3.5 3.5H9l-5 4z" />
    </template>
    <!-- 播放 -->
    <template v-else-if="name === 'play'">
      <path d="M8 5.5l11 6.5-11 6.5z" />
    </template>
    <!-- 咖啡 -->
    <template v-else-if="name === 'coffee'">
      <path d="M5 9h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z" />
      <path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16" />
      <path d="M8 5.5c0-1 .8-1.2.8-2M11.5 5.5c0-1 .8-1.2.8-2" />
    </template>
    <!-- 公文包 -->
    <template v-else-if="name === 'briefcase'">
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2M4 13h16" />
    </template>
    <!-- 书本 -->
    <template v-else-if="name === 'book'">
      <path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v17H7.5A2.5 2.5 0 0 0 5 21.5z" />
      <path d="M5 17.5A2.5 2.5 0 0 1 7.5 15H19" />
    </template>
    <!-- 飞机 -->
    <template v-else-if="name === 'plane'">
      <path d="M10.5 12.5L4 9l1.5-1.5L13 9.5l4.5-4.5a1.8 1.8 0 0 1 2.5 2.5L15.5 12l2 7.5-1.5 1.5-3.5-6.5z" />
    </template>
    <!-- 检查/勾 -->
    <template v-else-if="name === 'check'">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </template>
    <!-- 图表 -->
    <template v-else-if="name === 'chart'">
      <path d="M4 20V4M4 20h16" />
      <path d="M8 16v-5M12 16V7M16 16v-3" />
    </template>
    <!-- 波形 -->
    <template v-else-if="name === 'wave'">
      <path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 12h2" />
    </template>
    <!-- 返回箭头 -->
    <template v-else-if="name === 'back'">
      <path d="M15 5l-7 7 7 7" />
    </template>
    <!-- 箭头右 -->
    <template v-else-if="name === 'arrow'">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </template>
    <!-- 耳机 -->
    <template v-else-if="name === 'headphone'">
      <path d="M4 13a8 8 0 0 1 16 0" />
      <rect x="3.5" y="13" width="4" height="6" rx="2" />
      <rect x="16.5" y="13" width="4" height="6" rx="2" />
    </template>
    <!-- 奖杯 -->
    <template v-else-if="name === 'trophy'">
      <path d="M8 4h8v6a4 4 0 0 1-8 0z" />
      <path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 14v4M8.5 20h7" />
    </template>
    <!-- 用户 -->
    <template v-else-if="name === 'user'">
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </template>
    <!-- 火花（装饰） -->
    <template v-else-if="name === 'spark'">
      <path d="M12 3l1.8 5.7L19.5 10l-5.7 1.8L12 17.5l-1.8-5.7L4.5 10l5.7-1.8z" />
    </template>
  </svg>
</template>
