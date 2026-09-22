<script setup lang="ts">
/**
 * 移动端 · 唱吧（跟唱）—— M3 唱歌 P0 接真（2026-09-09）
 * 全链路：选歌（歌曲列表 + 40905 就绪门禁）→ 整首跟唱（≤180s）→ 上传 →
 * 异步评分轮询（queued→processing→done|failed）→ 逐句评分 + D3 对齐图 + 报告。
 * 数据源：GET /api/v1/songs(/id)、POST /sessions(kind=sing)、POST /sessions/{id}/audio、
 * GET /sing/attempts/{id}(/status)（api/sing.ts；错误码映射见 singErrorMessage）。
 * 视觉：沿用重制版基线（深青精选卡/56px 分段/点线时间轴歌单）；交互逻辑接真。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'

import { shareDemoLink } from '@/composables/share'
import { SING_MAX_RECORD_MS, useSingPlay } from '@/composables/sing'
import { useDelayedLoading } from '@/composables/useDelayedLoading'
import { useReferenceAudio } from '@/composables/useReferenceAudio'
import { useSingAccompaniment } from '@/composables/useSingAccompaniment'
import { useLivePitchPref } from '@/composables/useLivePitchPref'
import { useSingLyricClock } from '@/composables/useSingLyricClock'
import { useUiStore } from '@/stores/ui'
import { useSingStore } from '@/stores/sing'
import { hapticTap } from '@/utils/haptic'

import { toLyricLines } from '@/lib/sing-lyrics'
import type { SongSummary } from '@/api/sing'

import SingActionBar from '@/components/sing/SingActionBar.vue'
import SingLibrarySection from '@/components/sing/SingLibrarySection.vue'
import SingTabBar from '@/components/sing/SingTabBar.vue'
import SingTopBar from '@/components/sing/SingTopBar.vue'
import type { SingCat } from '@/components/sing/SingTopBar.vue'
import SingMiniPlayer from '@/components/sing/SingMiniPlayer.vue'
import SingLyrics from '@/components/sing/SingLyrics.vue'
import SingSheetHead from '@/components/sing/SingSheetHead.vue'
import SingSongPickerSheet from '@/components/sing/SingSongPickerSheet.vue'
import LivePitchChart from '@/components/LivePitchChart.vue'
import SingReport from '@/components/sing/SingReport.vue'
import { formatClock } from '@/lib/sing-lyrics'
import '@/styles/mobile-uic.css'
import '@/styles/mobile-sing.css'

const ui = useUiStore()
/** 选曲真源（与桌面顶栏同一份；跨模块读 `currentSong` 即可同步，2026-09-21） */
const sing = useSingStore()

const play = useSingPlay()

/** 跟唱面板（同页全屏 sheet）：null=关闭 */
const sheetOpen = ref(false)

/** 跟唱曲目选择弹层（顶栏入口 · 2026-09-21）：底部 sheet，列表/选中态来自 store */
const pickerOpen = ref(false)


type Tab = 'songs' | 'fav'

const tab = ref<Tab>('songs')

/**
 * 分类（2026-09-23 用户原型：QQ 式横滑 tab）。
 *
 * 原型 6 项「推荐/刷歌/乐馆/听书/伴奏库/热歌榜」中，我们只有两档真实内容：
 * 推荐 = 全部曲目、收藏 = 用户自主收藏（2026-09-10 组长需求，带测试）——
 * 原型第二项「刷歌」无对应能力，就地换成「收藏」；其余 4 项按原型保留视觉，
 * 点击 toast「后续版本」（不假装有内容、不空跳）。
 */
const tabs: SingCat[] = [
  { key: 'songs', label: '推荐', real: true },
  { key: 'fav', label: '收藏', real: true },
  { key: 'hall', label: '乐馆', real: false },
  { key: 'listen', label: '听书', real: false },
  { key: 'accomp', label: '伴奏库', real: false },
  { key: 'hot', label: '热歌榜', real: false },
]

function onCat(t: SingCat) {
  if (t.real) {
    tab.value = t.key as Tab
    return
  }
  ui.showToast(`${t.label} · 后续版本`)
}

