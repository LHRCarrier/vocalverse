<script setup lang="ts">
/**
 * 唱吧歌单 · 滚动动画列表（React Bits `AnimatedList` 的 Vue 移植 · 2026-09-22）
 *
 * 为什么需要它：歌单原来是一条**跟随页面长高**的点线时间轴（`.u-dotline` 连接的一长串卡片）。
 * 曲库只有 3 首时没问题；歌曲一多，整页被拉到几千像素 —— 精选卡、筛选、页脚注释全部被推走，
 * 想找一首歌只能一路下滑。本组件把歌单收进一个**定高滚动区**：页面高度从此与曲库规模无关，
 * 列表内部自己滚，曲库涨到几十首也不影响页面版式。
 *
 * 与上游 `AnimatedList` 的对应关系（能一一对上的都保留，扩项见括号）：
 * - 滚动容器 + `showGradients` 上下渐隐提示「还有内容」（渐隐色改用本项目纸面色，不是上游的 #120F17）；
 * - `displayScrollbar` 自定义滚动条（配色改用 `--u-track` / `--u-weak`，深色轨道在纸面页上会像一道黑缝）；
 * - `enableArrowNavigation` ↑/↓/Tab/Shift+Tab 移动选中、Enter 打开（**只在列表自身可见时生效**，见下）；
 * - `initialSelectedIndex` + 悬停/聚焦跟随选中，键盘滚动时把选中行带回视野（上游 `extraMargin` 口径）；
 * - `className` / `itemClassName` 透传。
 *
 * 三处**有意偏离**上游，都是移动端真形态的硬要求：
 * 1. **不做入场隐藏**。上游 `AnimatedItem` 用 `initial={{scale:.7, opacity:0}}` 起手、等
 *    `useInView` 触发才显形。移动端 `IntersectionObserver` 一旦不触发（无排版引擎的宿主、
 *    老 WebView）列表就是**一片空白**；且上游 `triggerOnce:false` 会让滚出视口的行**重新缩回去**
 *    再滚回来又放大，在滚动列表里相当晃眼。这里改成「默认可见，进场只做一次放大淡入」——
 *    渲染结果永远可见，动画是叠加的锦上添花，失败也不吞内容。
 * 2. **键盘导航按可见性收窄**。上游无条件挂在 `window` 上并 `preventDefault()`，会吃掉整页的
 *    ↑↓/Tab（本页底部跟唱面板还有自己的方向键用途）。这里 ① 已 `preventDefault` 的事件一律放过
 *    （面板侧的处理优先）② 用 `IntersectionObserver` 盯住列表可见性，**列表不在屏上就不接管键盘**，
 *    键盘用户仍可按 Tab 走完页面。
 * 3. **动效遵守项目三级降级**（docs/31 §2）。上游只认 `prefers-reduced-motion`；这里读
 *    `useMotionTier()`：`off` 档（系统减少动效 / 手动覆盖）直接不启动动画，`low` 档缩短时长
 *    （与样式侧 90ms 口径对齐），`high` 保持 200ms。
 *
 * 行内交互（点行去跟唱 / 点心形收藏）仍归 `MobileSongRow`：本组件只做动画壳与选中态，
 * 不自己 emit 切换动作，`open` 事件原样带上下标（顺带满足上游 `onItemSelect(item, index)` 语义）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { animate, inView } from 'motion'

import MobileSongRow from './MobileSongRow.vue'
import type { SongSummary } from '@/api/sing'
import { useMotionTier } from '@/composables/useMotionTier'

const props = withDefaults(
  defineProps<{
    /** 待展示曲目（顺序即渲染顺序；数据源与过滤都在页面/store，本组件不碰） */
    songs: SongSummary[]
    /** 在播曲目 id（悬浮播放条当前曲目）→ 行叠加音波；null = 无 */
    activeId?: number | null
    showGradients?: boolean
    enableArrowNavigation?: boolean
    className?: string
    itemClassName?: string
    displayScrollbar?: boolean
    /** 初始选中下标（上游同名 props）；-1 = 无选中 */
    initialSelectedIndex?: number
  }>(),
  {
    activeId: null,
    showGradients: true,
    enableArrowNavigation: true,
    className: '',
    itemClassName: '',
    displayScrollbar: true,
    initialSelectedIndex: -1,
  },
)

const emit = defineEmits<{
  /** 试听（行点击 / 键盘 Enter；带下标，等价上游 `onItemSelect(item, index)`） */
  preview: [id: number, index: number]
  /** 去跟唱（行内药丸键；带下标） */
  open: [id: number, index: number]
  favorite: [song: SongSummary]
}>()

const { tier } = useMotionTier()

/** 选中下标（悬停 / 聚焦 / 键盘共用；-1 = 无选中） */
const selectedIndex = ref(props.initialSelectedIndex)
/** 本次选中变更来自键盘 → 需要把该行滚回视野（上游 `keyboardNav` 同义） */
const keyboardNav = ref(false)

