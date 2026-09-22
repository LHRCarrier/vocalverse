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
import { useRouter } from 'vue-router'

import IconShare from '~icons/tabler/share'

import { shareDemoLink } from '@/composables/share'
import { SING_MAX_RECORD_MS, useSingPlay } from '@/composables/sing'
import { useDelayedLoading } from '@/composables/useDelayedLoading'
import { useReferenceAudio } from '@/composables/useReferenceAudio'
import { useLivePitchPref } from '@/composables/useLivePitchPref'
import { useSingLyricClock } from '@/composables/useSingLyricClock'
import { useUiStore } from '@/stores/ui'
import { useSingStore } from '@/stores/sing'
import { hapticTap } from '@/utils/haptic'

import { toLyricLines } from '@/lib/sing-lyrics'
import type { SongSummary } from '@/api/sing'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileSkeleton from '@/components/mobile/MobileSkeleton.vue'
import MobileSongList from '@/components/mobile/MobileSongList.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import SingActionBar from '@/components/sing/SingActionBar.vue'
import SingFeaturedCard from '@/components/sing/SingFeaturedCard.vue'
import SingLyrics from '@/components/sing/SingLyrics.vue'
import SingSheetHead from '@/components/sing/SingSheetHead.vue'
import SingSongPickerSheet from '@/components/sing/SingSongPickerSheet.vue'
import LivePitchChart from '@/components/LivePitchChart.vue'
import SingReport from '@/components/sing/SingReport.vue'
import { formatClock } from '@/lib/sing-lyrics'
import '@/styles/mobile-uic.css'
import '@/styles/mobile-sing.css'

const router = useRouter()
const ui = useUiStore()
/** 选曲真源（与桌面顶栏同一份；跨模块读 `currentSong` 即可同步，2026-09-21） */
const sing = useSingStore()

const play = useSingPlay()

/** 跟唱面板（同页全屏 sheet）：null=关闭 */
const sheetOpen = ref(false)

/** 跟唱曲目选择弹层（顶栏入口 · 2026-09-21）：底部 sheet，列表/选中态来自 store */
const pickerOpen = ref(false)

/** 顶栏选曲入口的文案（icon-only 按钮的语义补充：把「当前在唱哪首」带出去） */
const pickerLabel = computed(() =>
  sing.currentSong ? `选择跟唱曲目（当前：${sing.currentSong.title}）` : '选择跟唱曲目',
)

type Tab = 'all' | 'hot' | 'fav'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: 'chart' | 'note' | 'heart' }[] = [
  { key: 'all', label: '全部', icon: 'chart' },
  // 「热门」→「短歌」（2026-09-22 歌单排版优化）：这个分类的口径就是 `expected_lines ≤ 8`，
  // 与「热度/播放量」无关，旧文案会让用户以为排的是人气。
  { key: 'hot', label: '短歌', icon: 'note' },
  { key: 'fav', label: '收藏', icon: 'heart' },
]

/* 分类规则：hot=短歌（句数少）；fav=**用户自主收藏**（服务端 favorited 为准，2026-09-10） */
const visibleSongs = computed(() => {
  if (tab.value === 'fav') return play.favorites.value
  return tab.value === 'hot'
    ? play.songs.value.filter((s) => s.expected_lines <= 8)
    : play.songs.value
})

const featured = computed(() => play.songs.value[0] ?? null)
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
/** 底部一行「已录 / 全长」：全长取歌曲时长（契约 `duration_s`），缺失时退回录音上限 */
const totalMs = computed(
  () => (sheetDetail.value?.duration_s ? sheetDetail.value.duration_s * 1000 : SING_MAX_RECORD_MS),
)
const recClock = computed(() => formatClock(recElapsedMs.value ?? 0))
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
 *  另取 `elapsedMs`（录音轴已用时长，整秒量化）供底部「已录 / 全长」；
 *  `paused` 传入后，暂停段不计入游标与时长（2026-09-22 新增暂停能力）。 */
const { timeMs: lyricTimeMs, elapsedMs: recElapsedMs, recMs } = useSingLyricClock({
  playing: refPlaying,
  recording,
  paused,
  audioMs: reference.currentMs,
  voiceAtMs,
  firstLineMs: () => lyricFirstMs.value,
})

/**
 * 开始跟唱（P1-5，2026-09-10）：**先停参考旋律再开录**。
 * 修复前录音按钮直接 `play.startRecording()`：外放先听后唱时原唱被麦克风一起录进去
 * （实时线显示的是参考音），而「停止参考旋律」按钮此刻又被 `:disabled` 锁死 → 用户停不掉。
 * 依据：docs/31（跟唱为练习辅助，输入须为用户本人）、拷问报告 A-F3/D-F3。
 */
