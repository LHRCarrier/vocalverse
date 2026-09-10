<script setup lang="ts">
/**
 * 移动端 · 阅读器（docs/45 §6 · /m/reader/:chapterId · 沉浸页无底栏）：
 * 纯文本阅读 + 点词查义（词卡 sheet）+ 划词批注（高亮/笔记）+ 生词标记 + 听书（句级高亮）
 * + 阅读设置（字号/行距/主题，localStorage）+ 进度保存（防抖 + 退出 flush）。
 * 拆分纪律（fe-08 新代码不豁免）：查词/批注/进度/预合成为 composable，本页 ≈ 300 行。
 */
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileAnnotationNoteSheet from '@/components/mobile/MobileAnnotationNoteSheet.vue'
import MobileAnnotationSheet from '@/components/mobile/MobileAnnotationSheet.vue'
import MobileReaderBar from '@/components/mobile/MobileReaderBar.vue'
import MobileReaderSelectionBar from '@/components/mobile/MobileReaderSelectionBar.vue'
import MobileReaderSettingsSheet from '@/components/mobile/MobileReaderSettingsSheet.vue'
import MobileReaderTocSheet from '@/components/mobile/MobileReaderTocSheet.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import MobileTtsBar from '@/components/mobile/MobileTtsBar.vue'
import MobileWordCard from '@/components/mobile/MobileWordCard.vue'
import { fetchChapter, fetchVoices } from '@/api/reading'
import { buildSentenceSegments, safeAnnColor, sentenceHasAnnotation } from '@/audio/reader-words'
import { useMobileBack } from '@/composables/useMobileBack'
import { useReaderAnnotationUi } from '@/composables/useReaderAnnotationUi'
import { useBackLayers } from '@/composables/useBackLayers'
import { useReaderProgress } from '@/composables/useReaderProgress'
import { useReaderSelection } from '@/composables/useReaderSelection'
import { useReaderSettings } from '@/composables/useReaderSettings'
import { useReaderTap } from '@/composables/useReaderTap'
import { useReaderTts } from '@/composables/useReaderTts'
import { useReaderVocab } from '@/composables/useReaderVocab'
import { useReaderWordUi } from '@/composables/useReaderWordUi'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { ReadingChapter, ReadingVoice } from '@/api/reading'

const route = useRoute()
const router = useRouter()
const ui = useUiStore()

const chapterId = Number(route.params.chapterId)
const bookId = Number(route.query.book ?? 0)

/** 返回：回上一页（书详情/书架）；冷启直达阅读器（无上一条历史）时回退到书详情 */
const goBack = useMobileBack(bookId ? `/m/books/${bookId}` : '/m/bookshelf')

const chapter = ref<ReadingChapter | null>(null)
const loading = ref(true)
const error = ref('')

const voices = ref<ReadingVoice[]>([])
/** 生词标记集合（已加入生词本 → 正文淡黄下划线）；见 useReaderVocab */
const { vocabWords, refreshVocab } = useReaderVocab()

/* ---------- 阅读设置（localStorage；见 useReaderSettings） ---------- */
const { settings, patchSettings } = useReaderSettings()

/* ---------- 进度保存（防抖 + 退出 flush + 恢复定位） ---------- */
const mainEl = ref<HTMLElement | null>(null)
const readerProgress = useReaderProgress(bookId, chapterId, mainEl, () => chapter.value)
const scrollToSentence = readerProgress.scrollToSentence
const scheduleSave = () => readerProgress.scheduleSave()

/* ---------- 听书（useReaderTts：句级播放 + 整章预合成 + 听书条开关） ---------- */
const {
  ttsActive,
  tts,
  prepState,
  progressLabel,
  ttsState,
  ttsProgress,
  ttsRate,
  ttsError,
  ttsVoice,
  ttsCurrentIdx,
  openTts,
  closeTts,
  playOne,
} = useReaderTts(chapterId, () => chapter.value?.id ?? null, () => chapter.value?.sentences ?? [])

/* ---------- 查词卡与词音（useReaderWordUi：状态 + 生词本 + 词音 blob 管道） ---------- */
const { wordLookup, addWordToVocab, playWord } = useReaderWordUi(bookId, chapterId, refreshVocab)

