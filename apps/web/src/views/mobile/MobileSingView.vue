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
import { useSingPlay } from '@/composables/sing'
import { useUiStore } from '@/stores/ui'
import { loadAudioBlob } from '@/api/client'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { renderSingChart } from '@/lib/sing-chart'
import '@/styles/mobile-uic.css'
import '@/styles/mobile-sing.css'

const router = useRouter()
const ui = useUiStore()

const play = useSingPlay()

/** 跟唱面板（同页全屏 sheet）：null=关闭 */
const sheetOpen = ref(false)

type Tab = 'all' | 'hot' | 'fav'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: 'chart' | 'note' | 'heart' }[] = [
  { key: 'all', label: '全部', icon: 'chart' },
  { key: 'hot', label: '热门', icon: 'note' },
  { key: 'fav', label: '收藏', icon: 'heart' },
]

/* 分类规则（数据驱动的轻量口径）：hot=短歌（句数少），fav=低难度（level 1~2） */
const visibleSongs = computed(() =>
  tab.value === 'all'
    ? play.songs.value
    : play.songs.value.filter((s) =>
        tab.value === 'hot' ? s.expected_lines <= 8 : s.level <= 2,
      ),
)

const featured = computed(() => play.songs.value[0] ?? null)
const sheetDetail = computed(() => play.detail.value)
const recording = computed(() => play.phase.value === 'recording')
const processing = computed(
  () => play.phase.value === 'processing' || play.phase.value === 'uploading',
)
const scoreColor = (v: number | null) =>
  v == null ? '#999' : v >= 85 ? '#18a058' : v >= 60 ? '#f2a43a' : '#d03050'

/** 覆盖率（v2 口径）：有效句 < 50% → 「样本不足」提示（分数仍给，标注仅供参考） */
const evaluatedCount = computed(
  () => play.result.value?.lines.filter((x) => !x.skipped).length ?? 0,
)
const expectedCount = computed(() => play.result.value?.expected_lines ?? 0)
const lowCoverage = computed(
  () => expectedCount.value > 0 && evaluatedCount.value < expectedCount.value * 0.5,
)

/** 参考旋律回放（2026-09-09 真机反馈：先听一遍再跟唱，避免凭记忆清唱音准普遍偏低） */
const refPlaying = ref(false)
let refAudio: HTMLAudioElement | null = null

const refAudioPath = computed(() => {
  const url = sheetDetail.value?.audio_url
  return url ? `/api/v1/audio/${url.split('/').pop()}` : null
})

async function toggleReference() {
  if (refPlaying.value) {
    stopReference()
    return
  }
  const path = refAudioPath.value
  if (!path) {
    ui.showToast('该曲目暂无参考旋律音频')
    return
  }
  try {
    const blob = await loadAudioBlob(path)
    refAudio = new Audio(URL.createObjectURL(blob))
    refAudio.onended = () => {
      refPlaying.value = false
      refAudio = null
    }
    await refAudio.play()
    refPlaying.value = true
  } catch {
    ui.showToast('参考旋律播放失败，请重试')
    refPlaying.value = false
  }
}

function stopReference() {
  refAudio?.pause()
  refAudio = null
  refPlaying.value = false
}

function statusBadge(s: string): { text: string; variant: 'success' | 'star' | 'neutral' } {
  switch (s) {
    case 'ready':
      return { text: '就绪', variant: 'success' }
    case 'building':
      return { text: '提取中', variant: 'neutral' }
    case 'invalid':
      return { text: '提取失败', variant: 'neutral' }
    default:
      return { text: '未就绪', variant: 'neutral' }
  }
}

async function openSong(songId: number) {
  const ok = await play.openSong(songId)
  if (ok) sheetOpen.value = true
  else ui.showToast(play.error.value ?? '该歌暂时不能跟唱')
}

async function startOver() {
  stopReference()
  play.reset()
  sheetOpen.value = false
}

onUnmounted(() => {
  stopReference()
})

onMounted(play.loadSongs)

/** 结果就绪 → 渲染 D3 对齐图（参考 + 用户曲线） */
watch(
  () => play.result.value,
  async (v) => {
    if (!v) return
    await new Promise((r) => setTimeout(r, 60))
    const el = document.getElementById('m-sing-chart')
    if (el && sheetDetail.value) {
      renderSingChart(el, sheetDetail.value, v)
    }
  },
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

      <!-- 歌单（点线时间轴 · 真实数据） -->
      <div class="u-section-title">歌曲库</div>
      <template v-for="(s, i) in visibleSongs" :key="s.id">
        <button class="u-item" type="button" style="width: 100%; text-align: left" @click="openSong(s.id)">
          <span class="u-icon-block" :style="{ background: s.level <= 2 ? '#1E2B26' : '#16303A' }">
            <MobileIcon :name="s.level <= 2 ? 'headphone' : 'note'" :size="22" />
          </span>
          <span class="u-item__main">
            <span class="u-item__title">{{ s.title }}</span>
            <span class="u-item__sub">
              {{ s.artist ?? '歌单' }} · {{ s.expected_lines }} 句 · 难度 L{{ s.level }}
            </span>
          </span>
          <span class="u-item__right">
            <span class="u-item__value" :class="{ 'u-item__value--ink': s.pitch_ref_status !== 'ready' }">
              {{
                s.pitch_ref_status === 'ready'
                  ? '可跟唱'
                  : s.pitch_ref_status === 'building'
                    ? '提取中'
                    : s.pitch_ref_status === 'invalid'
                      ? '提取失败'
                      : '未就绪'
              }}
            </span>
            <span class="u-badge" :class="`u-badge--${statusBadge(s.pitch_ref_status).variant}`">
              {{ statusBadge(s.pitch_ref_status).text }}
            </span>
          </span>
        </button>
        <div v-if="i < visibleSongs.length - 1" class="u-dotline" aria-hidden="true">
          <span class="dot" /><span class="line" />
        </div>
      </template>
      <div v-if="!visibleSongs.length" class="u-empty">
        <div class="u-empty__art"><MobileArt name="note" :size="96" /></div>
        <div class="u-empty__title">这个分类还没有歌</div>
        <div class="u-empty__sub">参考旋律离线提取完成后即可跟唱。</div>
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
            @click="toggleReference"
          >
            <MobileIcon name="play" :size="16" />
            {{ refPlaying ? '停止参考旋律' : '听参考旋律（建议先听一遍再跟唱）' }}
          </button>
          <button
            class="u-btn u-btn--primary"
            type="button"
            style="width: 100%; margin-top: 8px"
            :disabled="recording || processing"
            @click="play.startRecording()"
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
            <div id="m-sing-chart" class="m-sing-chart" />
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
            <div class="m-sing-sheet__hint" style="margin: 8px 0">
              有效句 {{ evaluatedCount }}/{{ expectedCount }}
              <template v-if="evaluatedCount < expectedCount">
                · 未评测 {{ expectedCount - evaluatedCount }} 句（无音高/参考缺失/有效帧不足），综合按有效句均分（docs/06 §9.4 D5）
              </template>
            </div>
            <div v-if="lowCoverage" class="m-sing-sheet__hint" style="color: #c0392b; margin: 8px 0">
              样本不足（仅 {{ evaluatedCount }}/{{ expectedCount }} 句有效），分数仅供参考——建议完整唱一遍再评。
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
