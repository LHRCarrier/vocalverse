<script setup lang="ts">
/**
 * 跟唱面板歌词区（2026-09-22 按用户视频模板重排 → 同日排版优化 → 同日尺寸优化）。
 *
 * 视觉（浅色版，按视频的排版与远近表达）：
 * - **歌词占面板主区但不再吃满**：行高 `--line-h` 由**屏高**定（`clamp(42px, 6.6vh, 56px)`），
 *   卡片高度上限 = `--rows-cap`（句数 + 1，封顶 7）× 行高 + 卡头 → 6 句歌约占屏高 50%；
 * - 字号 `clamp(14px, 4vw, 17px)`（焦点 `clamp(16px, 4.6vw, 19px)`）——比上一版收小一档，
 *   与行高同步缩放，行内留白比例保持；
 * - **靠透明度渐隐表达远近**（视频里没有模糊）：焦点句最亮 + 加粗 + 略放大，越远越淡（`.is-dim-0..3`）；
 * - **无游标态（未播放/未开口）每行都取 1 级**：打开面板即可读完整首歌，不再是一片 0.2 的灰雾；
 * - 时间数字在左上（取代传统进度条；无游标时不渲染）；焦点句的**已唱部分**用绿色推进（颜色即进度）——
 *   有参考旋律时按**音符段**推进（拖长音慢慢填、快速过字迅速填、休止保持），无旋律数据回退按句长线性推进。
 *
 * 交互：
 * - 自动跟随：演唱到下一句时平滑滚到下一句居中（逐句）；
 * - **手动翻动时"始终聚焦视口中心的句子"**（用户口径）：拖动期间焦点 = 最接近视口中心的句，
 *   停手 2s 后自动归位到时间轴当前句；
 * - 留白 = (H − 行高)/2，保证**首句与末句也能滚到正中**；
 * - 无游标时**首句顶对齐**（整首歌铺满卡片）；滚动区 H 变化后（切实时曲线开关等）重新居中当前句。
 *
 * 时间轴口径见 `lib/sing-lyrics.ts`：参考播放 = 音频位置；跟唱 = 首帧人声锚点 + 已开口时长。
 * 动效约束（docs/31 规则 4）：只动 color / opacity / transform / clip-path；`motion=off` 时滚动瞬时。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { useMotionTier } from '@/composables/useMotionTier'
import type { RawLyricLines } from '@/lib/sing-lyrics'
import {
  activeLineIndex,
  dimLevel,
  formatClock,
  lineDistance,
  lineProgress,
  nearestLineIndex,
  noteSpans,
  spanProgress,
  toLyricLines,
} from '@/lib/sing-lyrics'

const props = defineProps<{
  /** 后端下发的歌词行（含 start_ms/end_ms） */
  lines: RawLyricLines
  /** 当前歌词时间轴位置（ms）；null = 未在播放/录音 */
  timeMs: number | null
}>()

const { tier } = useMotionTier()
const scroller = ref<HTMLElement | null>(null)

const lines = computed(() => toLyricLines(props.lines))
/**
 * 卡片高度上限（可见行数）：**句数 + 1，封顶 7 行**（2026-09-22 尺寸优化）。
 *
 * 卡片高度由 `.m-sing-lyrics` 的 `max-height: L × var(--rows-cap) + 卡头` 表达，本值即其中的行数上限：
 * - 6 句歌 → 7 行 ≈ 屏高 50%（旧口径吃满剩余空间 ≈ 66%）；
 * - 更短的歌卡片更矮（4 句 → 5 行），不会用一大片空白把卡片撑高；
 * - 更长的歌封顶 7 行，其余行靠滚动/时间轴推进进入视口。
 * 让出的高度归底部控制区（见 `mobile-sing.css` 的 `.m-sing-live` / `--grow`）。
 */
const rowsCap = computed(() => Math.min(lines.value.length + 1, 7))
/** 时间轴当前句（决定「已唱进度」画在哪句） */
const current = computed(() => (props.timeMs == null ? -1 : activeLineIndex(lines.value, props.timeMs)))
/** 拖动时视口中心最近的行（「始终聚焦中心的句子」） */
const centerIdx = ref(-1)
/**
 * 句内**逐字进度**（2026-09-22 用户口径「整句对得上，但唱得有快有慢，唱到哪个字对不上」）：
 * 有参考旋律（`pitch_ref.midi`）时按**音符段**推进——拖长音慢慢填、快速过字迅速填、
 * 休止保持；无旋律数据（老数据/未提取）回退按句长线性推进（原口径）。
 */