/* ---------- 划词批注（useReaderAnnotationUi：划选 → 高亮/笔记；句尾编号标签 → 查看/编辑） ---------- */
const annotationsApi = useReaderAnnotationUi(chapterId, () => chapter.value, scrollToSentence)
const {
  annotations,
  annSheet,
  annListOpen,
  noteSheet,
  flashAnnId,
  sentList,
  sentListItems,
  annBySentence,
  saveAnnotation,
  updateAnnotation,
  removeAnnotation,
} = annotationsApi

/**
 * 长按抑制原生选词的时间窗：长按（静止）走「整句批注卡」，拖动才走划词。
 * WebView 的原生选词在长按后 ~500ms 才出现，若不抑制会双开弹层（先句子卡、再划词卡）。
 */
let suppressSelectionUntil = 0

/** 长按句子（550ms 静止）→ 打开该句的批注卡（2026-09-09 组长拍板） */
function onLongPressSentence(idx: number) {
  suppressSelectionUntil = Date.now() + 1200
  selIdx.value = null
  wordLookup.close()
  annotationsApi.createForSentence(idx)
}

function onSelectionCreate() {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return
  annotationsApi.createFromSelection(sel)
}

/* ---------- 渲染（词块 × 批注区间 → 上色分段；点词查义） ---------- */
/** 句子渲染段：词 + 批注着色（见 reader-words.buildSentenceSegments） */
function sentenceSegments(idx: number) {
  const s = chapter.value?.sentences[idx]
  return s ? buildSentenceSegments(s.text, s.start, annotations.value) : []
}

/* ---------- 点击语义（词=查词 / 句=选中；长按=批注卡；分发在 useReaderTap） ---------- */
const { selIdx, onReaderClick, onPointerDown, onPointerMove, onPointerUp } = useReaderTap({
  getSentence: (idx) => chapter.value?.sentences[idx],
  openWord: (word, context, idx) => void wordLookup.openFor(word, context, idx),
  openNoteById: annotationsApi.openNoteById,
  annotations,
  ttsState,
  ttsCurrentIdx,
  playFrom: (idx) => void tts.playFrom(idx),
  onLongPress: onLongPressSentence,
})

/**
 * 句子级动作（单一入口，供两处调用）：
 * · 动作条（单击句子/分隔符选中后）：highlight=色点（显式传色→直出）、note=批注、play=听这句
 * · 查词卡底部：highlight=**先出选色面板**（不传色）、note=批注这句
 *   （**点中空格的命中区只有 4.6px，卡片按钮才是可靠入口**——2026-09-10 量测结论）
 * 2026-09-09 修复组长实测「点高亮这句不等选色就默认第一个颜色」：不传色 = 先选色再落库。
 */
function runSentenceAction(action: 'highlight' | 'note' | 'play', color?: string) {
  const idx = selIdx.value ?? wordLookup.state.sentenceIdx
  if (idx == null) return
  selIdx.value = null
  wordLookup.close()
  if (action === 'play') {
    // 只显示听书条，不整章预合成；单句模式只播这一句，播完即止（2026-09-10 组长反馈）
    playOne(idx)
  } else if (action === 'note') {
    annotationsApi.createForSentence(idx)
  } else if (color) {
    // 动作条色点直出：色点本身就是选色动作
    void annotationsApi
      .highlightSentence(idx, color)
      .then((ok) => ui.showToast(ok ? '已高亮这句' : '高亮失败'))
  } else {
    // 查词卡「高亮这句」：先让用户选色，保存后才高亮
    annotationsApi.chooseColorForSentence(idx)
  }
}

async function refreshAnnotations() {
  await annotationsApi.refresh()
}

