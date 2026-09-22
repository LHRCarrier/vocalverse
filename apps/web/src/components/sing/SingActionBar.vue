<script setup lang="ts">
/**
 * 跟唱面板底部控制条（2026-09-22 深色录唱页重做：对齐参考图的「两左 + 中主钮 + 两右」五键；
 * 2026-09-21 追加**选曲**键 → 现为六键）。
 *
 * 参考图五键 = 原唱 / 调音 / **暂停** / 重录 / 完成；我们**只放真实能力**（AskUserQuestion 已拍板
 * 「调音」不做——没有音效处理能力，不做点了没用的钮），于是：
 *   左：**原唱**（听参考旋律 ⇄ 停止，录音中禁用）/ **曲线**（实时曲线开关，只管显示）/
 *       **选曲**（打开跟唱曲目列表；2026-09-21 加，见下）
 *   中：**开始跟唱 ⇄ 暂停 ⇄ 继续**（录音暂停为 2026-09-22 新增能力，见 `VoiceRecorder.pause`）
 *   右：**重录**（放弃本次，不上传）/ **完成**（停止并评分；未录音时禁用）
 * 各键**常驻**（不做显示/隐藏切换）：位置稳定 → 不会有「按到一半按钮换地方」的问题。
 *
 * **为什么左右各套一层 `__group`**（2026-09-21）：旧布局是「N 个 `flex:1` 键 + 中间一个定宽主钮」，
 * 主钮居中**依赖左右键数相等**；加第 6 键后变成 3|2，主钮会被顶偏约 29px（375px 宽实测）。
 * 改成「左右两组各 `flex:1`」后，主钮由结构本身居中，与两侧键数无关（加/减键都不会漂）。
 *
 * **选曲键的行为**：只打开列表（`emit('pick')`，由视图挂 `SingSongPickerSheet`），**不在这里切歌**；
 * 真正切歌走页面既有的 `openSong()`（先停原唱 + 停录音 + 作废在飞轮询 = 「先停止再切换」，
 * 与跟唱中切曲的用户口径一致）。上传/评分中禁用：避免把在飞的评分任务打断（与「重录」同口径）。
 *
 * 可访问性：图标 + 短标签同时呈现；动作全名放 `aria-label`（测试与联调脚本据此定位）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'

const props = defineProps<{
  /** 录音中（含暂停） */
  recording: boolean
  /** 暂停中（中心钮变「继续」、外圈变暂停色） */
  paused: boolean
  /** 上传/评分中（中心钮与两侧禁用） */
  processing: boolean
  /** 参考旋律在播（决定左一键文案与图标） */
  refPlaying: boolean
  /** 实时曲线是否显示（只管显示，检测照常跑） */
  liveOn: boolean
}>()

const emit = defineEmits<{
  (e: 'toggleReference'): void
  (e: 'start'): void
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'stop'): void
  (e: 'cancel'): void
  (e: 'toggleLive'): void
  /** 打开跟唱曲目列表（切歌由视图经 openSong 完成，见文件头注释） */
  (e: 'pick'): void
}>()

/** 中心钮：未录音 → 开始；暂停中 → 继续；录音中 → 暂停 */
const mainAction = () => (!props.recording ? emit('start') : props.paused ? emit('resume') : emit('pause'))
const mainLabel = () => (!props.recording ? '开始跟唱' : props.paused ? '继续跟唱' : '暂停跟唱')
const mainIcon = () => (!props.recording ? 'mic' : props.paused ? 'play' : 'pause')
</script>

<template>
  <div class="m-sing-dock" :class="{ 'is-recording': recording, 'is-paused': paused }">
    <!-- 左组：听/显示/选曲（3 键）。左右两组各 flex:1 → 主钮恒居中，与键数无关 -->
    <div class="m-sing-dock__group">
      <button
        class="m-sing-dock__key"
        type="button"
        :disabled="processing || recording"
        :aria-label="refPlaying ? '停止参考旋律' : '听参考旋律'"
        @click="emit('toggleReference')"
      >
        <MobileIcon :name="refPlaying ? 'pause' : 'headphone'" :size="20" />
        <span>{{ refPlaying ? '停止原唱' : '原唱' }}</span>
      </button>

      <button
        class="m-sing-dock__key"
        :class="{ 'is-on': liveOn }"
        type="button"
        :aria-pressed="liveOn"
        aria-label="实时曲线"
        @click="emit('toggleLive')"
      >
        <MobileIcon name="chart" :size="20" />
        <span>曲线</span>
      </button>

      <!-- 选曲（2026-09-21）：打开跟唱曲目列表；跟唱中**可用**（选了新曲由视图先停录再切） -->
      <button
        class="m-sing-dock__key"
        type="button"
        :disabled="processing"
        aria-label="选择跟唱曲目"
        @click="emit('pick')"
      >
        <MobileIcon name="music" :size="20" />
        <span>选曲</span>
      </button>
    </div>

    <button
      class="m-sing-dock__main"
      :class="{ 'is-rec': recording && !paused, 'is-paused': paused }"
      type="button"
      :disabled="processing"
      :aria-label="mainLabel()"
      @click="mainAction()"
    >
      <MobileIcon :name="mainIcon()" :size="28" />
    </button>

    <!-- 右组：结束本轮（重录 / 完成） -->
    <div class="m-sing-dock__group">
      <button
        class="m-sing-dock__key"
        type="button"
        :disabled="!recording || processing"
        aria-label="放弃重录"
        @click="emit('cancel')"
      >
        <MobileIcon name="refresh" :size="20" />
        <span>重录</span>
      </button>

      <button
        class="m-sing-dock__key m-sing-dock__key--done"
        type="button"
        :disabled="!recording || processing"
        aria-label="停止并评分"
        @click="emit('stop')"
      >
        <MobileIcon name="check" :size="20" />
        <span>完成</span>
      </button>
    </div>
  </div>
</template>