const spansByLine = computed(() => lines.value.map((l) => noteSpans(l.midi)))
const progress = computed(() => {
  if (props.timeMs == null || current.value < 0) return 0
  const line = lines.value[current.value]
  const spans = spansByLine.value[current.value] ?? []
  return (
    spanProgress(spans, line.text.length, props.timeMs - line.startMs) ??
    lineProgress(lines.value, current.value, props.timeMs)
  )
})
const clockText = computed(() => formatClock(props.timeMs))
/** 当前句已唱比例（0~1）→ 裁剪右侧未唱部分（clip-path 只影响绘制，不触发布局） */
const fillClip = computed(() => `inset(0 ${(1 - progress.value) * 100}% 0 0)`)

/** 拖动期间暂停自动滚动；停止拖动 2s 后自动归位 */
const MANUAL_HOLD_MS = 2000
const manual = ref(false)
let manualTimer: ReturnType<typeof setTimeout> | undefined
/**
 * 程序化滚动目标（px）+ 上一次 scroll 位置。
 *
 * 判「自身滚动」不用时间窗：平滑滚动只会**逐步逼近**目标，距离变大即说明用户接管了滚动。
 * 时间窗在慢设备上会误判（2026-09-22 真机实测：平滑滚动的 scroll 事件晚于窗口到达 →
 * 被当成用户拖动 → 焦点句跳到「视口中心句」并与自动滚动互相打架，
 * 时钟单调推进 00:00→00:10 期间焦点却在 0/1/2 句之间来回跳）。
 */
let scrollTarget: number | null = null
let lastScrollTop = 0

/** 焦点句：拖动中 = 视口中心句；否则 = 时间轴当前句（-1 = 无游标：未播放/未开口） */
const focus = computed(() => (manual.value && centerIdx.value >= 0 ? centerIdx.value : current.value))
/** 无游标态（面板刚打开 / 参考旋律停止 / 尚未开口）：不做「焦点句」处理 */
const idle = computed(() => focus.value < 0)
/**
 * 透明度级别：焦点句 0（最亮），越远越淡。
 * 2026-09-22 排版优化：**无游标态一律取 1 级**（可读的中灰）。
 * 旧口径在无游标时把每一行都算成 3 级（0.20）→ 真机截图里整张歌词卡看着像空白卡；
 * 用户打开面板的第一眼应该是「我能把这首歌唱出来」，而不是一片灰雾。
 */
const dimLevels = computed(() =>
  lines.value.map((_, i) => (idle.value ? 1 : dimLevel(lineDistance(focus.value, i)))),
)

function centerCurrent(behavior?: ScrollBehavior) {
  const box = scroller.value
  if (!box) return
  const idx = current.value
  // 归零（无时间轴）用瞬时滚动：一帧内就位；跟随当前句用平滑滚动（动效档 off 时也瞬时）
  const mode: ScrollBehavior =
    idx < 0 ? 'auto' : (behavior ?? (tier.value === 'off' ? 'auto' : 'smooth'))
  const rows = box.querySelectorAll('.m-sing-lyric')
  const first = rows[0] as HTMLElement | undefined
  // 用 rect 差值而非 offsetTop：`.m-sing-lyric` 自身是 `position: relative`（为承载已唱叠加层），
  // 其 offsetParent 会跳到 `position: fixed` 的面板，offsetTop 不再是「相对滚动容器」的距离
  // （2026-09-21 CDP 实测踩坑：scrollTop 被钳到最大滚动量、当前句不居中）。
  const boxRect = box.getBoundingClientRect()
  let top = 0
  if (idx >= 0) {
    const el = rows[idx] as HTMLElement | undefined
    if (!el) return
    const elRect = el.getBoundingClientRect()
    top = box.scrollTop + (elRect.top - boxRect.top) - (box.clientHeight - elRect.height) / 2
  } else if (first) {
    // **无游标态：首句顶到视口上沿**（2026-09-22 排版优化）。
    // 旧实现归零到 `scrollTop = 0`，等价于「首句居中」——留白 (H−L)/2 全露在上方，
    // 未播放/未开口时卡片上半张是空的。顶对齐后整首歌直接铺满卡片；一旦有游标（播放/开口）
    // 就回到「当前句恒居中」的既定口径，转换只有一次平滑滚动。
    top = box.scrollTop + (first.getBoundingClientRect().top - boxRect.top)
  }
  // 目标先夹到可滚范围：否则实际到不了目标，`onScroll` 会一直以为「自身滚动还在途」
  scrollTarget = Math.max(0, Math.min(top, box.scrollHeight - box.clientHeight))
  lastScrollTop = box.scrollTop
  box.scrollTo({ top: scrollTarget, behavior: mode })
}

