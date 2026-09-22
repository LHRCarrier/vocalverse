<script setup lang="ts">
/**
 * 移动端 · 酒馆（TRPG 跑团）——ai4u 酒馆模块迁移版（docs/52）
 *
 * 玩法闭环：场景卡开局 → 打字/语音说行动 → DM 流式叙述（逐句 TTS）→ 系统卡 → 主持台抽屉。
 * 2026-09-22 按设计稿（local/trpg-redesign.html）改版：副本任务卡 + 立绘抽屉 + 页内底栏
 * （大堂/酒馆跑团/角色卡/纪事）→ **沉浸页**（全局底栏移出）；出口 = 顶栏「离开」→ /m/learn。
 * 立绘/属性为占位（docs/54 规划），语音链路（ASR + 逐句 TTS + 卡拉OK）保留。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useTavernAudio } from '@/composables/useTavernAudio'
import { useTavernCards } from '@/composables/useTavernCards'
import { useTavernMarks } from '@/composables/useTavernMarks'
import { useTavernMessageActions } from '@/composables/useTavernMessageActions'
import { useTavernTranslations } from '@/composables/useTavernTranslations'
import { useTavernSession } from '@/composables/useTavernSession'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

import MobileArt from '@/components/mobile/MobileArt.vue'
import TrpgBottomBar from '@/components/mobile/trpg/TrpgBottomBar.vue'
import TrpgCampaignPicker from '@/components/mobile/trpg/TrpgCampaignPicker.vue'
import TrpgCardSheet from '@/components/mobile/trpg/TrpgCardSheet.vue'
import TrpgConsoleSheet from '@/components/mobile/trpg/TrpgConsoleSheet.vue'
import TrpgMessageActions from '@/components/mobile/trpg/TrpgMessageActions.vue'
import TrpgMessageItem from '@/components/mobile/trpg/TrpgMessageItem.vue'
import TrpgOnboarding from '@/components/mobile/trpg/TrpgOnboarding.vue'
import TrpgSettingsSheet from '@/components/mobile/trpg/TrpgSettingsSheet.vue'
import TrpgStageHeader from '@/components/mobile/trpg/TrpgStageHeader.vue'
import TrpgStandeeSheet from '@/components/mobile/trpg/TrpgStandeeSheet.vue'
import TrpgTopBar from '@/components/mobile/trpg/TrpgTopBar.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()
const auth = useAuthStore()
const ui = useUiStore()
const avatarLetter = computed(() =>
  (auth.me?.nickname ?? auth.me?.username ?? '我').slice(0, 1).toUpperCase(),
)
const pcName = computed(() => auth.me?.nickname ?? auth.me?.username ?? '冒险者')

const audio = useTavernAudio()
const session = useTavernSession(audio)
const tavernCards = useTavernCards()
const {
  cards: cardList,
  cardsLoading,
  prefs,
  prefsSaving,
  generating: cardGenerating,
  draft: cardDraft,
  error: cardError,
  loadCards,
  loadPrefs,
  savePrefs,
  generateFromKeywords,
  saveDraft,
  createManual,
  updateCardFields,
  removeCard,
  startFromCard,
  clearDraft,
} = tavernCards
const {
  stage,
  campaigns,
  state,
  campaignId,
  rows,
  inputError,
  bootError,
  sending,
  recording,
  statusHint,
  status,
  hp,
  location,
  inventory,
  activeTasks,
  danglingCount,
  npcNames,
} = session

const marks = useTavernMarks()
const translations = useTavernTranslations()
const msgActions = useTavernMessageActions(rows, audio, marks, translations)
const consoleOpen = ref(false)
const pickerOpen = ref(false)
const settingsOpen = ref(false)
const cardsOpen = ref(false)
const standeeOpen = ref(false)
const standeeHero = ref<'dm' | 'pc'>('dm')

/** 副本任务卡「目标」行：全部 active 任务用 ` / ` 连接（对原型 mission-deck 的目标行） */
const goalText = computed(() => {
  const titles = state.value?.tasks.filter((t) => t.status === 'active').map((t) => t.title) ?? []
  return titles.length ? titles.join(' / ') : null
})
const clueCount = computed(() => state.value?.clues.length ?? 0)
const npcList = computed(
  () => state.value?.entities.filter((e) => e.kind === 'npc').map((e) => e.name) ?? [],
)

watch(campaignId, (id) => { marks.load(id); translations.clear() }, { immediate: true })

onMounted(() => {
  void session.boot()
  void loadPrefs()
  void loadCards()
})