function startSinging() {
  voiceAtMs.value = null // 新一轮跟唱：锚点等首帧人声
  liveScore.value = null // 上一轮的实时分不带进新的一轮
  reference.stop()
  play.startRecording()
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
  <div class="u-phone">
    <!-- 统一顶栏（← 回学习主页 + 全局头像 / 唱吧 / 分享歌曲） -->
    <MobileTopBar title="唱吧" back @back="router.push('/m/learn')">
      <template #actions>
        <!-- 跟唱曲目入口（2026-09-21）：44px icon-only，与相邻分享钮同规格——
             不在这里放「当前曲名」文本：顶栏是 `minmax(min-content,1fr)` 三轨居中布局，
             右侧变宽会把居中标题顶偏（2026-09-10 长标题吞头像那次就是这类几何问题）；
             当前曲目改在弹层副标题与跟唱面板标题里显示（同一 store，天然一致）。 -->
        <button
          class="u-topbar__act m-sing-pick-entry"
          :class="{ 'is-on': !!sing.currentSong }"
          type="button"
          :title="pickerLabel"
          :aria-label="pickerLabel"
          @click="pickerOpen = true"
        >
          <MobileIcon name="music" :size="20" />
        </button>
        <button class="u-topbar__act" type="button" title="分享歌曲" aria-label="分享歌曲" @click="shareSong">
          <IconShare />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content">
      <!-- 2026-09-22 用户要求删掉页面副标题「英文歌逐句跟唱，音准与节奏即时评分。」：
           与精选卡的说明行重复，页面直接从精选卡开场 -->
      <!-- 本周精选（深色卡 · 每屏唯一深色卡）——版式见 components/sing/SingFeaturedCard.vue -->
      <!-- 加载态：骨架卡（docs/31 硬规则 3：>300ms 才出现；防抖见 useDelayedLoading）
           ——与其余 7 个移动端页同款，不再用「深青大卡写加载中…」再跳变成内容卡（P0-6 的跳变） -->
      <MobileSkeleton
        v-if="!featured && skelPending"
        :class="{ 'is-pending': !skelVisible }"
        variant="feed"
        :count="3"
        label="歌曲库加载中"
      />
      <SingFeaturedCard v-else-if="featured" :song="featured" @open="openSong" />
      <!-- 错误态（P1-6）：与兄弟页同款 u-comm-empty（原来用深青内容卡承载错误，与内容态同形、语义混淆）；
           「歌曲库加载失败」文案是既有测试锚点，必须保留。 -->
      <div v-else-if="loadFailed" class="u-comm-empty" role="status">
        <span class="u-comm-empty__icon"><MobileIcon name="info" :size="28" /></span>
        <p class="u-comm-empty__title">歌曲库加载失败</p>
        <p class="u-comm-empty__sub">{{ play.error.value ?? '网络异常，请重试' }}</p>
        <button class="u-comm-empty__btn" type="button" @click="play.loadSongs()">
          <MobileIcon name="refresh" :size="15" />
          重试
        </button>
      </div>

      <!-- 分段筛选（56px） -->
      <div class="u-segment" role="tablist">
        <button
          v-for="t in tabs"
          :key="t.key"
          type="button"
          role="tab"
          :aria-selected="tab === t.key"
          :class="{ active: tab === t.key }"
          @click="tab = t.key"
        >
          <MobileIcon :name="t.icon" />{{ t.label }}
        </button>
      </div>

      <!-- 歌单（滚动动画列表 · 真实数据 + 每首歌收藏按钮）。
           2026-09-22：原来是 `.u-dotline` 连接的一长串卡片，**随曲库长高** —— 歌一多整页被拉到
           几千像素，精选卡/筛选/页脚注释全被推走。现收进 `MobileSongList` 的定高滚动区
           （React Bits AnimatedList 的 Vue 移植）：页面高度从此与曲库规模无关，列表内部自己滚。
           区块标题与空态在**加载中/加载失败**时不渲染：否则会出现「共 0 首」+「这个分类还没有歌」
           与骨架/错误态自相矛盾的两句话（P1-6 对 hero 卡修过同一类问题，这里补齐列表侧）。 -->
      <div v-if="!skelPending && !loadFailed" class="u-section-title">
        歌曲库 · 共 {{ visibleSongs.length }} 首
      </div>
      <MobileSongList
        v-if="visibleSongs.length"
        :songs="visibleSongs"
        @open="openSong"
        @favorite="toggleFav"
      />
      <div v-if="!skelPending && !loadFailed && !visibleSongs.length" class="u-empty">
        <div class="u-empty__art"><MobileArt name="note" :size="96" /></div>
        <div class="u-empty__title">
          {{ tab === 'fav' ? '还没有收藏的歌曲' : '这个分类还没有歌' }}
        </div>
        <div class="u-empty__sub">
          {{
            tab === 'fav'
              ? '点歌曲右侧的心形按钮收藏，再点一次取消。'
              : '参考旋律离线提取完成后即可跟唱。'
          }}
        </div>
      </div>
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
            :enabled="livePitchOn"
            :paused="paused"
            :clock-ms="recMs"
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
            @toggle-reference="reference.toggle()"
            @start="startSinging"
            @pause="play.pauseRecording()"
            @resume="play.resumeRecording()"
            @stop="play.stopRecording()"
            @cancel="play.cancelRecording()"
            @toggle-live="toggleLivePitch()"
            @pick="pickerOpen = true"
          />
          <!-- 已录 / 全长（参考图「若梦 · 00:42 / 04:04」的位置）；暂停中显式标出，避免「卡住了」的误会 -->
          <div class="m-sing-foot">
            <span class="m-sing-foot__name">{{ sheetDetail?.title ?? '跟唱' }}</span>
            <span class="m-sing-foot__times">{{ recClock }} / {{ totalClock }}</span>
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
  </div>
</template>
