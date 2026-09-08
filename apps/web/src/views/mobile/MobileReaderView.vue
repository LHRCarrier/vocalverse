<script setup lang="ts">
/**
 * 移动端 · 阅读器（docs/45 §6 · /m/reader/:chapterId · 沉浸页无底栏）：
 * 纯文本阅读 + 点词查义（词卡 sheet）+ 划词批注（高亮/笔记）+ 生词标记 + 听书（句级高亮）
 * + 阅读设置（字号/行距/主题，localStorage）+ 进度保存（防抖 + 退出 flush）。
 * 拆分纪律（fe-08 新代码不豁免）：查词/批注/进度/预合成为 composable，本页 ≈ 300 行。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
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
import { buildSentenceSegments, sentenceHasAnnotation } from '@/audio/reader-words'
import { useChapterPrep } from '@/composables/useChapterPrep'
import { useChapterTts } from '@/composables/useChapterTts'
import { useMobileBack } from '@/composables/useMobileBack'
import { useNativeBack } from '@/composables/useNativeBack'
import { useReaderAnnotations } from '@/composables/useReaderAnnotations'
import { useReaderProgress } from '@/composables/useReaderProgress'
import { useReaderSettings } from '@/composables/useReaderSettings'
import { useReaderTap } from '@/composables/useReaderTap'
import { useReaderVocab } from '@/composables/useReaderVocab'
import { useWordAudio } from '@/composables/useWordAudio'
import { useWordLookup } from '@/composables/useWordLookup'
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

/* ---------- 听书（useChapterTts 句级播放 + useChapterPrep 整章预合成） ---------- */
const ttsActive = ref(false)
const tts = useChapterTts(chapterId, () => chapter.value?.sentences ?? [])
const ttsState = tts.state
const ttsProgress = tts.progress
const ttsRate = tts.rate
const ttsError = tts.errorText
const ttsVoice = tts.voice
const ttsCurrentIdx = tts.currentIdx
const { prepState, start: startPrep } = useChapterPrep()
const progressLabel = computed(() => {
  const total = chapter.value?.sentences.length ?? 0
  return total ? `${Math.min(ttsCurrentIdx.value + 1, total)}/${total}` : '听书'
})

function openTts() {
  if (!chapter.value) return
  ttsActive.value = true
  if (prepState.status === 'idle' || prepState.status === 'failed') {
    startPrep(chapter.value.id, ttsVoice.value)
  }
}

/* ---------- 查词卡（useWordLookup：纯状态管理；词卡展示层在 MobileWordCard） ---------- */
const wordLookup = useWordLookup()

async function addWordToVocab() {
  const ok = await wordLookup.addToVocab({ bookId, chapterId })
  ui.showToast(ok ? '已加入生词本' : '加入失败')
  if (ok) await refreshVocab()
}

/* ---------- 划词批注（useReaderAnnotations：句内划选 → 高亮/笔记） ---------- */
const annotationsApi = useReaderAnnotations(chapterId, () => chapter.value, scrollToSentence)
const annotations = annotationsApi.annotations
const annSheet = annotationsApi.annSheet
const annListOpen = annotationsApi.annListOpen
const { noteSheet, flashAnnId } = annotationsApi

function onSelectionCreate() {
  const sel = window.getSelection()
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return
  annotationsApi.createFromSelection(sel)
}

async function saveAnnotation(payload: { note: string; color: string }) {
  const ok = await annotationsApi.save(payload)
  ui.showToast(ok ? '已添加批注' : '批注保存失败')
}

async function removeAnnotation(id: number) {
  await annotationsApi.remove(id)
}

/* ---------- 渲染（词块 × 批注区间 → 上色分段；点词查义） ---------- */
/** 句子渲染段：词 + 批注着色（见 reader-words.buildSentenceSegments） */
function sentenceSegments(idx: number) {
  const s = chapter.value?.sentences[idx]
  return s ? buildSentenceSegments(s.text, s.start, annotations.value) : []
}

/* ---------- 点击语义（词=查词 / 句=选中；分发在 useReaderTap） ---------- */
const { selIdx, onReaderClick } = useReaderTap({
  getSentence: (idx) => chapter.value?.sentences[idx],
  openWord: (word, context, idx) => void wordLookup.openFor(word, context, idx),
  openNoteById: annotationsApi.openNoteById,
  annotations,
  ttsState,
  ttsCurrentIdx,
  playFrom: (idx) => void tts.playFrom(idx),
})