/* 分类规则：songs=全部曲目；fav=**用户自主收藏**（服务端 favorited 为准，2026-09-10） */
const visibleSongs = computed(() =>
  tab.value === 'fav' ? play.favorites.value : play.songs.value,
)

const featured = computed(() => play.songs.value[0] ?? null)
/** 收藏第一首（英雄卡 2「My List」数据源；无收藏 → 卡 2 不渲染） */
const firstFavorite = computed(() => play.favorites.value[0] ?? null)
const sheetDetail = computed(() => play.detail.value)
const recording = computed(() => play.phase.value === 'recording')
/** 录音暂停中（2026-09-22 深色录唱页：中心钮变「继续」，计时/歌词游标冻结） */
const paused = play.paused
const processing = computed(
  () => play.phase.value === 'processing' || play.phase.value === 'uploading',
)

/** 有效句计数（覆盖率提示文案由后端 `alignment.coverage_note` 下发，v4 口径） */
const evaluatedCount = computed(
  () => play.result.value?.lines.filter((x) => !x.skipped).length ?? 0,
)
const expectedCount = computed(() => play.result.value?.expected_lines ?? 0)

/** 实时分（顶栏评级条数据源；由 LivePitchChart 的 `score` 事件上报，≤4Hz） */
const liveScore = ref<number | null>(null)
/** 顶栏模式 chip 文案 */
const headModeText = computed(() =>
  paused.value ? '暂停中' : recording.value ? '跟唱中' : refPlaying.value ? '原唱中' : '待开始',
)
/** 底部一行「歌曲位置 / 全长」：全长取歌曲时长（契约 `duration_s`），缺失时退回录音上限。
 *  时间与歌词区左上角数字、引导条走针**同一条歌曲轴**（2026-09-22 用户口径）：
 *  听原唱 = 播放位置（旧实现恒 00:00）；跟唱 = 首句锚点位置（开口前即首句起点，不是录音已用时长）。 */
const totalMs = computed(
  () => (sheetDetail.value?.duration_s ? sheetDetail.value.duration_s * 1000 : SING_MAX_RECORD_MS),
)
const totalClock = computed(() => formatClock(totalMs.value))

/** 参考旋律回放（2026-09-09 真机反馈：先听一遍再跟唱，避免凭记忆清唱音准普遍偏低）。
 *  播放/回收/重入守卫抽到 `useReferenceAudio`（P1-7；视图受 max-lines 门禁约束）。 */
const refAudioPath = computed(() => {
  const url = sheetDetail.value?.audio_url
  return url ? `/api/v1/audio/${url.split('/').pop()}` : null
})
const reference = useReferenceAudio(
  () => refAudioPath.value,
  (msg) => ui.showToast(msg),
)
const refPlaying = reference.playing

/** 伴奏（录音期间播放 · 2026-09-22 用户口径「伴奏是唱的时候放的」；细节见组合式文件头） */
const accompaniment = useSingAccompaniment(
  () => ({ instrumental: sheetDetail.value?.instrumental_url, audio: sheetDetail.value?.audio_url }),
  (msg) => ui.showToast(msg),
)

/**
 * 悬浮播放条 · 参考旋律试听（2026-09-23 用户原型 QQ 音乐式播放条「接真」）。
 * 与跟唱面板的「听原唱」是**两路独立实例**：试听只活在列表页，开跟唱面板即停（见 openSong），不叠放。
 * 路径口径与面板一致：`audio_url` 取 basename 拼 `/api/v1/audio/`（后端公开音频路由）。
 */
const previewSong = ref<SongSummary | null>(null)
const previewPath = computed(() => {
  const url = previewSong.value?.audio_url
  return url ? `/api/v1/audio/${url.split('/').pop()}` : null
})
const preview = useReferenceAudio(() => previewPath.value, (msg) => ui.showToast(msg))
const previewPlaying = preview.playing

/** 播放条展示的曲目：本次试听 > store 当前选中 > 列表第一首（列表页常驻可见） */
const miniSong = computed(() => previewSong.value ?? sing.currentSong ?? featured.value)

