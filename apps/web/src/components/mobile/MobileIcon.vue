<script setup lang="ts">
/**
 * 移动端线性图标（**Tabler Icons 官方 path · MIT · 与底部 Tab 同源**）
 *
 * 2026-09-06 组长拍板「方案 A 全局统一」：本组件作为唯一图标层，内部 34 个图标全部
 * 换为 @iconify-json/tabler 官方路径（服务端渲染同源同规格 stroke-width 2 / 圆头圆角），
 * API 不变、47 处使用点零改动。规范：**新图标只从 Tabler 取**（规模 ≤40 显示名足量）；
 * 装饰性插画（UicArt 手绘线稿等）不算图标，允许独立。
 * icon-only 按钮必须带 title/tooltip（docs/35 硬规则）。
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
      | 'play'
      | 'chat'
      | 'coin'
      | 'share'
      | 'user-plus'
      | 'stop'
      | 'volume'
      | 'mail'
      | 'bell'
      | 'settings'
      | 'search'
      | 'hash'
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
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <!-- home (tabler: home) -->
    <template v-if="props.name === 'home'">
      <path d="M5 12H3l9-9l9 9h-2M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7" />
      <path d="M9 21v-6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v6" />
    </template>

    <!-- 麦克风 (tabler: microphone) -->
    <template v-else-if="props.name === 'mic'">
      <path d="M9 5a3 3 0 0 1 3-3a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3a3 3 0 0 1-3-3z" />
      <path d="M5 10a7 7 0 0 0 14 0M8 21h8m-4-4v4" />
    </template>

    <!-- 音符 (tabler: music) -->
    <template v-else-if="props.name === 'note' || props.name === 'music'">
      <path d="M3 17a3 3 0 1 0 6 0a3 3 0 0 0-6 0m10 0a3 3 0 1 0 6 0a3 3 0 0 0-6 0" />
      <path d="M9 17V4h10v13M9 8h10" />
    </template>

    <!-- 人 (tabler: user) -->
    <template v-else-if="props.name === 'user'">
      <path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0-8 0M6 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2" />
    </template>

    <!-- 加号 (tabler: plus) -->
    <template v-else-if="props.name === 'plus'">
      <path d="M12 5v14m-7-7h14" />
    </template>

    <!-- 返回（左箭头 · tabler: arrow-left） -->
    <template v-else-if="props.name === 'back'">
      <path d="M5 12h14M5 12l6 6m-6-6l6-6" />
    </template>

    <!-- 右箭头（列表跳转 · tabler: chevron-right） -->
    <template v-else-if="props.name === 'chevron'">
      <path d="m9 6l6 6l-6 6" />
    </template>

    <!-- 发送（右箭头 · tabler: arrow-right） -->
    <template v-else-if="props.name === 'arrow'">
      <path d="M5 12h14m-6 6l6-6m-6-6l6 6" />
    </template>

    <!-- 播放（tabler: player-play） -->
    <template v-else-if="props.name === 'play'">
      <path d="M7 4v16l13-8z" />
    </template>

    <!-- 评论（tabler: message-circle） -->
    <template v-else-if="props.name === 'chat'">
      <path d="m3 20l1.3-3.9C1.976 12.663 2.874 8.228 6.4 5.726c3.526-2.501 8.59-2.296 11.845.48c3.255 2.777 3.695 7.266 1.029 10.501S11.659 20.922 7.7 19z" />
    </template>

    <!-- 投币（tabler: coin） -->
    <template v-else-if="props.name === 'coin'">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0" />
      <path d="M14.8 9A2 2 0 0 0 13 8h-2a2 2 0 1 0 0 4h2a2 2 0 1 1 0 4h-2a2 2 0 0 1-1.8-1M12 7v10" />
    </template>

    <!-- 分享（tabler: share） -->
    <template v-else-if="props.name === 'share'">
      <path d="M3 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0m12-6a3 3 0 1 0 6 0a3 3 0 1 0-6 0m0 12a3 3 0 1 0 6 0a3 3 0 1 0-6 0m-6.3-7.3l6.6-3.4m-6.6 6l6.6 3.4" />
    </template>

    <!-- 加好友（tabler: user-plus） -->
    <template v-else-if="props.name === 'user-plus'">
      <path d="M8 7a4 4 0 1 0 8 0a4 4 0 0 0-8 0m8 12h6m-3-3v6M6 21v-2a4 4 0 0 1 4-4h4" />
    </template>

    <!-- 时钟（回合 · tabler: clock） -->
    <template v-else-if="props.name === 'clock'">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0-18 0" />
      <path d="M12 7v5l3 3" />
    </template>

    <!-- 火焰（连续打卡 · tabler: flame） -->
    <template v-else-if="props.name === 'flame'">
      <path d="M12 10.941c2.333-3.308.167-7.823-1-8.941c0 3.395-2.235 5.299-3.667 6.706C5.903 10.114 5 12 5 14.294C5 17.998 8.134 21 12 21s7-3.002 7-6.706c0-1.712-1.232-4.403-2.333-5.588c-2.084 3.353-3.257 3.353-4.667 2.235" />
    </template>

    <!-- 五角星（收藏/评分 · tabler: star） -->
    <template v-else-if="props.name === 'star'">
      <path d="m12 17.75l-6.172 3.245l1.179-6.873l-5-4.867l6.9-1l3.086-6.253l3.086 6.253l6.9 1l-5 4.867l1.179 6.873z" />
    </template>

    <!-- 柱状图（报表 · tabler: chart-bar） -->
    <template v-else-if="props.name === 'chart'">
      <path d="M3 13a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1zm12-4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1zM9 5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1zM4 20h14" />
    </template>

    <!-- 咖啡（场景 · tabler: coffee） -->
    <template v-else-if="props.name === 'coffee'">
      <path d="M3 14c.83.642 2.077 1.017 3.5 1c1.423.017 2.67-.358 3.5-1s2.077-1.017 3.5-1c1.423-.017 2.67.358 3.5 1M8 3a2.4 2.4 0 0 0-1 2a2.4 2.4 0 0 0 1 2m4-4a2.4 2.4 0 0 0-1 2a2.4 2.4 0 0 0 1 2" />
      <path d="M3 10h14v5a6 6 0 0 1-6 6H9a6 6 0 0 1-6-6z" />
      <path d="M16.746 16.726a3 3 0 1 0 .252-5.555" />
    </template>

    <!-- 公文包（面试场景 · tabler: briefcase） -->
    <template v-else-if="props.name === 'briefcase'">
      <path d="M3 9a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zm5-2V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m-4 5v.01" />
      <path d="M3 13a20 20 0 0 0 18 0" />
    </template>

    <!-- 书（学习 · tabler: book） -->
    <template v-else-if="props.name === 'book'">
      <path d="M3 19a9 9 0 0 1 9 0a9 9 0 0 1 9 0M3 6a9 9 0 0 1 9 0a9 9 0 0 1 9 0M3 6v13m9-13v13m9-13v13" />
    </template>

    <!-- 耳机（跟唱 · tabler: headphones） -->
    <template v-else-if="props.name === 'headphone'">
      <path d="M4 15a2 2 0 0 1 2-2h1a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2zm11 0a2 2 0 0 1 2-2h1a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2z" />
      <path d="M4 15v-3a8 8 0 0 1 16 0v3" />
    </template>

    <!-- 声波（AI 数字人 · tabler: wave-sine） -->
    <template v-else-if="props.name === 'wave'">
      <path d="M21 12h-2c-.894 0-1.662-.857-1.761-2c-.296-3.45-.749-6-2.749-6s-2.5 3.582-2.5 8s-.5 8-2.5 8s-2.452-2.547-2.749-6c-.1-1.147-.867-2-1.763-2h-2" />
    </template>

    <!-- 对勾 (tabler: check) -->
    <template v-else-if="props.name === 'check'">
      <path d="m5 12l5 5L20 7" />
    </template>

    <!-- 重试 (tabler: refresh) -->
    <template v-else-if="props.name === 'refresh'">
      <path d="M20 11A8.1 8.1 0 0 0 4.5 9M4 5v4h4m-4 4a8.1 8.1 0 0 0 15.5 2m.5 4v-4h-4" />
    </template>

    <!-- 退出 (tabler: logout) -->
    <template v-else-if="props.name === 'logout'">
      <path d="M14 8V6a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h7a2 2 0 0 0 2-2v-2" />
      <path d="M9 12h12l-3-3m0 6l3-3" />
    </template>

    <!-- 信息 (tabler: info-circle) -->
    <template v-else-if="props.name === 'info'">
      <path d="M3 12a9 9 0 1 0 18 0a9 9 0 0 0-18 0m9-3h.01" />
      <path d="M11 12h1v4h1" />
    </template>

    <!-- 心形（收藏歌曲 · tabler: heart） -->
    <template v-else-if="props.name === 'heart'">
      <path d="M19.5 12.572L12 20l-7.5-7.428A5 5 0 1 1 12 6.006a5 5 0 1 1 7.5 6.572" />
    </template>

    <!-- 停止（录音中 · tabler: square，线性描边） -->
    <template v-else-if="props.name === 'stop'">
      <path d="M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    </template>

    <!-- 音量（重听 · tabler: volume） -->
    <template v-else-if="props.name === 'volume'">
      <path d="M15 8a5 5 0 0 1 0 8m2.7-11a9 9 0 0 1 0 14M6 15H4a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1h2l3.5-4.5A.8.8 0 0 1 11 5v14a.8.8 0 0 1-1.5.5z" />
    </template>

    <!-- 信封（私信 · tabler: mail） -->
    <template v-else-if="props.name === 'mail'">
      <path d="M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="m3 7l9 6l9-6" />
    </template>

    <!-- 铃铛（通知 · tabler: bell） -->
    <template v-else-if="props.name === 'bell'">
      <path d="M10 5a2 2 0 1 1 4 0a7 7 0 0 1 4 6v3a4 4 0 0 0 2 3H4a4 4 0 0 0 2-3v-3a7 7 0 0 1 4-6M9 17v1a3 3 0 0 0 6 0v-1" />
    </template>

    <!-- 齿轮（设置 · tabler: settings） -->
    <template v-else-if="props.name === 'settings'">
      <path d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 0 0 2.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 0 0 1.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 0 0-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 0 0-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 0 0-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 0 0-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 0 0 1.066-2.573c-.94-1.543.826-3.31 2.37-2.37c1 .608 2.296.07 2.572-1.065" />
      <path d="M9 12a3 3 0 1 0 6 0a3 3 0 0 0-6 0" />
    </template>

    <!-- 放大镜（搜索 · tabler: search） -->
    <template v-else-if="props.name === 'search'">
      <path d="M3 10a7 7 0 1 0 14 0a7 7 0 1 0-14 0m18 11l-6-6" />
    </template>

    <!-- 话题（# · tabler: hash） -->
    <template v-else-if="props.name === 'hash'">
      <path d="M5 9h14M5 15h14M11 4L7 20M17 4l-4 16" />
    </template>
  </svg>
</template>