/** 查词卡「朗读」：词读音端点需带 token，走 blob 管道（useWordAudio） */
const { play: playWordAudio } = useWordAudio()
function playWord(): void {
  const word = wordLookup.state.word
  if (!word) return
  void playWordAudio(word).then((ok) => !ok && ui.showToast('读音播放失败'))
}

/**
 * 句子级动作（单一入口，供两处调用）：
 * · 动作条（单击句子/分隔符选中后）：highlight=色点、note=批注、play=听这句
 * · 查词卡底部：highlight=高亮这句、note=批注这句（**点中空格的命中区只有 4.6px，
 *   卡片按钮才是可靠入口**——2026-09-10 量测结论）
 */
function runSentenceAction(action: 'highlight' | 'note' | 'play', color = '#fde68a') {
  const idx = selIdx.value ?? wordLookup.state.sentenceIdx
  if (idx == null) return
  selIdx.value = null
  wordLookup.close()
  if (action === 'play') {
    // 只显示听书条，不整章预合成；单句模式只播这一句，播完即止（2026-09-10 组长反馈）
    ttsActive.value = true
    void tts.playOne(idx)
  } else if (action === 'note') {
    annotationsApi.createForSentence(idx)
  } else {
    void annotationsApi
      .highlightSentence(idx, color)
      .then((ok) => ui.showToast(ok ? '已高亮这句' : '高亮失败'))
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

/** selectionchange：长按/划选结束（非 collapsed）经防抖后进入批注创建 */
let lastSelTs = 0
function onSelectionChange() {
  const sel = window.getSelection()
  if (!sel || sel.isCollapsed) return
  const now = Date.now()
  if (now - lastSelTs < 200) return
  lastSelTs = now
  if (mainEl.value?.contains(sel.anchorNode ?? sel.focusNode)) onSelectionCreate()
}

onMounted(() => {
  void load()
  document.addEventListener('selectionchange', onSelectionChange)
})
onBeforeUnmount(() => {
  document.removeEventListener('selectionchange', onSelectionChange)
  void readerProgress.flush()
})

/* ---------- 其他弹层 ---------- */
const tocOpen = ref(false)
const settingsOpen = ref(false)

/**
 * 原生返回手势/按键：先关最上层弹层，再交给原生回退历史
 * （否则滑动返回会连带退页/退到桌面；见 useNativeBack 注释）
 */
useNativeBack(() => {
  if (selIdx.value !== null) {
    selIdx.value = null
    return true
  }
  if (noteSheet.open) {
    noteSheet.open = false
    return true
  }
  if (wordLookup.state.open) {
    wordLookup.close()
    return true
  }
  if (annSheet.open) {
    annSheet.open = false
    return true
  }
  if (annListOpen.value) {
    annListOpen.value = false
    return true
  }
  if (settingsOpen.value) {
    settingsOpen.value = false
    return true
  }
  if (tocOpen.value) {
    tocOpen.value = false
    return true
  }
  if (ttsActive.value) {
    tts.stop()
    ttsActive.value = false
    return true
  }
  return false
})

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

      <main ref="mainEl" class="u-rd__main" @click="onReaderClick" @scroll.passive="scheduleSave()">
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
              :style="{ background: seg.ann ? (seg.ann.color ?? 'var(--ur-theme-annotation)') : undefined }"
              :data-word="seg.word ?? undefined"
              :data-ann="seg.ann ? seg.ann.id : undefined"
            >{{ seg.text }}<span
              v-if="seg.noteMarker && seg.ann"
              class="u-rd__annmark"
              :data-ann="seg.ann.id"
              :style="{ background: seg.ann.color ?? '#fde68a' }"
              aria-hidden="true"
            /></span>
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
        @highlight="runSentenceAction('highlight', $event)"
        @note="runSentenceAction('note')"
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
        mode="create"
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
      <!-- 单条批注查看（点正文批注段 / 批注角标 / 列表跳转后自动弹出） -->
      <MobileAnnotationNoteSheet
        :open="noteSheet.open"
        :item="noteSheet.item"
        @delete="removeAnnotation"
        @update:open="noteSheet.open = $event"
      />
      <MobileReaderTocSheet :open="tocOpen" @update:open="tocOpen = $event" @close="tocOpen = false" />
    </template>
  </div>
</template>
