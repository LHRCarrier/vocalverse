<script setup lang="ts">
/**
 * 酒馆场景卡抽屉（docs/52 §12.1）：
 * - 列表 = 我的卡（可改名/改场景/改开场、删除）+ 平台固定卡（只读，管理端上架）；
 * - 按关键词生成：LLM 起草 → 预览（标题/简介/开场）→ 保存为我的卡 / 重新生成；
 * - 手动新建：标题 + 起始场景 + 开场叙述；
 * - 开局：任一张卡「用这张开局」（含我的卡与平台卡）。
 */
import { ref } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { TrpgCard, TrpgCardUpsert } from '@/api/trpg'

const props = withDefaults(
  defineProps<{
    open: boolean
    cards: TrpgCard[]
    loading?: boolean
    generating?: boolean
    draft?: TrpgCardUpsert | null
    error?: string | null
    /** 当前 DM 语言（生成卡片时跟随；只读展示） */
    lang?: 'zh' | 'en'
  }>(),
  { loading: false, generating: false, draft: null, error: null, lang: 'zh' },
)

const emit = defineEmits<{
  close: []
  start: [cardId: number]
  generate: [keywords: string]
  'save-draft': []
  'clear-draft': []
  create: [payload: { title: string; scene: string; opening_line: string }]
  update: [cardId: number, payload: TrpgCardUpsert]
  remove: [cardId: number]
}>()

type Mode = 'list' | 'generate' | 'manual' | 'edit'
const mode = ref<Mode>('list')
const keywords = ref('')
const manual = ref({ title: '', scene: '', opening_line: '' })
const editing = ref<TrpgCard | null>(null)
const editForm = ref({ title: '', scene: '', opening_line: '' })

function openGenerate() {
  mode.value = 'generate'
  keywords.value = ''
}

function openManual() {
  mode.value = 'manual'
  manual.value = { title: '', scene: '', opening_line: '' }
}

function openEdit(card: TrpgCard) {
  mode.value = 'edit'
  editing.value = card
  editForm.value = {
    title: card.title,
    scene: card.scene ?? '',
    opening_line: card.opening_line ?? '',
  }
}

function back() {
  mode.value = 'list'
}

function submitManual() {
  if (!manual.value.title.trim()) return
  emit('create', { ...manual.value })
}

function submitEdit() {
  if (!editing.value || !editForm.value.title.trim()) return
  emit('update', editing.value.id, {
    title: editForm.value.title.trim(),
    scene: editForm.value.scene.trim(),
    opening_line: editForm.value.opening_line,
  })
  mode.value = 'list'
}
</script>