const listEl = ref<HTMLElement | null>(null)
const topGradientOpacity = ref(0)
const bottomGradientOpacity = ref(1)
/** 列表是否在屏上（键盘导航的接管条件；见文件头「偏离 2」） */
const listVisible = ref(false)
/** 当前是否真有可滚内容 → 决定要不要抑制滚动链（理由见 `measureGradients`） */
const scrollable = ref(false)

/** 进场动画参数（上游 duration .2 / delay .1；low 档缩短，与样式侧 90ms 口径对齐） */
const ENTER_DURATION_MS = computed(() => (tier.value === 'low' ? 0.09 : 0.2))
const ENTER_DELAY_S = 0.1

/**
 * 该行是否要**叠加**入场动画（把 opacity/scale 从初值推到终值）。
 * off 档：完全不叠加 —— 没有动画就只剩一层「CSS 初值 → 终值」的跳变，纯属闪烁，故直接跳过。
 * 动画能力探测：`animate` 底层走 WAAPI，宿主不提供时直接跳过（上游无此判断，靠 React 渲染兜底）。
 */
function shouldAnimate(): boolean {
  if (tier.value === 'off') return false
  const el = listEl.value
  return !!el && typeof el.animate === 'function'
}

function onItemEnter(index: number) {
  selectedIndex.value = index
}

/** 行激活（试听）：下标由行自身带不出去，这里补上（上游 onItemSelect 的 (item, index) 语义） */
function onRowPreview(id: number, index: number) {
  selectedIndex.value = index
  emit('preview', id, index)
}

/** 「去跟唱」药丸键：带上标后原样上抛（页面侧打开跟唱面板） */
function onRowOpen(id: number, index: number) {
  selectedIndex.value = index
  emit('open', id, index)
}

/**
 * 一次测量出「上下渐隐透明度」+「当前是否真有可滚内容」。
 *
 * 为什么不能只在滚动事件里算：上游把渐隐透明度**只放在 `onScroll`** 里，而"内容不满一屏"
 * 这类情况**永远不会产生滚动事件** → 底渐隐停在初值 `1`，把**最后一张卡整片糊掉**。
 * 这个缺陷在 happy-dom 里测不出来（无排版引擎，量不到真实高度），是**真机实测**抓到的：
 * 3 首时 `scrollHeight === clientHeight === 312`，底渐隐却仍是 1 → 截图里第三首
 * 「Ode to Joy」的副文与徽标被纸面色洗掉（见工作日志 2026-09-22 记录）。
 * 修法：把「测量」与「滚动」解耦，滚动事件只是触发测量的一种来源。
 */
function measureGradients() {
  const el = listEl.value
  if (!el) return
  const { scrollTop, scrollHeight, clientHeight } = el
  topGradientOpacity.value = Math.min(scrollTop / 50, 1)
  const bottomDistance = scrollHeight - (scrollTop + clientHeight)
  const hasOverflow = scrollHeight > clientHeight
  bottomGradientOpacity.value = hasOverflow ? Math.min(bottomDistance / 50, 1) : 0
  /**
   * 是否真有可滚内容 → 决定要不要 `overscroll-behavior: contain`。
   *
   * 用户口径是「滑列表时只滑列表、不滑整页」，`contain` 正是干这个的；但**无条件**加 contain
   * 是有风险的：宿主若把"元素不可滚"也当成"整条链到此为止"，手指落在列表上就既滑不动列表、
   * 也滑不动页面 → 那块区域变**死区**（用户会描述成"页面滑不动了"）。
   * Android WebView 实测会把不可滚元素的滚动链让给页面（本地 412×876 真机已验证 pageY 0→139），
   * 但 iOS Safari 历史上在这点上更严格 —— 与其依赖宿主行为，不如**只在真有内容可滚时才 contain**：
   * 有内容 → 手势归列表（需求原文成立）；没内容 → 声明都不写，滚动链天然交给页面（无死区）。
   */
  scrollable.value = hasOverflow
}

/** 滚动事件：只需重新测量（口径单一，避免四处散落同一套算式） */
function handleScroll() {
  measureGradients()
}

/** window 级按键入口（`enableArrowNavigation`）：列表不在屏上 / 功能关闭 → 完全不接管键盘 */
function onKeyDown(e: KeyboardEvent) {
  if (!props.enableArrowNavigation || !listVisible.value) return
  // 别处已处理（跟唱面板的方向键等）→ 不抢
  if (e.defaultPrevented) return
  const last = props.songs.length - 1
  const down = e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)
  const up = e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)
  if (down || up) {
    e.preventDefault()
    keyboardNav.value = true
    selectedIndex.value = down
      ? Math.min(selectedIndex.value + 1, last)
      : Math.max(selectedIndex.value - 1, 0)
    return
  }
  if (e.key !== 'Enter') return
  const s = props.songs[selectedIndex.value]
  if (!s) return
  e.preventDefault()
  emit('preview', s.id, selectedIndex.value)
}