/** 试听/暂停同一首；换歌则从头播（`play()` 内部先停旧实例，P1-7 资源回收） */
function playOrTogglePreview(song: SongSummary) {
  if (previewSong.value?.id === song.id) {
    if (previewPlaying.value) preview.pause()
    else preview.resume()
    return
  }
  previewSong.value = song
  void preview.play()
}

/** 行点击：试听该曲（原型口径「点行=播放，药丸键=去跟唱」） */
function onPreview(song: SongSummary) {
  hapticTap('light')
  playOrTogglePreview(song)
}

/** 播放条播放/暂停键：还没选过曲时，对当前展示的曲目开播 */
function togglePreview() {
  const s = previewSong.value ?? miniSong.value
  if (s) playOrTogglePreview(s)
}
/** 任一路在播（歌词时钟的「跟随音频」判据：听原唱或跟唱放伴奏都算） */
const anyPlaying = computed(() => refPlaying.value || accompaniment.playing.value)
/** 当前音频位置（ms）：伴奏在播时取伴奏位置，否则取参考音位置 */
const audioPosMs = () =>
  accompaniment.playing.value ? accompaniment.currentMs() : reference.currentMs()

/** 实时音准线显示开关（2026-09-22：按视频模板移到面板底部按钮行；只管显示，检测照常跑） */
const { on: livePitchOn, toggle: toggleLivePitch } = useLivePitchPref()

/**
 * 跟唱歌词锚点（2026-09-21 用户口径）：**开口那一刻回到第一句**。
 * 由 `LivePitchChart` 的 `firstVoice` 事件给出「本次录音首帧人声」的相对时刻；
 * 尚未开口 → null（歌词不预跑，停在顶部等开口）。
 */
const voiceAtMs = ref<number | null>(null)
/** 首句起点（锚点目标；随换歌更新） */
const lyricFirstMs = computed(() => toLyricLines(sheetDetail.value?.lines)[0]?.startMs ?? 0)

/** 歌词游标：参考播放取音频位置；跟唱取「首句 + 已开口时长」（同一条 LRC 时间轴）。
 *  另取 `elapsedMs`（录音轴已用时长，整秒量化）供面板头部计时/进度线；
 *  `positionMs`（歌曲轴，跟唱开口前回退首句起点）供底部时间与引导条——三者分工见各注释。
 *  `paused` 传入后，暂停段不计入游标与时长（2026-09-22 新增暂停能力）。 */
const {
  timeMs: lyricTimeMs,
  elapsedMs: recElapsedMs,
  positionMs,
  recMs,
} = useSingLyricClock({
  playing: anyPlaying,
  recording,
  paused,
  audioMs: audioPosMs,
  voiceAtMs,
  firstLineMs: () => lyricFirstMs.value,
})

/** 本轮是否用伴奏起唱（决定轨迹的轴映射口径；由 `startSinging` 置位） */
const takeWithAccompaniment = ref(false)

/**
 * 引导条用户轨迹的轴映射（2026-09-22；同日深夜按伴奏口径修正）：检测帧时间戳是**录音轴**
 * （检测起点起算），引导条走针/目标音符块用**歌曲轴**：
 * - **伴奏轮**：伴奏与录音同起点（`startSinging` 先等伴奏就位再开录）→ 两轴重合，偏移 = **0**。
 *   此前一律按「首句锚点」算偏移——用户只要不是恰好在首句开口，整条轨迹就横移数秒，
 *   看起来「怎么唱都不在块内」；
 * - **清唱轮**：开口即首句锚点 → 偏移 = 首句起点 − 首帧人声时刻（有前奏的歌不错位）。
 */
const laneOffsetMs = computed(() =>
  takeWithAccompaniment.value ? 0 : lyricFirstMs.value - (voiceAtMs.value ?? 0),
)

/** 底部时间 = 歌曲轴位置（听原唱 = 播放位置；跟唱 = 首句锚点位置；空闲 = 00:00） */
const songClock = computed(() => formatClock(positionMs.value ?? 0))

