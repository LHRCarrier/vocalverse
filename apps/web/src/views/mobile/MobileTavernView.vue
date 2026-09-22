<script setup lang="ts">
/**
 * 移动端 · 酒馆（TRPG 跑团）——ai4u 酒馆模块迁移版（docs/52）
 *
 * 玩法闭环：场景卡开局 → 打字/语音说行动 → DM 流式叙述（逐句 TTS）→ 系统卡 → 主持台抽屉。
 * 2026-09-22 设计稿改版 + docs/57 §3.2「状态搬进玩家视线」：
 * - 大钟条/在场条不再常驻正文流，改迷你状态条（dock 上方一行，点开才展开完整条）；
 * - 动作面板常驻且与 dock 推荐行动合并为一排；流式节流跟随 + turn_end 兜底滚底；
 * - 钟满可「收尾本幕」（确定性结算接口）+ 已完结条「开新篇章」；实时 ending 事件兜底渲染。
 * 立绘/属性为占位（docs/54 规划），语音链路（ASR + 逐句 TTS + 卡拉OK）保留。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useTavernDock } from '@/composables/useTavernDock'
import { useTavernCardFlow } from '@/composables/useTavernCardFlow'
import { useTavernScrollFollow } from '@/composables/useTavernScroll'
import { useTavernStandee } from '@/composables/useTavernStandee'
import { useTavernSuggestions } from '@/composables/useTavernSuggestions'
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
const avatarLetter = computed(() => (auth.me?.nickname ?? auth.me?.username ?? '我').slice(0, 1).toUpperCase())
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
  updateCardFields,
  removeCard,
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
const pickerOpen = ref(false)
const settingsOpen = ref(false)
const cardsOpen = ref(false)

/* ---- 场景卡流程 / 立绘展台（实现拆在对应 composable，docs/57 §3.2） ---- */
const cardFlow = useTavernCardFlow({
  cards: tavernCards,
  refreshCampaigns: session.refreshCampaigns,
  selectCampaign: session.selectCampaign,
  open: () => { cardsOpen.value = true },
  close: () => { cardsOpen.value = false },
})
const standee = useTavernStandee({
  portrait: session.portrait,
  dismissPortrait: session.dismissPortrait,
  toast: (message) => ui.showToast(message),
  roll: session.onRoll,
})
/** 展台开合/聚焦 ref 提为顶层绑定（模板里自动解包；对象上的方法仍走 standee.*） */
const { open: standeeOpen, hero: standeeHero, npc: standeeNpc } = standee

/* ---- 闭环领域数据（docs/56 §6：useTavernSession 暴露的三个域 composable） ---- */
const { quests: questClocks, activeQuests, ending } = session.quest
const { members: castMembers, present: castPresent, arriving: castArriving } = session.cast
const { encounter: activeEncounter, participants: encounterParticipants, attackTargets, items: usableItems } = session.encounter

/** 动态推荐行动（docs/57 §3.2）：场景/在场/任务变化即刷新 */
const quickActions = useTavernSuggestions({
  scene: computed(() => state.value?.scene),
  present: computed(() => castPresent.value.map((m) => ({ name: m.name, kind: m.kind }))),
  quests: computed(() => {
    const clocks = activeQuests.value.map((q) => ({ name: q.name, status: q.status }))
    if (clocks.length) return clocks
    // 无进度钟时退化为卡片任务（旧剧本只有 tasks 表）
    return (state.value?.tasks ?? [])
      .filter((t) => t.status === 'active')
      .map((t) => ({ name: t.title, status: 'active' }))
  }),
  encounter: computed(() => activeEncounter.value),
})

/** 满格可收尾任务（已完结后不再出现收尾钮；攻击 chip 的遭遇门控在 TrpgBottomBar） */
const settleableQuests = computed(() => (session.finished.value ? [] : activeQuests.value.filter((q) => q.full)))

/** 副本任务卡「目标」行：全部 active 任务用 ` / ` 连接（对原型 mission-deck 的目标行） */
const goalText = computed(
  () => state.value?.tasks.filter((t) => t.status === 'active').map((t) => t.title).join(' / ') || null,
)
const clueCount = computed(() => state.value?.clues.length ?? 0)

watch(campaignId, (id) => { marks.load(id); translations.clear() }, { immediate: true })

