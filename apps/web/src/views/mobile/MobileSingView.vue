<script setup lang="ts">
/**
 * 移动端 · 唱吧（跟唱）—— M3 唱歌 P0 接真（2026-09-09）
 * 全链路：选歌（歌曲列表 + 40905 就绪门禁）→ 整首跟唱（≤180s）→ 上传 →
 * 异步评分轮询（queued→processing→done|failed）→ 逐句评分 + D3 对齐图 + 报告。
 * 数据源：GET /api/v1/songs(/id)、POST /sessions(kind=sing)、POST /sessions/{id}/audio、
 * GET /sing/attempts/{id}(/status)（api/sing.ts；错误码映射见 singErrorMessage）。
 * 视觉：沿用重制版基线（深青精选卡/56px 分段/点线时间轴歌单）；交互逻辑接真。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import IconShare from '~icons/tabler/share'

import { shareDemoLink } from '@/composables/share'
import { useSingPlay } from '@/composables/sing'
import { useReferenceAudio } from '@/composables/useReferenceAudio'
import { useUiStore } from '@/stores/ui'

import type { SongSummary } from '@/api/sing'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileSongRow from '@/components/mobile/MobileSongRow.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import LivePitchChart from '@/components/LivePitchChart.vue'
import { renderSingChart } from '@/lib/sing-chart'
import '@/styles/mobile-uic.css'
import '@/styles/mobile-sing.css'

const router = useRouter()
const ui = useUiStore()

const play = useSingPlay()

/** 跟唱面板（同页全屏 sheet）：null=关闭 */
const sheetOpen = ref(false)

/** 报告图容器（P1-8：模板 ref 取代 document.getElementById） */
const chartEl = ref<HTMLElement | null>(null)