/**
 * 开始跟唱（P1-5，2026-09-10；2026-09-22 补伴奏）：
 * - **先停原唱**（原口径：外放先听后唱时原唱会被麦克风录进评分）；
 * - 若「伴奏」开着 → **从头播伴奏**（`songs.instrumental_url`，无则回退参考音）：
 *   用户口径「没有伴奏怎么唱」——录音期间要有伴奏；伴奏同样经麦克风（建议戴耳机，
 *   否则会与用户声音一起被录进去，评分受影响）。
 * - 依据：docs/31（跟唱为练习辅助，输入须为用户本人）、拷问报告 A-F3/D-F3。
 */
async function startSinging() {
  voiceAtMs.value = null // 新一轮跟唱：锚点等首帧人声
  liveScore.value = null // 上一轮的实时分不带进新的一轮
  reference.stop()
  // 伴奏先就位（加载+开播）再开录 → 歌曲轴与录音轴同一起点（轨迹偏移才为 0）
  takeWithAccompaniment.value = await accompaniment.start()
  play.startRecording()
}

/** 听原唱 ⇄ 停止（听原唱时停掉伴奏，两路不叠放） */
function toggleReference() {
  accompaniment.stop()
  void reference.toggle()
}

/**
 * 首帧人声锚点（2026-09-22 加固）：**同一轮只认第一个**，且必须早于当前已开口时长。
 *
 * 修复前直接把事件值写进 `voiceAtMs`：检测重启（暂停/切歌等）会再次触发 `firstVoice`，
 * 而 Worker 的帧时间戳是**跨会话累加**的（不复位）→ 第二次锚点是个很大的值 →
 * 游标算成 `首句 + (已开口 − 大锚点)` = 负数 → clamp 到 0 → **歌词进度与高亮整个归零**
 * （用户实测「暂停后进度有时候会归零」）。现在第二个及以后的锚点一律忽略。
 */
function onFirstVoice(tMs: number) {
  if (voiceAtMs.value != null) return // 本轮已有锚点：不覆盖
  const elapsed = recMs.value
  if (elapsed != null && tMs > elapsed + 1000) return // 明显来自上一轮/跨会话的时间戳：丢弃
  voiceAtMs.value = tMs
}

async function openSong(songId: number) {
  reference.stop() // 换歌即停播（原实现会继续播上一首的参考旋律）
  accompaniment.stop() // 伴奏同理
  preview.stop() // 悬浮播放条的试听也停（进跟唱面板后由面板自己的「听原唱」接管）
  const ok = await play.openSong(songId)
  if (ok) sheetOpen.value = true
  else ui.showToast(play.error.value ?? '该歌暂时不能跟唱')
}

/** 收藏按钮：点一下收藏，再点一次取消（乐观更新 + 失败回滚，见 useSingPlay.toggleFavorite） */
async function toggleFav(song: SongSummary) {
  hapticTap('light') // 语义动作触觉（安卓支持；其余平台静默）
  const r = await play.toggleFavorite(song.id)
  if (r === null) ui.showToast(play.favoriteError.value ?? '收藏操作失败，请重试')
  else ui.showToast(r ? '已收藏，可在「收藏」里找到' : '已取消收藏')
}

async function startOver() {
  reference.stop()
  accompaniment.stop()
  play.reset()
  sheetOpen.value = false
}

/**
 * 面板背景滚动锁（2026-09-10 P0-4 配套）：
 * sheet 改为**视口锚定**后，若背景仍可滚，移动端会出现"面板下方露出歌单/背景橡皮筋"；
 * 打开锁 `body` 溢出、关闭与卸载都要还原（防"锁死整页"）。
 * 依据：docs/35（App 端 UI 迭代 SOP：浮层与视口关系）+ 拷问报告 A-F1/D-F1 处置建议。
 */
watch(sheetOpen, (open) => {
  document.body.style.overflow = open ? 'hidden' : ''
})

onUnmounted(() => {
  reference.stop()
  accompaniment.stop()
  document.body.style.overflow = '' // 卸载兜底：面板开着直接离开页面时不得把整页锁死
})

onMounted(play.loadSongs)

