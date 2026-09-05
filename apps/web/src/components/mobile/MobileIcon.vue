<script setup lang="ts">
/**
 * 移动端线性图标（Lucide 风格 · 统一 stroke-width 1.5 / 圆头圆角）
 * 本组件只提供图标——图标必须配文字；icon-only 按钮必须带 title/tooltip。
 */
const props = withDefaults(
  defineProps<{
    name:
      | 'home'
      | 'mic'
      | 'note'
      | 'user'
      | 'plus'
      | 'back'
      | 'chevron'
      | 'clock'
      | 'flame'
      | 'star'
      | 'chart'
      | 'coffee'
      | 'briefcase'
      | 'book'
      | 'headphone'
      | 'wave'
      | 'check'
      | 'refresh'
      | 'logout'
      | 'info'
      | 'heart'
      | 'music'
      | 'arrow'
      | 'stop'
      | 'volume'
    size?: number
  }>(),
  { size: 20 },
)
</script>

<template>
  <svg
    :width="props.size"
    :height="props.size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.5"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- 家 -->
    <template v-if="props.name === 'home'">
      <path d="M4 20V4M4 20h16" />
      <path d="M8 16v-5M12 16V7M16 16v-3" />
    </template>

    <!-- 麦克风 -->
    <template v-else-if="props.name === 'mic'">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </template>

    <!-- 音符 -->
    <template v-else-if="props.name === 'note' || props.name === 'music'">
      <path d="M9 18V6l10-2v12" />
      <circle cx="6.5" cy="18" r="2.5" />
      <circle cx="16.5" cy="16" r="2.5" />
    </template>

    <!-- 人 -->
    <template v-else-if="props.name === 'user'">
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M5 20a7 7 0 0 1 14 0" />
    </template>

    <!-- 加号 -->
    <template v-else-if="props.name === 'plus'">
      <path d="M12 4.5v9M7.5 9h9" />
    </template>

    <!-- 返回（左箭头） -->
    <template v-else-if="props.name === 'back'">
      <path d="M15 5l-7 7 7 7" />
    </template>

    <!-- 右箭头（列表跳转） -->
    <template v-else-if="props.name === 'chevron'">
      <path d="M9 5l7 7-7 7" />
    </template>

    <!-- 发送（右箭头 · 2026-09-05 补：联合类型已声明但缺模板 → 发送按钮渲染成空圆圈） -->
    <template v-else-if="props.name === 'arrow'">
      <path d="M5 12h14" />
      <path d="M13 5.5l6.5 6.5-6.5 6.5" />
    </template>

    <!-- 时钟（回合） -->
    <template v-else-if="props.name === 'clock'">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </template>

    <!-- 火焰（连续打卡） -->
    <template v-else-if="props.name === 'flame'">
      <path d="M12 3.5c1 2.5 4.5 4 4.5 8.5a4.5 4.5 0 0 1-9 0c0-1.8.8-3 1.7-4.2.4 1 .9 1.6 1.8 2.2-.3-2.2.2-4.6 1-6.5z" />
    </template>

    <!-- 五角星（收藏/评分） -->
    <template v-else-if="props.name === 'star'">
      <path d="M12 3.8l2.4 4.8 5.4.8-3.9 3.8.9 5.4-4.8-2.6-4.8 2.6.9-5.4-3.9-3.8 5.4-.8z" />
    </template>

    <!-- 柱状图（报表） -->
    <template v-else-if="props.name === 'chart'">
      <path d="M4 20V4M4 20h16" />
      <path d="M8 16v-5M12 16V7M16 16v-3" />
    </template>

    <!-- 咖啡（场景） -->
    <template v-else-if="props.name === 'coffee'">
      <path d="M5 9h11v5a5 5 0 0 1-5 5H10a5 5 0 0 1-5-5z" />
      <path d="M16 10h1.5a2.5 2.5 0 0 1 0 5H16" />
    </template>

    <!-- 公文包（面试场景） -->
    <template v-else-if="props.name === 'briefcase'">
      <rect x="4" y="8" width="16" height="12" rx="3" />
      <path d="M9 8V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2" />
    </template>

    <!-- 书（学习） -->
    <template v-else-if="props.name === 'book'">
      <path d="M5 4h9a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3z" />
      <path d="M5 4v13M17 20v-8" />
    </template>

    <!-- 耳机（跟唱） -->
    <template v-else-if="props.name === 'headphone'">
      <path d="M4 13a8 8 0 0 1 16 0" />
      <rect x="3.5" y="13" width="4" height="6" rx="2" />
      <rect x="16.5" y="13" width="4" height="6" rx="2" />
    </template>

    <!-- 声波（AI 数字人） -->
    <template v-else-if="props.name === 'wave'">
      <path d="M3 12h2M7 8v8M11 5v14M15 8v8M19 12h2" />
    </template>

    <!-- 对勾 -->
    <template v-else-if="props.name === 'check'">
      <path d="M5 12.5l4.5 4.5L19 7.5" />
    </template>

    <!-- 重试 -->
    <template v-else-if="props.name === 'refresh'">
      <path d="M20 12a8 8 0 1 1-2.3-5.6" />
      <path d="M20 3.5V7h-3.5" />
    </template>

    <!-- 退出 -->
    <template v-else-if="props.name === 'logout'">
      <path d="M14 4H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h7" />
      <path d="M17 8l4 4-4 4M21 12H10" />
    </template>

    <!-- 信息 -->
    <template v-else-if="props.name === 'info'">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5M12 7.5h.01" />
    </template>

    <!-- 心形（收藏歌曲） -->
    <template v-else-if="props.name === 'heart'">
      <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />
    </template>

    <!-- 停止（实心方块 · 录音中） -->
    <template v-else-if="props.name === 'stop'">
      <path d="M7 7h10v10H7z" stroke-width="2" />
    </template>
    <!-- 音量（重听）：加粗圆润版（2.4px 圆头 + 实底音箱体） -->
    <template v-else-if="props.name === 'volume'">
      <path d="M4.5 9.7v4.6h3.2l4.6 3.9V5.8l-4.6 3.9H4.5Z" fill="currentColor" stroke="none" />
      <path d="M15.6 9.2a4.3 4.3 0 0 1 0 5.6" stroke-width="2.4" />
      <path d="M18.3 6.6a8.2 8.2 0 0 1 0 10.8" stroke-width="2.4" />
    </template>
  </svg>
</template>
