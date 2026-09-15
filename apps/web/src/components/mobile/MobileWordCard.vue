<script setup lang="ts">
/**
 * 移动端 · 查词卡（docs/45 §6 · UI 拷问裁定：底部 sheet，非词旁 popover）。
 * 内容序：词头+音标 → 中文释义（首义多行）→ 英文释义 → 词频/词形 → CTA（加入生词本）+ 读音 + 外链。
 */
import MobileIcon from './MobileIcon.vue'
import type { WordLookupResult } from '@/api/reading'

const props = defineProps<{
  result: WordLookupResult | null
  loading?: boolean
  /** 查词未收录（45003）时的降级展示 */
  missing?: boolean
  /** 该词所在句子 idx（2026-09-10：句子级批注入口——空格只有 4.6px 宽，点句命中不可靠，改由卡片提供） */
  sentenceIndex?: number | null
}>()

const emit = defineEmits<{
  close: []
  'add-vocab': []
  'play-word': []
  'sentence-highlight': []
  'sentence-note': []
}>()

function firstMeaning(translation: string | null | undefined): string {
  if (!translation) return ''
  return translation
    .split('\n')
    .map((s) => s.trim())
    .filter((s) => s && !s.startsWith('['))
    .slice(0, 3)
    .join('\n')
}

function firstDefinition(definition: string | null | undefined): string {
  if (!definition) return ''
  return definition.split('\n').map((s) => s.trim()).filter(Boolean).slice(0, 2).join('\n')
}

/** exchange（词形）→ 中文标签 */
const FORM_LABEL: Record<string, string> = {
  p: '过去式',
  d: '过去分词',
  i: '现在分词',
  '3': '三单',
  r: '比较级',
  t: '最高级',
  s: '复数',
}

function formText(exchange: Record<string, string> | null | undefined): string {
  if (!exchange) return ''
  return Object.entries(exchange)
    .map(([k, v]) => `${FORM_LABEL[k] ?? k}: ${v}`)
    .join(' · ')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="props.loading" class="u-sheet-mask">
      <div class="u-sheet u-rd-word">
        <p class="u-rd-word__definition">查词中…</p>
      </div>
    </div>
    <div v-else-if="props.missing" class="u-sheet-mask">
      <div class="u-sheet u-rd-word">
        <p class="u-rd-word__word">暂无释义</p>
        <p class="u-rd-word__definition">
          词典暂未收录该词。试试去在线词典查看，或直接加入生词本稍后复习。
        </p>
        <div class="u-rd-word__actions">
          <button class="u-btn u-btn--primary" type="button" @click="emit('add-vocab')">加入生词本</button>
          <button class="u-btn" type="button" @click="emit('close')">关闭</button>
        </div>
        <div v-if="props.sentenceIndex != null" class="u-rd-word__sentence">
          <span class="u-rd-word__sentence-label">这一句</span>
          <button class="u-btn u-btn--secondary" type="button" @click="emit('sentence-highlight')">高亮这句</button>
          <button class="u-btn u-btn--secondary" type="button" @click="emit('sentence-note')">批注这句</button>
        </div>
      </div>
    </div>
    <div v-else-if="props.result" class="u-sheet-mask">
      <div class="u-sheet u-rd-word">
        <header class="u-sheet__head">
          <h2 class="u-sheet__title">释义</h2>
          <button class="u-sheet__close" type="button" aria-label="关闭" @click="emit('close')">
            <MobileIcon name="x" :size="18" />
          </button>
        </header>

        <div class="u-rd-word__head">
          <span class="u-rd-word__word">{{ props.result.word }}</span>
          <span class="u-rd-word__phonetic">{{ props.result.phonetic ?? '' }}</span>
          <div class="u-rd-word__head-actions">
            <button class="u-btn u-btn--icon" type="button" title="朗读" aria-label="朗读" @click="emit('play-word')">
              <MobileIcon name="volume" :size="18" />
            </button>
          </div>
        </div>

        <p class="u-rd-word__meaning">{{ firstMeaning(props.result.translation) }}</p>
        <p v-if="firstDefinition(props.result.definition)" class="u-rd-word__definition">
          {{ firstDefinition(props.result.definition) }}
        </p>
        <p v-if="formText(props.result.exchange)" class="u-rd-word__definition">
          词形：{{ formText(props.result.exchange) }}
        </p>

        <div class="u-rd-word__meta">
          <span v-if="props.result.frequency" class="u-bd__badge">词频 #{{ props.result.frequency }}</span>
          <span v-if="props.result.pos" class="u-bd__badge">{{ props.result.pos }}</span>
          <span v-if="props.result.matched !== props.result.word" class="u-bd__badge">
            词形 {{ props.result.matched }}
          </span>
        </div>

        <div class="u-rd-word__actions">
          <button
            v-if="!props.result.in_vocab"
            class="u-btn u-btn--primary"
            type="button"
            @click="emit('add-vocab')"
          >
            加入生词本
          </button>
          <button v-else class="u-btn" type="button" disabled>
            ★ 已在生词本
          </button>
          <a
            class="u-btn"
            :href="`https://cn.bing.com/dict/search?q=${encodeURIComponent(props.result.word)}`"
            target="_blank"
            rel="noopener noreferrer"
          >
            更多释义
          </a>
        </div>

        <!-- 句子级动作（作用于该词所在句子；命中区 = 按钮，不依赖点中空格） -->
        <div v-if="props.sentenceIndex != null" class="u-rd-word__sentence">
          <span class="u-rd-word__sentence-label">这一句</span>
          <!-- .u-btn--ghost 是深色卡专用（白字透明底）→ 白卡上文字为白不可见，改用浅色卡次级按钮 -->
          <button class="u-btn u-btn--secondary" type="button" @click="emit('sentence-highlight')">高亮这句</button>
          <button class="u-btn u-btn--secondary" type="button" @click="emit('sentence-note')">批注这句</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.u-btn--icon {
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: 50%;
}
</style>
