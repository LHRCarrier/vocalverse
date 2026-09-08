<script setup lang="ts">
/**
 * 移动端 · 阅读器（docs/45 §6 · /m/reader/:chapterId · 沉浸页无底栏）：
 * 纯文本阅读 + 点词查义（词卡 sheet）+ 划词批注（高亮/笔记）+ 生词标记 + 听书（句级高亮）
 * + 阅读设置（字号/行距/主题，localStorage）+ 进度保存（防抖 + 退出 flush）。
 * 拆分纪律（fe-08 新代码不豁免）：查词/批注/进度/预合成为 composable，本页 ≈ 300 行。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import MobileAnnotationSheet from '@/components/mobile/MobileAnnotationSheet.vue'
import MobileReaderBar from '@/components/mobile/MobileReaderBar.vue'
import MobileReaderSettingsSheet from '@/components/mobile/MobileReaderSettingsSheet.vue'
import MobileReaderTocSheet from '@/components/mobile/MobileReaderTocSheet.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import MobileTtsBar from '@/components/mobile/MobileTtsBar.vue'
import MobileWordCard from '@/components/mobile/MobileWordCard.vue'
import { fetchChapter, fetchVoices, fetchVocab } from '@/api/reading'
import { splitPieceWords, vocabWordSet } from '@/audio/reader-words'
import { useChapterPrep } from '@/composables/useChapterPrep'
import { useChapterTts } from '@/composables/useChapterTts'
import { useMobileBack } from '@/composables/useMobileBack'
import { useReaderAnnotations } from '@/composables/useReaderAnnotations'
import { useReaderProgress } from '@/composables/useReaderProgress'
import { useWordLookup } from '@/composables/useWordLookup'
import { useUiStore } from '@/stores/ui'
import '@/styles/mobile-uic.css'
import '@/styles/reader-uic.css'

import type { AnnotationItem, ReadingChapter, ReadingVoice } from '@/api/reading'

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
const vocabWords = ref<Set<string>>(new Set())

/* ---------- 阅读设置（localStorage） ---------- */
const settings = reactive({
  theme: (localStorage.getItem('vv_rd_theme') as 'paper' | 'cream' | 'night') ?? 'paper',
  fontSize: Number(localStorage.getItem('vv_rd_font') ?? 19),
  lineHeight: Number(localStorage.getItem('vv_rd_line') ?? 1.85),
})
function patchSettings(patch: Partial<typeof settings>) {
  Object.assign(settings, patch)
  localStorage.setItem('vv_rd_theme', settings.theme)
  localStorage.setItem('vv_rd_font', String(settings.fontSize))
  localStorage.setItem('vv_rd_line', String(settings.lineHeight))
}

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

async function refreshVocab() {
  try {
    const res = await fetchVocab()
    vocabWords.value = vocabWordSet(res.items)
  } catch {
    /* 生词标记非关键路径 */
  }
}

/* ---------- 划词批注（useReaderAnnotations：句内划选 → 高亮/笔记） ---------- */
const annotationsApi = useReaderAnnotations(chapterId, () => chapter.value, scrollToSentence)
const annotations = annotationsApi.annotations
const annSheet = annotationsApi.annSheet
const annListOpen = annotationsApi.annListOpen

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

function jumpToAnnotation(a: AnnotationItem) {
  annotationsApi.jump(a)
}

async function refreshAnnotations() {
  await annotationsApi.refresh()
}

/* ---------- 渲染（词块/批注标记/点词） ---------- */
const currentIdx = computed(() => ttsCurrentIdx.value)

function sentencePieces(idx: number) {
  const s = chapter.value?.sentences[idx]
  return s ? splitPieceWords(s.text) : []
}

function sentenceHasAnnotation(sentenceStart: number, sentenceEnd: number): boolean {
  return annotations.value.some(
    (a) => a.kind === 'highlight' && a.start_offset >= sentenceStart && a.start_offset < sentenceEnd,
  )
}

function onReaderClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  const wordEl = target.closest('.u-rd__run.is-word') as HTMLElement | null
  if (wordEl) {
    const word = wordEl.dataset.word ?? ''
    const sentenceEl = wordEl.closest('.u-rd__sentence') as HTMLElement | null
    const idx = Number(sentenceEl?.dataset.idx ?? -1)
    const context = chapter.value?.sentences[idx]?.text ?? ''
    void wordLookup.openFor(word, context)
    return
  }
  const sentenceEl = target.closest('.u-rd__sentence') as HTMLElement | null
  if (sentenceEl && ttsState.value !== 'idle') {
    const idx = Number(sentenceEl.dataset.idx ?? -1)
    if (idx >= 0 && idx !== ttsCurrentIdx.value) void tts.playFrom(idx)
  }
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
            :class="{ 'is-current': currentIdx === s.idx, 'is-annotated': sentenceHasAnnotation(s.start, s.end) }"
            :data-idx="s.idx"
          >
            <span
              v-for="(piece, wi) in sentencePieces(s.idx)"
              :key="wi"
              class="u-rd__run"
              :class="{ 'is-word': !!piece.word && vocabWords.has(piece.word.toLowerCase()) }"
              :data-word="piece.word ?? undefined"
            >{{ piece.text }}</span>
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
        @close="wordLookup.close()"
        @add-vocab="addWordToVocab"
        @play-word="void 0"
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
        @jump="jumpToAnnotation"
        @update:open="annListOpen = $event"
      />
      <MobileReaderTocSheet :open="tocOpen" @update:open="tocOpen = $event" @close="tocOpen = false" />
    </template>
  </div>
</template>