type Tab = 'all' | 'hot' | 'fav'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: 'chart' | 'note' | 'heart' }[] = [
  { key: 'all', label: '全部', icon: 'chart' },
  { key: 'hot', label: '热门', icon: 'note' },
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
const processing = computed(
  () => play.phase.value === 'processing' || play.phase.value === 'uploading',
)
/** 分数→颜色（P1-14：契约生成类型里逐句分项是可选字段，签名同时接 null/undefined） */
const scoreColor = (v: number | null | undefined) =>
  v == null ? '#999' : v >= 85 ? '#18a058' : v >= 60 ? '#f2a43a' : '#d03050'

/** 有效句计数（覆盖率提示文案由后端 `alignment.coverage_note` 下发，v4 口径） */
const evaluatedCount = computed(
  () => play.result.value?.lines.filter((x) => !x.skipped).length ?? 0,
)
const expectedCount = computed(() => play.result.value?.expected_lines ?? 0)

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

/**
 * 开始跟唱（P1-5，2026-09-10）：**先停参考旋律再开录**。
 * 修复前录音按钮直接 `play.startRecording()`：外放先听后唱时原唱被麦克风一起录进去
 * （实时线显示的是参考音），而「停止参考旋律」按钮此刻又被 `:disabled` 锁死 → 用户停不掉。
 * 依据：docs/31（跟唱为练习辅助，输入须为用户本人）、拷问报告 A-F3/D-F3。
 */
function startSinging() {
  reference.stop()
  play.startRecording()
}

async function openSong(songId: number) {
  reference.stop() // 换歌即停播（原实现会继续播上一首的参考旋律）
  const ok = await play.openSong(songId)
  if (ok) sheetOpen.value = true
  else ui.showToast(play.error.value ?? '该歌暂时不能跟唱')
}

/** 收藏按钮：点一下收藏，再点一次取消（乐观更新 + 失败回滚，见 useSingPlay.toggleFavorite） */
async function toggleFav(song: SongSummary) {
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

/** 结果就绪 → 渲染 D3 对齐图（参考 + 用户曲线）。
 *
 * P1-8（2026-09-10）：原实现用 `document.getElementById` + 一次性 60ms 延时——若结果在
 * **面板关闭时**落地（如评分中关面板），元素不存在 → 静默跳过，且再打开时不会重画 →
 * 报告页图表区永久空盒（实测 `#m-sing-chart` innerHTML 长度 0）。现改为**模板 ref** +
 * 监听 `[result, sheetOpen]`：面板打开且结果就绪时才画，两种情况都能出图。
 * 依据：docs/35（状态覆盖：交互后/重新进入）、拷问报告 A-F4/D-F28。
 */
watch(
  [() => play.result.value, sheetOpen],
  async ([v, open]) => {
    if (!v || !open) return
    await nextTick()
    await new Promise((r) => setTimeout(r, 60))
    if (chartEl.value && sheetDetail.value) {
      renderSingChart(chartEl.value, sheetDetail.value, v)
    }
  },
  { flush: 'post' },
)

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
        <button class="u-topbar__act" type="button" title="分享歌曲" aria-label="分享歌曲" @click="shareSong">
          <IconShare />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content">
      <p class="u-head__sub" style="margin: 0 0 16px">英文歌逐句跟唱，音准与节奏即时评分。</p>

      <!-- 本周精选（深青卡 · 每屏唯一深色卡 · 音符线稿锚点） -->
      <section v-if="featured" class="u-dark-card u-dark-card--teal">
        <div class="u-dark-card__art" aria-hidden="true">
          <MobileArt name="note" :size="104" />
        </div>
        <span class="u-chip u-chip--teal">
          {{ featured.pitch_ref_status === 'ready' ? '本周精选' : '参考旋律提取中' }}
        </span>
        <span class="u-dark-card__meta">
          {{ featured.artist ?? '歌单' }} · {{ featured.expected_lines }} 句 ·
          {{ featured.pitch_ref_status === 'ready' ? '可跟唱' : '稍后开放' }}
        </span>
        <h2 class="u-dark-card__title">{{ featured.title }}</h2>
        <p class="u-dark-card__desc">
          {{
            featured.pitch_ref_status === 'ready'
              ? `整首跟唱 ≤3 分钟，逐句音准/节奏/发音 + D3 对齐图。`
              : '参考旋律正在离线提取，完成后即可跟唱（自动刷新）。'
          }}
        </p>
        <button
          class="u-btn u-btn--ghost"
          type="button"
          style="margin-top: 16px"
          @click="openSong(featured.id)"
        >
          <MobileIcon name="mic" :size="16" /> 去跟唱
        </button>
      </section>
      <!-- 加载失败态（P1-6）：原实现在 v-else 里一律显示「加载中…」，且错误只写进 sheet 内的
           play.error → 断网/500/401 时页面永久「加载中…」+ 列表空态「这个分类还没有歌」两句
           自相矛盾的话，且没有重试入口。这里把三者拆开：loading / error（含重试）/ empty。
           依据：docs/35（状态覆盖：空态/错误态）、拷问报告 A-F5/D-F4。 -->
      <section v-else-if="loadFailed" class="u-dark-card u-dark-card--teal">
        <div class="u-dark-card__art" aria-hidden="true"><MobileArt name="note" :size="104" /></div>
        <span class="u-chip u-chip--teal">加载失败</span>
        <h2 class="u-dark-card__title">歌曲库加载失败</h2>
        <p class="u-dark-card__desc">{{ play.error.value ?? '网络异常，请重试' }}</p>
        <button class="u-btn u-btn--ghost" type="button" style="margin-top: 16px" @click="play.loadSongs()">
          <MobileIcon name="refresh" :size="16" /> 重试
        </button>
      </section>
      <section v-else class="u-dark-card u-dark-card--teal">
        <div class="u-dark-card__art" aria-hidden="true"><MobileArt name="note" :size="104" /></div>
        <span class="u-chip u-chip--teal">歌曲库</span>
        <h2 class="u-dark-card__title">加载中…</h2>
      </section>

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

      <!-- 歌单（点线时间轴 · 真实数据 + 每首歌收藏按钮） -->
      <div class="u-section-title">歌曲库</div>
      <template v-for="(s, i) in visibleSongs" :key="s.id">
        <MobileSongRow :song="s" @open="openSong" @favorite="toggleFav" />
        <div v-if="i < visibleSongs.length - 1" class="u-dotline" aria-hidden="true">
          <span class="dot" /><span class="line" />
        </div>
      </template>
      <div v-if="!visibleSongs.length" class="u-empty">
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

      <p class="u-note" style="margin-top: 24px">
        跟唱评分 = 0.5·音准 + 0.2·节奏 + 0.3·发音（发音=抽样句，默认前 3 句）；蓝图与抽检见 docs/06 §9.4。
      </p>
    </div>

    <!-- 跟唱面板（全屏 sheet） -->
    <div v-if="sheetOpen" class="m-sing-sheet">
      <div class="m-sing-sheet__head">
        <button class="u-topbar__act" type="button" aria-label="关闭" @click="startOver">
          <MobileIcon name="chevron" :size="20" style="transform: rotate(90deg)" />
        </button>
        <strong>{{ sheetDetail?.title ?? '跟唱' }}</strong>
        <span class="m-sing-sheet__sub">{{ sheetDetail?.expected_lines }} 句 · 整首 ≤180s</span>
      </div>

      <div class="m-sing-sheet__body">
        <!-- 录音/评分阶段 -->
        <template v-if="!play.result.value">
          <div v-if="play.error.value" class="m-sing-sheet__hint" style="color: #c0392b; margin: 8px 0">
            {{ play.error.value }}
          </div>
          <div class="m-sing-sheet__lyrics">
            <p v-for="line in (sheetDetail?.lines ?? []).slice(0, 6)" :key="line.seq" class="m-sing-lyric">
              {{ line.text }}
            </p>
            <p v-if="(sheetDetail?.lines.length ?? 0) > 6" class="m-sing-lyric m-sing-lyric--more">
              …共 {{ sheetDetail?.lines.length }} 句
            </p>
          </div>
          <button
            class="u-btn u-btn--secondary"
            type="button"
            style="width: 100%; margin-top: 12px"
            :disabled="recording"
            @click="reference.toggle()"
          >
            <MobileIcon name="play" :size="16" />
            {{ refPlaying ? '停止参考旋律' : '听参考旋律（建议先听一遍再跟唱）' }}
          </button>
          <button
            class="u-btn u-btn--primary"
            type="button"
            style="width: 100%; margin-top: 8px"
            :disabled="recording || processing"
            @click="startSinging"
          >
            <MobileIcon name="mic" :size="16" />
            {{ recording ? '录音中…' : processing ? '上传/评分中…' : '开始跟唱（≤3 分钟）' }}
          </button>
          <div v-if="recording" class="m-sing-sheet__stopbar">
            <button class="u-btn u-btn--secondary" type="button" style="width: 48%" @click="play.cancelRecording()">
              放弃重录
            </button>
            <button class="u-btn u-btn--primary" type="button" style="width: 48%" @click="play.stopRecording()">
              停止并评分
            </button>
          </div>
          <!-- 实时音准线（docs/06 §9.4 注记：练习辅助，同流分析，评分以离线为准） -->
          <LivePitchChart
            v-if="sheetDetail"
            class="m-sing-live"
            :detail="sheetDetail"
            :stream="play.getLiveStream()"
            :active="recording"
          />
          <div v-if="processing" class="m-sing-sheet__progress">
            <div class="m-sing-sheet__bar">
              <div class="m-sing-sheet__bar-inner" :style="{ width: `${play.progressPct.value}%` }" />
            </div>
            <span>{{ play.progressPct.value }}% · {{ play.progressPct.value < 100 ? '评分计算中…' : '正在生成报告…' }}</span>
          </div>
          <div class="m-sing-sheet__hint">
            移动端提示：授权后请保持前台；录音自动在 3 分钟停止。
          </div>
        </template>

        <!-- 报告阶段 -->
        <template v-else>
          <div class="m-sing-report">
            <div class="m-sing-report__score">
              <span class="m-sing-report__num">{{ play.result.value.overall?.toFixed(1) ?? '—' }}</span>
              <span class="m-sing-report__label">综合分</span>
            </div>
            <div class="m-sing-report__sub">
              <span>音准 {{ play.result.value.pitch?.toFixed(1) ?? '—' }}</span>
              <span>节奏 {{ play.result.value.rhythm?.toFixed(1) ?? '—' }}</span>
              <span>发音 {{ play.result.value.pron?.toFixed(1) ?? '—' }}</span>
            </div>
            <div ref="chartEl" class="m-sing-chart" />
            <div class="m-sing-report__lines">
              <div v-for="(l, i) in play.result.value.lines" :key="l.seq" class="m-sing-line">
                <span class="m-sing-line__text">
                  {{ i + 1 }}.
                  <template v-if="l.skipped">未评测（{{ l.reason ?? 'skipped' }}）</template>
                  <template v-else-if="l.onset_dev_ms != null">
                    起唱偏差 {{ Math.round(l.onset_dev_ms) }}ms
                  </template>
                  <template v-else>✓</template>
                </span>
                <span class="m-sing-line__score">
                  <b :style="{ color: scoreColor(l.pitch_score) }">{{ l.pitch_score?.toFixed(0) ?? '—' }}</b>
                  <i :style="{ color: scoreColor(l.rhythm_score) }">{{ l.rhythm_score?.toFixed(0) ?? '—' }}</i>
                </span>
              </div>
            </div>
            <!-- 有效句 + v3/v4 提示（音域/在调音符/覆盖率置信度；docs/06 §9.4） -->
            <div class="m-sing-sheet__hint" style="margin: 8px 0">
              有效句 {{ evaluatedCount }}/{{ expectedCount }}
              <template v-if="evaluatedCount < expectedCount">
                · 未评测 {{ expectedCount - evaluatedCount }} 句（无音高/参考缺失/有效帧不足），综合按有效句均分（docs/06 §9.4 D5）
              </template>
              <template v-if="play.result.value.alignment?.range_hint"> · {{ play.result.value.alignment.range_hint }}</template>
              <template v-if="play.result.value.alignment?.note_hit_rate != null"> · 在调音符 {{ Math.round((play.result.value.alignment.note_hit_rate ?? 0) * 100) }}%（未唱到的音符按比例扣减音准分）</template>
            </div>
            <div v-if="play.result.value.alignment?.coverage_note" class="m-sing-sheet__hint" style="color: #c0392b; margin: 8px 0">
              {{ play.result.value.alignment.coverage_note }}
            </div>
            <button class="u-btn u-btn--ghost" type="button" style="width: 100%; margin-top: 10px" @click="startOver">
              返回歌单
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
