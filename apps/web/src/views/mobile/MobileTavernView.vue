<script setup lang="ts">
/**
 * 移动端 · 酒馆（TRPG 跑团）——ai4u 酒馆模块迁移版（docs/52）
 *
 * 玩法闭环：选/建剧本 → 打字或语音说行动 → DM 流式叙述（服务端逐句 TTS 排队播放）
 * → 系统卡（开场/过场/判定）→ 主持台抽屉（状态/事实表/任务线索/桌骰）。
 * 状态全在服务端（campaign 事实表）；本页只做渲染与动作转发（编排见 useTavernSession）。
 */
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { useTavernAudio } from '@/composables/useTavernAudio'
import { useTavernSession } from '@/composables/useTavernSession'
import { useAuthStore } from '@/stores/auth'

import IconAdjustments from '~icons/tabler/adjustments'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import TrpgActionDock from '@/components/mobile/trpg/TrpgActionDock.vue'
import TrpgConsoleSheet from '@/components/mobile/trpg/TrpgConsoleSheet.vue'
import TrpgMessageItem from '@/components/mobile/trpg/TrpgMessageItem.vue'
import TrpgOnboarding from '@/components/mobile/trpg/TrpgOnboarding.vue'
import TrpgStageHeader from '@/components/mobile/trpg/TrpgStageHeader.vue'
import '@/styles/mobile-uic.css'

const router = useRouter()
const auth = useAuthStore()
const avatarLetter = computed(() =>
  (auth.me?.nickname ?? auth.me?.username ?? '我').slice(0, 1).toUpperCase(),
)

const audio = useTavernAudio()
const session = useTavernSession(audio)
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

const consoleOpen = ref(false)
const pickerOpen = ref(false)
const scrollBox = ref<HTMLElement | null>(null)

onMounted(() => {
  void session.boot()
})

onUnmounted(() => {
  session.dispose()
})

watch(
  () => rows.value.length,
  async () => {
    await nextTick()
    scrollBox.value?.scrollTo({ top: scrollBox.value.scrollHeight })
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
</script>

<template>
  <div class="u-phone">
    <div
      class="v-line"
      :class="`v-line--${status}`"
      role="status"
      :aria-label="status === 'busy' ? 'DM 处理中' : status === 'error' ? '出错了' : '空闲'"
    />
    <MobileTopBar title="酒馆" back @back="router.push('/m/learn')">
      <template #actions>
        <button
          v-if="stage === 'play'"
          class="u-topbar__act"
          type="button"
          title="切换剧本"
          aria-label="切换剧本"
          @click="pickerOpen = true"
        >
          <MobileIcon name="book" :size="20" />
        </button>
        <button
          v-if="stage === 'play'"
          class="u-topbar__act"
          type="button"
          title="主持台"
          aria-label="主持台"
          @click="consoleOpen = true"
        >
          <IconAdjustments />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content u-content--dock">
      <TrpgOnboarding v-if="stage === 'onboarding'" @demo="session.startDemo" @create="session.startCustom" />

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
          :status="status"
        />

        <div ref="scrollBox" class="t-log">
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
            :speakable="m.speakable"
            :playing="audio.playingIndex.value === i"
            @replay="audio.replay(i, m.content)"
          />
          <div v-if="rows.length === 0" class="u-empty u-empty--center">
            <div class="u-empty__art"><MobileArt name="wave" :size="96" /></div>
            <div class="u-empty__sub">说一句话，DM 会接住你</div>
          </div>
          <div v-if="statusHint" class="t-status" role="status">{{ statusHint }}</div>
          <div v-if="inputError" class="u-error">{{ inputError }}</div>
        </div>

        <TrpgActionDock
          :sending="sending"
          :recording="recording"
          :max-seconds="30"
          @send="session.sendText"
          @toggle-mic="session.toggleMic"
        />
      </template>
    </div>

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

    <div v-if="pickerOpen" class="t-sheet">
      <div class="t-sheet__backdrop" role="presentation" @click="pickerOpen = false" />
      <section class="t-sheet__panel t-sheet__panel--short" role="dialog" aria-label="选择剧本">
        <header class="t-sheet__head">
          <div class="t-sheet__title">我的剧本</div>
          <button
            class="t-sheet__close"
            type="button"
            title="关闭"
            aria-label="关闭"
            @click="pickerOpen = false"
          >
            <MobileIcon name="x" :size="18" />
          </button>
        </header>
        <div class="t-sheet__body">
          <button
            v-for="c in campaigns"
            :key="c.id"
            class="t-pick"
            :class="{ 'is-on': c.id === campaignId }"
            type="button"
            @click="onSwitch(c.id)"
          >
            {{ c.name }}
          </button>
          <button
            class="u-btn u-btn--secondary u-btn--block"
            type="button"
            @click="pickerOpen = false; stage = 'onboarding'"
          >
            ＋ 新建剧本
          </button>
          <button class="u-btn u-btn--outline u-btn--block" type="button" @click="onRestart">
            重开本剧本（清空对话）
          </button>
        </div>
      </section>
    </div>
  </div>
</template>