/* ---- 流式跟随滚动 + dock 状态（docs/57 §3.2；实现分别拆在对应 composable） ---- */
const scrollFollow = useTavernScrollFollow({
  rows,
  turnEndAt: session.turnEndAt,
  ending,
})
const { stripExpanded, dockPrefill, consoleOpen, consoleTab, toggleStrip, onPrefill, openConsole, onSettle } =
  useTavernDock({
    settle: session.settleQuest,
    toast: (message) => ui.showToast(message),
    pinToBottom: () => scrollFollow.pinToBottom(),
  })

onMounted(() => { void session.boot(); void loadPrefs(); void loadCards() })

onUnmounted(() => session.dispose())

/** 用户发送（dock/动作面板）→ 重新吸附跟随 */
function onSend(text: string) { scrollFollow.reengage(); session.sendText(text) }

async function onSwitch(id: number) { pickerOpen.value = false; await session.switchCampaign(id) }

async function onRestart() { pickerOpen.value = false; await session.restartCampaign() }

/* ---- 设置 ---- */
async function onPrefsUpdate(patch: Parameters<typeof savePrefs>[0]) {
  if (patch.voice_enabled === false) audio.flush() // 关语音即时静音（服务端随后不再合成）
  await savePrefs(patch)
}</script>

<template>
  <div
    class="u-phone t-page"
    :class="{ 't-page--play': stage === 'play', 't-page--bars': stage === 'play' && stripExpanded }"
  >
    <div
      class="v-line"
      :class="`v-line--${status}`"
      role="status"
      :aria-label="status === 'busy' ? 'DM 处理中' : status === 'error' ? '出错了' : '空闲'"
    />
    <TrpgTopBar
      :stage="stage"
      @leave="router.push('/m/learn')"
      @standee="standee.openStandee('dm')"
      @settings="settingsOpen = true"
      @cards="cardFlow.openCards"
      @picker="pickerOpen = true"
      @console="openConsole('state')"
    />

    <div class="u-content u-content--dock">
      <TrpgOnboarding
        v-if="stage === 'onboarding'"
        :has-cards="cardList.length > 0"
        @open-cards="cardFlow.openCards"
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

        <!-- 大钟条/在场条默认不占正文流（迷你状态条展开时才在 dock 上方出现） -->
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
            @standee="standee.openStandee($event === 'user' ? 'pc' : 'dm')"
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

    <!-- 底部控制区：已完结条 / 展开钟条 / 动作面板 / 迷你状态条 / 输入 dock / 页内导航 -->
    <TrpgBottomBar
      v-if="stage === 'play'"
      :sending="sending"
      :recording="recording"
      :prefill="dockPrefill"
      :finished="session.finished.value"
      :strip-expanded="stripExpanded"
      :quests="questClocks"
      :cast-members="castMembers"
      :present-count="castPresent.length"
      :arriving-count="castArriving.length"
      :clue-count="clueCount"
      :attack-targets="attackTargets"
      :items="usableItems"
      :quick-actions="quickActions"
      :encounter="activeEncounter"
      :participants="encounterParticipants"
      :settleable="settleableQuests"
      :settling="session.settling.value"
      :disabled="sending"
      @send="onSend"
      @toggle-mic="session.toggleMic"
      @roll="session.onRoll({ dice: 'd20' })"
      @prefill="onPrefill"
      @feedback="ui.showToast($event)"
      @settle="onSettle"
      @toggle-strip="toggleStrip"
      @open-console="openConsole"
      @cast-select="standee.onCastSelect"
      @new-chapter="pickerOpen = true"
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
      :initial-tab="consoleTab"
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
      @start="cardFlow.onStartCard"
      @generate="generateFromKeywords"
      @save-draft="cardFlow.onSaveDraftAndStart"
      @clear-draft="clearDraft"
      @create="cardFlow.onCreateCard"
      @update="updateCardFields"
      @remove="removeCard"
    />

    <TrpgCampaignPicker
      :open="pickerOpen"
      :campaigns="campaigns"
      :current-id="campaignId"
      @close="pickerOpen = false"
      @switch="onSwitch"
      @new-campaign="pickerOpen = false; cardFlow.openCards()"
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
      :npcs="[...npcNames]"
      :initial-hero="standeeHero"
      :npc="standeeNpc"
      :status="standeeNpc?.status ?? null"
      @close="standeeOpen = false"
      @roll="standee.onRoll"
    />
  </div>
</template>