let stopKeyboardWatch: (() => void) | null = null
/** 尺寸观察器（换标签 / 转屏 / 底部栏出现都会改可滚高度） */
let sizeObserver: ResizeObserver | null = null

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  // 挂载即测一次：内容不满一屏时**不会有滚动事件**，底渐隐必须在这里就归零
  measureGradients()
  if (typeof ResizeObserver === 'function') {
    sizeObserver = new ResizeObserver(() => measureGradients())
    if (listEl.value) sizeObserver.observe(listEl.value)
  }
  const el = listEl.value
  if (!el) return
  // 可见性守卫：宿主无 IntersectionObserver（老 WebView / 无排版引擎的宿主）时**视为常驻可见**，
  // 否则键盘导航会被这条守卫永久关掉 —— 降级方向必须是「可用」，不是「少一个功能」。
  if (typeof IntersectionObserver !== 'function') {
    listVisible.value = true
    return
  }
  stopKeyboardWatch = inView(el, (_el, entry) => {
    listVisible.value = entry.isIntersecting
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  sizeObserver?.disconnect()
  sizeObserver = null
  stopKeyboardWatch?.()
  stopKeyboardWatch = null
})

/** 曲目增删（换标签 / 收藏导致行数变化）后高度变了 → 重测渐隐 */
watch(
  () => props.songs.length,
  () => {
    void nextTick(measureGradients)
  },
)

/** 键盘移动选中后把该行带回视野（上游 `extraMargin = 50` 同口径） */
watch([selectedIndex, keyboardNav], () => {
  if (!keyboardNav.value || selectedIndex.value < 0) return
  const container = listEl.value
  const item = container?.querySelector<HTMLElement>(`[data-index="${selectedIndex.value}"]`)
  if (container && item && typeof container.scrollTo === 'function') {
    const extraMargin = 50
    const { scrollTop, clientHeight } = container
    const itemTop = item.offsetTop
    const itemBottom = itemTop + item.offsetHeight
    if (itemTop < scrollTop + extraMargin) {
      container.scrollTo({ top: itemTop - extraMargin, behavior: 'smooth' })
    } else if (itemBottom > scrollTop + clientHeight - extraMargin) {
      container.scrollTo({ top: itemBottom - clientHeight + extraMargin, behavior: 'smooth' })
    }
  }
  keyboardNav.value = false
})

/**
 * 已经跑过入场动画的元素。**必须有**：Vue 在每次 patch 后都会重新调用 `:ref` 回调
 * （仅当值变化才解绑，函数 ref 每次都是新函数 → 旧的回调先收到 `null`、新的再收到同一个元素），
 * 于是同一个元素会被 `bindItem` 命中多次。第二次 `animate()` 会**打断**第一个动画（上游无此问题：
 * React 的 `initial/animate` 是声明式的，不存在重复触发），而 WAAPI 的 `finished` promise 在
 * 被打断时以 `AbortError` 拒绝 —— 在无排版引擎的宿主（happy-dom）里会变成 unhandled rejection，
 * 让整轮测试报错。用 WeakSet 记住「这个元素已经入场过」，从根上不制造打断。
 */
const enteredElements = new WeakSet<Element>()

/** 行级入场动画（等价上游 `AnimatedItem`，但不做隐藏初值；见文件头「偏离 1」） */
function bindItem(el: Element | null, index: number) {
  if (!el || !shouldAnimate() || enteredElements.has(el)) return
  enteredElements.add(el)
  animate(
    el as HTMLElement,
    { opacity: [0, 1], scale: [0.7, 1] },
    { duration: ENTER_DURATION_MS.value, delay: index * ENTER_DELAY_S },
  )
}
</script>

<template>
  <div class="m-sing-list" :class="[className, { 'is-scrollable': scrollable }]">
    <div
      ref="listEl"
      class="m-sing-list__scroll"
      :class="{ 'is-nobar': !displayScrollbar }"
      @scroll="handleScroll"
    >
      <div
        v-for="(song, i) in songs"
        :key="song.id"
        :ref="(el) => bindItem(el as Element | null, i)"
        class="m-sing-list__item"
        :class="[itemClassName, { 'is-selected': selectedIndex === i }]"
        :data-index="i"
        @mouseenter="onItemEnter(i)"
        @focusin="onItemEnter(i)"
      >
        <MobileSongRow
          :song="song"
          :active="activeId === song.id"
          @preview="onRowPreview($event.id, i)"
          @open="onRowOpen($event, i)"
          @favorite="emit('favorite', $event)"
        />
      </div>
    </div>

    <template v-if="showGradients">
      <div class="m-sing-list__grad m-sing-list__grad--top" :style="{ opacity: topGradientOpacity }" />
      <div
        class="m-sing-list__grad m-sing-list__grad--bottom"
        :style="{ opacity: bottomGradientOpacity }"
      />
    </template>
  </div>
</template>
