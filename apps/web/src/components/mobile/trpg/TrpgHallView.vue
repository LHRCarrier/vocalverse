<script setup lang="ts">
/**
 * 酒馆 · 大堂（页内「大堂」tab 的内容区；此前是占位 toast，现为真实视图）。
 *
 * 大堂 = 开局前的休息区：继续冒险（当前剧本卡）/ 我的冒险（切换 · 重开）/
 * 用场景卡开新局（走既有卡抽屉）/ 已完结（列表契约的 finished/finished_at + 当前局结局提示）。
 * 数据全部来自现有会话（session.campaigns / session.state），不发新请求；空态给下一步入口。
 */
import { computed } from 'vue'

import IconBook2 from '~icons/tabler/book-2'
import IconCards from '~icons/tabler/cards'
import IconCompass from '~icons/tabler/compass'
import IconRefresh from '~icons/tabler/refresh'

import type { TrpgCampaignItem, TrpgState } from '@/api/trpg'
import { readEndingPayload } from '@/composables/useTavernQuest'

const props = withDefaults(
  defineProps<{
    campaigns?: TrpgCampaignItem[]
    currentId?: number | null
    state?: TrpgState | null
    /** 当前剧本已完结（session.finished，读 campaign.finished） */
    finished?: boolean
  }>(),
  { campaigns: () => [], currentId: null, state: null, finished: false },
)

const emit = defineEmits<{
  continue: []
  switchCampaign: [id: number]
  restart: []
  openCards: []
}>()

const summary = computed(
  () => props.state?.narrative_summary || props.state?.campaign.narrative_summary || null,
)
const scene = computed(() => props.state?.scene ?? null)

/**
 * 是否已完结：列表契约（`finished`）优先；结算后列表未及刷新的窗口期，
 * 当前剧本以 state 的 `finished`（session.finished）为准。
 */
function isFinished(campaign: TrpgCampaignItem): boolean {
  return campaign.finished === true || (campaign.id === props.currentId && props.finished)
}

/** 已完结分组：列表里没有当前已完结剧本时补一行（结算 → 列表刷新之间的窗口期） */
const finishedCampaigns = computed(() => {
  const list = props.campaigns.filter(isFinished)
  if (!props.finished || props.currentId == null || list.some((c) => c.id === props.currentId)) return list
  const current = props.campaigns.find((c) => c.id === props.currentId)
  return current ? [{ ...current, finished: true }, ...list] : list
})

/** 当前剧本的结局提示（结局系统卡 payload；只有已加载的当前剧本拿得到） */
const endingHint = computed(() => {
  const message = [...(props.state?.messages ?? [])]
    .reverse()
    .find((m) => m.payload?.trpg_sys === 'ending')
  return readEndingPayload(message?.payload ?? null)
})

/** ISO 时间 → `YYYY-MM-DD`；非法/缺省 → null（不显示空占位） */
function fmtTime(iso?: string | null): string | null {
  if (!iso) return null
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}
</script>

<template>
  <div class="t-hall">
    <section class="t-hall__sec">
      <h2 class="t-hall__title"><IconCompass /> 继续冒险</h2>
      <div v-if="props.state" class="t-hall__hero">
        <div class="t-hall__hero-top">
          <span class="t-hall__hero-name">{{ props.state.campaign.name }}</span>
          <span v-if="props.finished" class="t-hall__badge is-done">已完结</span>
          <span v-else class="t-hall__badge is-live">进行中</span>
        </div>
        <p v-if="scene" class="t-hall__hero-scene">📍 {{ scene }}</p>
        <p class="t-hall__hero-sum">
          {{ summary ?? '还没有本局摘要——回到跑团里推进故事，回合结束会自动生成。' }}
        </p>
        <button class="u-btn u-btn--primary u-btn--block" type="button" @click="emit('continue')">
          {{ props.finished ? '回顾本局' : '继续冒险' }}
        </button>
      </div>
      <div v-else class="t-hall__empty">
        还没有开局——挑一张场景卡，酒馆会为你准备第一位说书人。
      </div>
    </section>

    <section class="t-hall__sec">
      <h2 class="t-hall__title">
        <IconBook2 /> 我的冒险
        <span class="t-hall__count">{{ props.campaigns.length }}</span>
      </h2>
      <div v-if="props.campaigns.length" class="t-hall__list">
        <div
          v-for="c in props.campaigns"
          :key="c.id"
          class="t-hall__item"
          :class="{ 'is-on': c.id === props.currentId }"
        >
          <button
            class="t-hall__item-main"
            type="button"
            :aria-label="`切换剧本 ${c.name}`"
            @click="emit('switchCampaign', c.id)"
          >
            <span class="t-hall__item-name">{{ c.name }}</span>
            <span class="t-hall__item-meta">
              <span v-if="c.id === props.currentId" class="t-hall__badge is-live">当前</span>
              <span v-if="isFinished(c)" class="t-hall__badge is-done">已完结</span>
              <span v-if="fmtTime(c.last_active_at)" class="t-hall__time">{{ fmtTime(c.last_active_at) }}</span>
            </span>
          </button>
          <button
            v-if="c.id === props.currentId"
            class="t-hall__restart"
            type="button"
            title="重开本剧本（清空对话）"
            aria-label="重开本剧本"
            @click="emit('restart')"
          >
            <IconRefresh />
          </button>
        </div>
      </div>
      <div v-else class="t-hall__empty">还没有冒险记录——用场景卡开新局后会出现在这里。</div>
    </section>

    <section class="t-hall__sec">
      <h2 class="t-hall__title"><IconCards /> 用场景卡开新局</h2>
      <p class="t-hall__hint">示例剧本或自己的卡都行；开局即进入新的篇章。</p>
      <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="emit('openCards')">
        打开场景卡
      </button>
    </section>

    <section class="t-hall__sec">
      <h2 class="t-hall__title">
        <IconBook2 /> 已完结
        <span class="t-hall__count">{{ finishedCampaigns.length }}</span>
      </h2>
      <div v-if="finishedCampaigns.length" class="t-hall__list">
        <button
          v-for="c in finishedCampaigns"
          :key="c.id"
          class="t-hall__done"
          type="button"
          :aria-label="`查看已完结剧本 ${c.name}`"
          @click="emit('switchCampaign', c.id)"
        >
          <span class="t-hall__done-top">
            <span class="t-hall__item-name">{{ c.name }}</span>
            <span class="t-hall__time">{{ fmtTime(c.finished_at) ?? '已完结' }}</span>
          </span>
          <span v-if="endingHint && c.id === props.currentId" class="t-hall__done-hint">
            {{ endingHint.title }}<template v-if="endingHint.epilogue"> · {{ endingHint.epilogue }}</template>
          </span>
        </button>
      </div>
      <div v-else class="t-hall__empty">
        还没有完结的篇章——钟满时在动作面板点「收尾本幕」，结局会收进这里。
      </div>
    </section>
  </div>
</template>