/** 列表加载失败（P1-6）：`phase='failed'` 且列表为空 → 页面级错误态（原实现只在 sheet 内显示错误） */
const loadFailed = computed(() => play.phase.value === 'failed' && play.songs.value.length === 0)

/** 加载态骨架防抖（docs/31 硬规则 3：>300ms 才出现；与其余移动端页同款写法） */
const { visible: skelVisible, pending: skelPending } = useDelayedLoading(
  computed(() => play.phase.value === 'loading'),
)

/** 结果就绪 → 渲染 D3 对齐图：**已随报告一起下沉到 `SingReport.vue`**（视图不再自己找元素画图，
 *  P1-8 的模板 ref 口径在那边继续成立）；这里只保留「结果在面板关闭时落地也不白画」的外层条件。 */

/** 顶栏 · 分享歌曲（演示：系统面板 / 复制链接）——架构级功能，保留演示入口 */
async function shareSong() {
  const s = featured.value
  const result = await shareDemoLink({
    title: s?.title ?? 'VocalVerse 跟唱',
    text: s ? `VocalVerse 跟唱 · ${s.title}（${s.expected_lines} 句）` : 'VocalVerse 跟唱',
    url: 'https://vocalverse.demo/sing',
  })
  if (result === 'shared') ui.showToast('已分享')
  else if (result === 'copied') ui.showToast('歌曲链接已复制（演示链接）')
  else if (result === 'failed') ui.showToast('复制失败，请手动复制')
}
</script>