onUnmounted(() => {
  session.dispose()
})

/** 会话滚到底：滚动容器是 window（.u-phone 为文档流，不是内部 scrollport）；
 *  此前对 .t-log 调 scrollTo 无效 → 新消息会被固定 dock 压住（2026-09-22 实测修复）。 */
function scrollToLatest(smooth = true) {
  window.scrollTo({
    top: document.documentElement.scrollHeight,
    behavior: smooth ? 'smooth' : 'auto',
  })
}

watch(
  () => rows.value.length,
  async () => {
    await nextTick()
    scrollToLatest(false)
  },
)

async function onSwitch(id: number) {
  pickerOpen.value = false
  await session.switchCampaign(id)
}

async function onRestart() {
  pickerOpen.value = false
  await session.restartCampaign()
}

/* ---- 设置 ---- */
async function onPrefsUpdate(patch: Parameters<typeof savePrefs>[0]) {
  if (patch.voice_enabled === false) audio.flush() // 关语音即时静音（服务端随后不再合成）
  await savePrefs(patch)
}

/* ---- 场景卡 ---- */
function openCards() {
  cardsOpen.value = true
  void loadCards()
}

async function onStartCard(id: number) {
  const newCampaignId = await startFromCard(id)
  if (newCampaignId == null) return
  cardsOpen.value = false
  await session.refreshCampaigns()
  await session.selectCampaign(newCampaignId)
}

async function onSaveDraftAndStart() {
  const card = await saveDraft()
  if (card) await onStartCard(card.id)
}

async function onCreateCard(payload: { title: string; scene: string; opening_line: string }) {
  const card = await createManual(payload)
  if (card) await onStartCard(card.id)
}

/* ---- 角色立绘 / 属性检定 ---- */
function openStandee(hero: 'dm' | 'pc') {
  standeeHero.value = hero
  standeeOpen.value = true
}

/** 立绘抽屉「属性检定」→ 现有 D20 桌骰（真实请求；属性系统为占位，见组件注释） */
function onStandeeRoll() {
  standeeOpen.value = false
  ui.showToast('🎲 检定已触发')
  void session.onRoll({ dice: 'd20' })
}
</script>