/* ---------- 装载与生命周期 ---------- */
async function load() {
  loading.value = true
  error.value = ''
  try {
    const c = await fetchChapter(chapterId)
    chapter.value = c
    fetchVoices().then((v) => (voices.value = v)).catch(() => {})
    await Promise.all([refreshVocab(), refreshAnnotations()])
    await nextTick()
    readerProgress.restore()
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

/* 划词监听（selectionchange + 节流 + 长按抑制窗口；实现见 useReaderSelection） */
useReaderSelection({
  root: () => mainEl.value,
  onSelect: onSelectionCreate,
  suppressed: () => Date.now() < suppressSelectionUntil,
})

onMounted(() => {
  void load()
})
onBeforeUnmount(() => {
  void readerProgress.flush()
})

/* ---------- 其他弹层 ---------- */
const tocOpen = ref(false)
const settingsOpen = ref(false)

/**
 * 原生返回手势/按键：按「最上层到最下层」顺序关弹层，全关完才交给原生回退历史
 * （否则滑动返回会连带退页/退到桌面；实现见 useBackLayers）
 */
useBackLayers([
  { open: () => selIdx.value !== null, close: () => (selIdx.value = null) },
  { open: () => noteSheet.open, close: () => (noteSheet.open = false) },
  { open: () => wordLookup.state.open, close: () => wordLookup.close() },
  { open: () => annSheet.open, close: () => (annSheet.open = false) },
  { open: () => sentList.open, close: () => (sentList.open = false) },
  { open: () => annListOpen.value, close: () => (annListOpen.value = false) },
  { open: () => settingsOpen.value, close: () => (settingsOpen.value = false) },
  { open: () => tocOpen.value, close: () => (tocOpen.value = false) },
  {
    open: () => ttsActive.value,
    close: closeTts,
  },
])

function nextChapter() {
  // 章节切换：回详情页列表（v1 精简路径）
  if (bookId) void router.push(`/m/books/${bookId}`)
}
</script>

<template>
  <div
    class="u-rd-views"
    :data-theme="settings.theme"
    :style="{ '--ur-size-base': `${settings.fontSize}px`, '--ur-line-base': settings.lineHeight }"
  >
    <div v-if="loading" class="u-rd">
      <div class="u-rd__main">
        <p class="u-comm-empty__sub">章节加载中…</p>
      </div>
    </div>
    <div v-else-if="error" class="u-rd">
      <div class="u-rd__main">
        <div class="u-comm-empty" role="status">
          <span class="u-comm-empty__title">加载失败</span>
          <p class="u-comm-empty__sub">{{ error }}</p>
          <button class="u-comm-empty__btn" type="button" @click="load">重试</button>
        </div>
      </div>
    </div>
    <template v-else-if="chapter">
      <MobileTopBar :title="chapter.title" back @back="goBack" />

      <main
        ref="mainEl"
        class="u-rd__main"
        @click="onReaderClick"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="onPointerUp"
        @pointercancel="onPointerUp"
        @scroll.passive="scheduleSave()"
      >
        <p class="u-rd__chapter-title">{{ chapter.title }}</p>
        <p class="u-rd__chapter-sub">第 {{ chapter.chapter_no }} 章 · {{ Math.round(chapter.word_count / 100) / 10 }}k 词</p>

        <div v-if="prepState.status === 'running'" class="u-rd-prep" role="status">
          <span>{{ prepState.text }}</span>
          <span class="u-rd-prep__bar" aria-hidden="true">
            <span
              class="u-rd-prep__fill"
              :style="{ width: `${prepState.total ? (prepState.done / prepState.total) * 100 : 0}%` }"
            />
          </span>
          <span>{{ prepState.done }}/{{ prepState.total }}</span>
        </div>

        <p v-for="(_, pi) in chapter.paragraphs" :key="pi" class="u-rd__para">
          <span
            v-for="s in chapter.sentences.filter((x) => x.para_idx === pi)"
            :key="s.idx"
            class="u-rd__sentence"
            :class="{
              'is-current': ttsCurrentIdx === s.idx,
              'is-annotated': sentenceHasAnnotation(annotations, s.start, s.end),
              'is-selected': selIdx === s.idx,
            }"
            :data-idx="s.idx"
          >
            <span
              v-for="(seg, wi) in sentenceSegments(s.idx)"
              :key="wi"
              class="u-rd__seg"
              :class="{
                'is-word': !!seg.word && vocabWords.has(seg.word.toLowerCase()),
                'is-ann': !!seg.ann,
                'is-flash': !!seg.ann && seg.ann.id === flashAnnId,
              }"
              :style="seg.ann ? { '--ur-ann-color': safeAnnColor(seg.ann.color) } : undefined"
              :data-word="seg.word ?? undefined"
              :data-ann="seg.ann ? seg.ann.id : undefined"
            >{{ seg.text }}</span>
            <!-- 句尾上标编号标签（2026-09-09 组长实测改版：句首竖条「很奇怪、不明显」→
                 改为句末 [1][2]…，按句内序号、按批注色区分，点标签看/改该条批注） -->
            <span v-if="annBySentence.has(s.idx)" class="u-rd__senttags">
              <button
                v-for="(a, ai) in annBySentence.get(s.idx)"
                :key="a.id"
                class="u-rd__senttag"
                :class="{ 'is-flash': a.id === flashAnnId }"
                type="button"
                :style="{ '--ur-ann-color': safeAnnColor(a.color) }"
                :aria-label="`查看这句的第 ${ai + 1} 条批注`"
                :data-ann="a.id"
                @click.stop="annotationsApi.openNote(a)"
              >{{ ai + 1 }}</button>
            </span>
          </span>
        </p>
      </main>

      <MobileTtsBar
        v-if="ttsActive"
        :label="ttsError || progressLabel"
        :playing="ttsState === 'playing'"
        :progress="ttsProgress"
        :rate="ttsRate"
        :busy-text="prepState.status === 'running' ? prepState.text : ''"
        @toggle="tts.toggle()"
        @prev="tts.prev()"
        @next="tts.next()"
        @change-rate="tts.changeRate()"
        @close="tts.stop(); ttsActive = false"
      />
      <!-- 句子选中动作条（单击句子后出现；听书进行中不显示） -->
      <MobileReaderSelectionBar
        :visible="selIdx !== null"
        :has-annotation="selIdx !== null && annBySentence.has(selIdx)"
        @highlight="runSentenceAction('highlight', $event)"
        @note="runSentenceAction('note')"
        @open-note="selIdx !== null && annotationsApi.openSentence(selIdx); selIdx = null"
        @play="runSentenceAction('play')"
        @close="selIdx = null"
      />
      <MobileReaderBar
        :tts-active="ttsActive"
        @toc="tocOpen = true"
        @annotations="annListOpen = true; refreshAnnotations()"
        @tts="openTts"
        @settings="settingsOpen = true"
      />

      <MobileWordCard
        v-if="wordLookup.state.open"
        :result="wordLookup.state.result"
        :loading="wordLookup.state.loading"
        :missing="wordLookup.state.missing"
        :sentence-index="wordLookup.state.sentenceIdx"
        @close="wordLookup.close()"
        @add-vocab="addWordToVocab"
        @play-word="playWord"
        @sentence-highlight="runSentenceAction('highlight')"
        @sentence-note="runSentenceAction('note')"
      />
      <MobileReaderSettingsSheet
        :open="settingsOpen"
        :theme="settings.theme"
        :font-size="settings.fontSize"
        :line-height="settings.lineHeight"
        :voices="voices"
        :current-voice="ttsVoice"
        @update:open="settingsOpen = $event"
        @patch="patchSettings"
        @voice="tts.setVoice"
        @next="nextChapter"
      />
      <MobileAnnotationSheet
        :open="annSheet.open && chapter !== null"
        :mode="annSheet.mode"
        :snippet="annSheet.snippet"
        @save="saveAnnotation"
        @update:open="annSheet.open = $event"
      />
      <MobileAnnotationSheet
        :open="annListOpen"
        mode="list"
        :annotations="annotations"
        @delete="removeAnnotation"
        @jump="annotationsApi.jump"
        @update:open="annListOpen = $event"
      />
      <!-- 本句批注列表（句首角标命中多条时打开） -->
      <MobileAnnotationSheet
        :open="sentList.open"
        mode="list"
        title="本句批注"
        :annotations="sentListItems"
        @delete="removeAnnotation"
        @jump="annotationsApi.jump"
        @update:open="sentList.open = $event"
      />
      <!-- 单条批注查看/编辑（点正文批注段 / 句首角标 / 段尾笔记角标 / 列表跳转后自动弹出） -->
      <MobileAnnotationNoteSheet
        :open="noteSheet.open"
        :item="noteSheet.item"
        :busy="annotationsApi.noteBusy.value"
        @save="updateAnnotation"
        @delete="removeAnnotation"
        @update:open="noteSheet.open = $event"
      />
      <MobileReaderTocSheet :open="tocOpen" @update:open="tocOpen = $event" @close="tocOpen = false" />
    </template>
  </div>
</template>