<template>
  <div class="u-phone m-sing-page">
    <!-- 顶部区（搜索胶囊 + 图标工具 + 横滑分类）——2026-09-23 用户原型 1:1，见 components/sing/SingTopBar.vue -->
    <SingTopBar
      :song-title="miniSong?.title ?? null"
      :cats="tabs"
      :active-key="tab"
      :picked="!!sing.currentSong"
      @pick="pickerOpen = true"
      @share="shareSong"
      @cat="onCat"
    />

    <div class="u-content m-sing-content">
      <!-- 曲库区（英雄卡/骨架/错误态/歌单/空态）——2026-09-23 抽出守 max-lines，见 components/sing/SingLibrarySection.vue -->
      <SingLibrarySection
        :featured="featured"
        :favorite="firstFavorite"
        :songs="visibleSongs"
        :tab="tab"
        :active-id="previewSong?.id ?? null"
        :skel-pending="skelPending"
        :skel-visible="skelVisible"
        :load-failed="loadFailed"
        :error-text="play.error.value"
        @open="openSong"
        @preview="onPreview"
        @favorite="toggleFav"
        @retry="play.loadSongs()"
      />
      <!-- 2026-09-22 用户要求删掉页脚评分公式（「跟唱评分 = 0.5·音准 + 0.2·节奏 + 0.3·发音…」）：
           属研发口径（口径真源在 docs/06 §9.4 与报告页），不该占歌单屏的版面 -->
    </div>

    <!-- 跟唱面板（全屏 sheet） -->
    <div v-if="sheetOpen" class="m-sing-sheet">
      <!-- 顶栏（抽出为组件）：关闭 + 实时评级条 + 模式 chip + 3 分钟录音进度线 -->
      <SingSheetHead
        :title="sheetDetail?.title ?? '跟唱'"
        :score="liveScore"
        :mode-text="headModeText"
        :recording="recording"
        :paused="paused"
        :elapsed-ms="recElapsedMs"
        :max-ms="SING_MAX_RECORD_MS"
        @close="startOver"
      />

      <div class="m-sing-sheet__body">
        <!-- 录音/评分阶段（2026-09-22 深色录唱页：大歌名 → 音准引导条 → 歌词 → 底部五键 → 已录/全长） -->
        <template v-if="!play.result.value">
          <div v-if="play.error.value" class="m-sing-sheet__hint" style="color: #ff8fa3">
            {{ play.error.value }}
          </div>
          <h1 class="m-sing-song">{{ sheetDetail?.title ?? '跟唱' }}</h1>
          <!-- 音准引导条（目标音符块 + 走针 + 用户轨迹）。开关「曲线」只管是否画用户轨迹，
               检测照常跑——歌词滚动的首帧人声锚点依赖 `firstVoice`；实时分经 `score` 上报顶栏。 -->
          <LivePitchChart
            v-if="sheetDetail"
            class="m-sing-lane"
            :detail="sheetDetail"
            :stream="play.getLiveStream()"
            :active="recording"
            :playing="refPlaying"
            :enabled="livePitchOn"
            :paused="paused"
            :clock-ms="positionMs"
            :offset-ms="laneOffsetMs"
            @first-voice="onFirstVoice"
            @score="liveScore = $event"
          />
          <!-- 歌词（几何与时间轴口径不变，仅换深色配色；见 lib/sing-lyrics.ts） -->
          <SingLyrics :lines="sheetDetail?.lines" :time-ms="lyricTimeMs" />
          <div v-if="processing" class="m-sing-sheet__progress">
            <div class="m-sing-sheet__bar">
              <div class="m-sing-sheet__bar-inner" :style="{ width: `${play.progressPct.value}%` }" />
            </div>
            <span>{{ play.progressPct.value }}% · {{ play.progressPct.value < 100 ? '评分计算中…' : '正在生成报告…' }}</span>
          </div>
          <!-- 底部六键：原唱 / 曲线 / 选曲 / 开始·暂停·继续 / 重录 / 完成（参考图布局；调音键不做——无该能力）。
               「选曲」只负责开列表（本页的 SingSongPickerSheet），切歌仍走 openSong()。 -->
          <SingActionBar
            :recording="recording"
            :paused="paused"
            :processing="processing"
            :ref-playing="refPlaying"
            :live-on="livePitchOn"
            :accompaniment-on="accompaniment.on.value"
            @toggle-reference="toggleReference"
            @start="startSinging"
            @pause="play.pauseRecording(); accompaniment.pause()"
            @resume="play.resumeRecording(); accompaniment.resume()"
            @stop="accompaniment.stop(); play.stopRecording()"
            @cancel="accompaniment.stop(); play.cancelRecording()"
            @toggle-live="toggleLivePitch()"
            @toggle-accompaniment="accompaniment.toggle()"
            @pick="pickerOpen = true"
          />
          <!-- 歌曲位置 / 全长（参考图「若梦 · 00:42 / 04:04」的位置）；与歌词区时间、引导条同轴；
               暂停中显式标出，避免「卡住了」的误会 -->
          <div class="m-sing-foot">
            <span class="m-sing-foot__name">{{ sheetDetail?.title ?? '跟唱' }}</span>
            <span class="m-sing-foot__times">{{ songClock }} / {{ totalClock }}</span>
            <span v-if="paused" class="m-sing-foot__flag">已暂停</span>
          </div>
        </template>

        <!-- 报告阶段（已抽成组件：视图守 max-lines 门禁；图表渲染随之下沉） -->
        <template v-else>
          <SingReport
            :detail="sheetDetail"
            :result="play.result.value"
            :evaluated-count="evaluatedCount"
            :expected-count="expectedCount"
            @back="startOver"
          />
        </template>
      </div>
    </div>

    <!-- 跟唱曲目选择（顶栏入口的弹层；选曲直接复用页面既有 openSong：
         内部已停参考旋律 + 停录音 + 作废旧轮询 + 40905 门禁 → 即「先停止再切换」） -->
    <SingSongPickerSheet v-model:open="pickerOpen" @select="openSong" />

    <!-- 悬浮试听播放条（2026-09-23 用户原型；转盘=封面、播放/暂停=参考旋律试听、红心=收藏、队列=选曲） -->
    <SingMiniPlayer
      v-if="miniSong"
      :song="miniSong"
      :playing="previewPlaying"
      @toggle="togglePreview"
      @open="openSong"
      @queue="pickerOpen = true"
      @favorite="toggleFav"
    />

    <!-- 页内底部 Tab 栏（2026-09-23 用户原型 1:1：唱吧独用一套；全局底栏在本页不再渲染） -->
    <SingTabBar />
  </div>
</template>