<template>
  <div class="u-phone t-page">
    <div
      class="v-line"
      :class="`v-line--${status}`"
      role="status"
      :aria-label="status === 'busy' ? 'DM 处理中' : status === 'error' ? '出错了' : '空闲'"
    />
    <TrpgTopBar
      :stage="stage"
      @leave="router.push('/m/learn')"
      @standee="openStandee('dm')"
      @settings="settingsOpen = true"
      @cards="openCards"
      @picker="pickerOpen = true"
      @console="consoleOpen = true"
    />

    <div class="u-content u-content--dock">
      <TrpgOnboarding
        v-if="stage === 'onboarding'"
        :has-cards="cardList.length > 0"
        @open-cards="openCards"
        @demo="session.startDemo"
        @create="session.startCustom"
      />

      <div
        v-else-if="stage === 'loading'"
        class="u-empty u-empty--center"
        role="status"
        aria-label="正在进入酒馆"
      >
        <div class="u-empty__art"><MobileArt name="wave" :size="96" /></div>
      </div>

      <section v-else-if="stage === 'error'" class="u-empty">
        <div class="u-empty__art"><MobileArt name="mic" :size="96" /></div>
        <div class="u-empty__title">无法进入酒馆</div>
        <div class="u-empty__sub">{{ bootError }}</div>
        <div class="u-done__actions" style="width: 100%; max-width: 280px">
          <button class="u-btn u-btn--primary u-btn--block" type="button" @click="session.boot">
            重试
          </button>
          <RouterLink to="/m/home" class="u-btn u-btn--secondary u-btn--block">回到首页</RouterLink>
        </div>
      </section>

      <template v-else>
        <TrpgStageHeader
          :campaign-name="state?.campaign.name ?? ''"
          :scene="state?.scene"
          :hp="hp"
          :location="location"
          :inventory="inventory"
          :active-tasks="activeTasks"
          :dangling-count="danglingCount"
          :goal="goalText"
          :status="status"
        />

        <div class="t-log">
          <TrpgMessageItem
            v-for="(m, i) in rows"
            :key="i"
            :role="m.role"
            :kind="m.kind"
            :content="m.content"
            :payload="m.payload"
            :live="m.live"
            :npc-names="npcNames"
            :avatar-letter="avatarLetter"
            :avatar-url="auth.me?.avatarUrl"
            :user-name="pcName"
            :marked="marks.has(m.content)"
            :active="msgActions.actionIndex.value === i"
            :translation="translations.stateFor(i)"
            :highlight="msgActions.highlightFor(i)"
            @actions="msgActions.open(i)"
            @translate="translations.toggle(i, m.content)"
            @standee="openStandee($event === 'user' ? 'pc' : 'dm')"
          />
          <div v-if="rows.length === 0" class="u-empty u-empty--center">
            <div class="u-empty__art"><MobileArt name="wave" :size="96" /></div>
            <div class="u-empty__sub">说一句话，DM 会接住你</div>
          </div>
          <div v-if="statusHint" class="t-status" role="status">{{ statusHint }}</div>
          <div v-if="inputError" class="u-error">{{ inputError }}</div>
        </div>
      </template>
    </div>

    <!-- 底部控制区：dock（推荐行动/骰钮/语音/发送）+ 页内 4 项导航（设计稿 dock + bottom-nav） -->
    <TrpgBottomBar
      v-if="stage === 'play'"
      :sending="sending"
      :recording="recording"
      @send="session.sendText"
      @toggle-mic="session.toggleMic"
      @roll="session.onRoll({ dice: 'd20' })"
    />

    <TrpgConsoleSheet
      v-if="state"
      :open="consoleOpen"
      :campaign-name="state.campaign.name"
      :scene="state.scene"
      :snapshot="state.snapshot"
      :narrative-summary="state.narrative_summary"
      :facts="state.facts"
      :tasks="state.tasks"
      :clues="state.clues"
      :events="state.events"
      :dangling="state.verify?.dangling ?? []"
      @close="consoleOpen = false"
      @edit-fact="session.onEditFact"
      @delete-fact="session.onDeleteFact"
      @create-task="session.onCreateTask"
      @set-task-status="session.onSetTaskStatus"
      @create-clue="session.onCreateClue"
      @recover-clue="session.onRecoverClue"
      @set-scene="session.onSetScene"
      @roll="session.onRoll"
      @refresh-narrative="session.onRefreshNarrative"
    />

    <TrpgMessageActions
      :open="msgActions.actionIndex.value != null"
      :role="msgActions.actionRow.value?.role ?? 'assistant'"
      :preview="msgActions.preview.value"
      :marked="msgActions.actionRow.value ? marks.has(msgActions.actionRow.value.content) : false"
      :translated="msgActions.translated.value"
      :playing="msgActions.actionIndex.value != null && audio.playingIndex.value === msgActions.actionIndex.value"
      :speakable="
        !!msgActions.actionRow.value &&
          msgActions.actionRow.value.kind !== 'system' &&
          !!msgActions.actionRow.value.content.trim()
      "
      @close="msgActions.close"
      @listen="msgActions.listen"
      @translate="msgActions.translate"
      @toggle-mark="msgActions.toggleMark"
      @copy="msgActions.copy"
    />

    <TrpgSettingsSheet
      :open="settingsOpen"
      :prefs="prefs"
      :saving="prefsSaving"
      @close="settingsOpen = false"
      @update="onPrefsUpdate"
    />

    <TrpgCardSheet
      :open="cardsOpen"
      :cards="cardList"
      :loading="cardsLoading"
      :generating="cardGenerating"
      :draft="cardDraft"
      :error="cardError"
      :lang="prefs.lang"
      @close="cardsOpen = false"
      @start="onStartCard"
      @generate="generateFromKeywords"
      @save-draft="onSaveDraftAndStart"
      @clear-draft="clearDraft"
      @create="onCreateCard"
      @update="updateCardFields"
      @remove="removeCard"
    />

    <TrpgCampaignPicker
      :open="pickerOpen"
      :campaigns="campaigns"
      :current-id="campaignId"
      @close="pickerOpen = false"
      @switch="onSwitch"
      @new-campaign="pickerOpen = false; openCards()"
      @restart="onRestart"
    />

    <!-- 角色立绘 / 档案展台（设计稿 standee-sheet；立绘与属性为占位，docs/54） -->
    <TrpgStandeeSheet
      v-if="state"
      :open="standeeOpen"
      :campaign-name="state.campaign.name"
      :scene="state.scene"
      :pc-name="pcName"
      :tasks="activeTasks"
      :clues="clueCount"
      :facts="state.facts"
      :npcs="npcList"
      :initial-hero="standeeHero"
      @close="standeeOpen = false"
      @roll="onStandeeRoll"
    />
  </div>
</template>