/** 只读 2 个 rect（首行 + 容器）后纯算术求中心句下标——避免逐行 rect 触发强制同步布局 */
function updateCenterIndex() {
  const box = scroller.value
  const first = box?.querySelector('.m-sing-lyric') as HTMLElement | null
  if (!box || !first) return
  const boxRect = box.getBoundingClientRect()
  const firstRect = first.getBoundingClientRect()
  const padTop = firstRect.top - boxRect.top + box.scrollTop
  centerIdx.value = nearestLineIndex(
    box.scrollTop,
    box.clientHeight,
    padTop,
    firstRect.height,
    lines.value.length,
  )
}

function onScroll() {
  const box = scroller.value
  if (!box) return
  const st = box.scrollTop
  // 程序化滚动：距离在缩小 → 是它自己在走，不算用户拖动
  if (
    scrollTarget !== null &&
    Math.abs(st - scrollTarget) < Math.abs(lastScrollTop - scrollTarget)
  ) {
    lastScrollTop = st
    if (Math.abs(st - scrollTarget) <= 1) scrollTarget = null // 到位
    return
  }
  // 距离没缩小（或本就没有在途滚动）→ 用户拖动，交还控制权
  scrollTarget = null
  lastScrollTop = st
  manual.value = true
  updateCenterIndex()
  clearTimeout(manualTimer)
  manualTimer = setTimeout(() => {
    manual.value = false
    centerCurrent()
  }, MANUAL_HOLD_MS)
}

watch(current, (idx) => {
  if (idx < 0 || !manual.value) centerCurrent()
})

/**
 * 视口高度变化后把当前句重新居中（2026-09-22 排版优化）：
 * 行高已与容器解耦（不会重排），但**滚动位置**仍是按旧 H 算出来的——
 * 展开/收起实时曲线区、或用户切「实时曲线」开关时 H 会变，不重算焦点句就会偏离中心（最长要等一整句 ~5s）。
 * 读操作只用现成的 2 个 rect（见 centerCurrent）；happy-dom 单测环境无 `ResizeObserver` → 守卫跳过。
 */
let ro: ResizeObserver | undefined
onMounted(() => {
  centerCurrent() // 初次进入：无游标 → 首句顶对齐，把整首歌铺进卡片
  if (typeof ResizeObserver === 'undefined' || !scroller.value) return
  ro = new ResizeObserver(() => {
    if (!manual.value && current.value >= 0) centerCurrent()
  })
  ro.observe(scroller.value)
})

onUnmounted(() => {
  clearTimeout(manualTimer)
  ro?.disconnect()
})
</script>

<template>
  <div class="m-sing-lyrics" :style="{ '--rows-cap': rowsCap }">
    <div class="m-sing-lyrics__head">
      <!-- 播放位置数字：**无游标时不渲染**（2026-09-22 排版优化）。
           旧实现恒显示 `--:--` 占位，真机截图里左上角一串灰破折号像渲染坏了；
           行高固定（min-height）所以隐藏它不会让歌词区跳动。 -->
      <span
        v-if="timeMs != null"
        class="m-sing-lyrics__time"
        aria-label="当前播放位置"
      >{{ clockText }}</span>
    </div>
    <div ref="scroller" class="m-sing-lyrics__scroller" @scroll.passive="onScroll">
      <!-- 上下留白：(视口高 − 行高)/2 → 首句与末句也能滚到正中 -->
      <div class="m-sing-lyrics__pad" aria-hidden="true" />
      <p
        v-for="(line, i) in lines"
        :key="line.seq"
        class="m-sing-lyric"
        :class="{ 'is-focus': i === focus, [`is-dim-${dimLevels[i] ?? 3}`]: true }"
      >
        <span class="m-sing-lyric__text">{{ line.text }}</span>
        <!-- 已唱部分：同文案叠一层，用 clip-path 裁出已唱宽度（颜色推进 = 进度指示） -->
        <span
          v-if="i === current"
          class="m-sing-lyric__sung"
          :style="{ clipPath: fillClip }"
          aria-hidden="true"
        >{{ line.text }}</span>
      </p>
      <div class="m-sing-lyrics__pad" aria-hidden="true" />
    </div>
  </div>
</template>