<template>
  <div v-if="props.open" class="t-sheet">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-sheet__panel" role="dialog" aria-label="场景卡">
      <header class="t-sheet__head">
        <div>
          <div class="t-sheet__title">场景卡</div>
          <div class="t-sheet__sub">选一张开局，或让 AI 按你的关键词现写一张</div>
        </div>
        <button
          class="t-sheet__close"
          type="button"
          title="关闭"
          aria-label="关闭"
          @click="emit('close')"
        >
          <MobileIcon name="x" :size="18" />
        </button>
      </header>

      <div class="t-sheet__body">
        <p v-if="props.error" class="u-error">{{ props.error }}</p>

        <!-- 列表 -->
        <template v-if="mode === 'list'">
          <div class="t-card-actions">
            <button class="u-btn u-btn--primary u-btn--sm" type="button" @click="openGenerate">
              ✨ 按关键词生成
            </button>
            <button class="u-btn u-btn--secondary u-btn--sm" type="button" @click="openManual">
              手动新建
            </button>
          </div>

          <div v-if="props.loading" class="t-sheet__text">加载中…</div>

          <template
            v-for="group in [
              { key: 'mine', label: '我的场景卡', items: props.cards.filter((c) => c.source === 'user') },
              { key: 'platform', label: '精选场景卡', items: props.cards.filter((c) => c.source === 'admin') },
            ]" :key="group.key"
          >
            <div v-if="group.items.length" class="t-sheet__label">{{ group.label }}</div>
            <article v-for="card in group.items" :key="card.id" class="t-card-item">
              <div class="t-card-item__main">
                <div class="t-card-item__title">
                  {{ card.title }}
                  <span v-if="card.generated_by === 'llm'" class="t-chip t-chip--warn">AI</span>
                </div>
                <div class="t-card-item__sub">
                  {{ card.scene || '未定场景' }}<template v-if="card.summary"> · {{ card.summary }}</template>
                </div>
              </div>
              <div class="t-card-item__ops">
                <button
                  class="u-btn u-btn--primary u-btn--sm"
                  type="button"
                  @click="emit('start', card.id)"
                >
                  开局
                </button>
                <template v-if="card.source === 'user'">
                  <button
                    class="t-fact__ops-btn"
                    type="button"
                    title="编辑"
                    aria-label="编辑"
                    @click="openEdit(card)"
                  >
                    <MobileIcon name="pencil" :size="16" />
                  </button>
                  <button
                    class="t-fact__ops-btn"
                    type="button"
                    title="删除"
                    aria-label="删除"
                    @click="emit('remove', card.id)"
                  >
                    <MobileIcon name="trash" :size="16" />
                  </button>
                </template>
              </div>
            </article>
          </template>

          <div v-if="!props.loading && !props.cards.length" class="t-sheet__text">
            还没有场景卡：点「按关键词生成」，或让管理端上架精选卡。
          </div>
        </template>

        <!-- 生成 -->
        <template v-else-if="mode === 'generate'">
          <div class="t-sheet__label">你想玩什么？（1-200 字，逗号分隔即可）</div>
          <input
            v-model="keywords"
            class="text-input"
            placeholder="如：海盗、灯塔、幽灵船"
            aria-label="场景关键词"
            maxlength="200"
          >
          <button
            class="u-btn u-btn--primary u-btn--block"
            type="button"
            :disabled="!keywords.trim() || props.generating"
            @click="emit('generate', keywords.trim())"
          >
            {{ props.generating ? '生成中…' : '生成卡片' }}
          </button>

          <template v-if="props.draft">
            <div class="t-sheet__label">预览（可保存后编辑）</div>
            <div class="t-card-item t-card-item--preview">
              <div class="t-card-item__title">{{ props.draft.title }}</div>
              <div class="t-card-item__sub">
                {{ props.draft.scene || '未定场景' }}
                <template v-if="props.draft.summary"> · {{ props.draft.summary }}</template>
              </div>
              <p class="t-sheet__text">{{ props.draft.opening_line }}</p>
            </div>
            <div class="t-card-actions">
              <button class="u-btn u-btn--primary u-btn--sm" type="button" @click="emit('save-draft')">
                保存并开局
              </button>
              <button class="u-btn u-btn--secondary u-btn--sm" type="button" @click="emit('clear-draft')">
                重新生成
              </button>
            </div>
          </template>

          <button class="u-btn u-btn--outline u-btn--block" type="button" @click="back">返回列表</button>
        </template>

        <!-- 手动新建 -->
        <template v-else-if="mode === 'manual'">
          <div class="t-sheet__label">新建场景卡</div>
          <input v-model="manual.title" class="text-input" placeholder="标题（必填，如：雨夜驿站）" aria-label="卡片标题" maxlength="60">
          <input v-model="manual.scene" class="text-input" placeholder="起始场景（如：驿站大堂）" aria-label="起始场景" maxlength="40">
          <textarea
            v-model="manual.opening_line"
            class="text-input t-textarea"
            placeholder="开场叙述（DM 的第一条消息，可空）"
            aria-label="开场叙述"
            maxlength="600"
          />
          <div class="t-card-actions">
            <button
              class="u-btn u-btn--primary u-btn--sm"
              type="button"
              :disabled="!manual.title.trim()"
              @click="submitManual"
            >
              保存
            </button>
            <button class="u-btn u-btn--secondary u-btn--sm" type="button" @click="back">返回</button>
          </div>
        </template>

        <!-- 编辑我的卡 -->
        <template v-else>
          <div class="t-sheet__label">编辑「{{ editing?.title }}」</div>
          <input v-model="editForm.title" class="text-input" placeholder="标题" aria-label="编辑标题" maxlength="60">
          <input v-model="editForm.scene" class="text-input" placeholder="起始场景" aria-label="编辑场景" maxlength="40">
          <textarea
            v-model="editForm.opening_line"
            class="text-input t-textarea"
            placeholder="开场叙述"
            aria-label="编辑开场叙述"
            maxlength="600"
          />
          <div class="t-card-actions">
            <button
              class="u-btn u-btn--primary u-btn--sm"
              type="button"
              :disabled="!editForm.title.trim()"
              @click="submitEdit"
            >
              保存修改
            </button>
            <button class="u-btn u-btn--secondary u-btn--sm" type="button" @click="back">返回</button>
          </div>
        </template>
      </div>
    </section>
  </div>
</template>
