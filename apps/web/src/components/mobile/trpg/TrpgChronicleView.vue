<script setup lang="ts">
/**
 * 酒馆 · 纪事（页内「纪事」tab 的内容区）。
 *
 * 本局摘要（`state.narrative_summary`）/ 编年史（`state.events`，最新在前，回合 + 摘要）/
 * 任务与线索（tasks/clues 状态）/ 尾声（消息行里的 `trpg_sys="ending"` 结局卡，实时与刷新同源）。
 * 只读视图：数据来自当前状态快照，不发新请求。
 */
import { computed } from 'vue'

import IconBook2 from '~icons/tabler/book-2'
import IconFlag from '~icons/tabler/flag'
import IconKey from '~icons/tabler/key'
import IconListCheck from '~icons/tabler/list-check'
import IconTimeline from '~icons/tabler/timeline'

import type { TrpgState } from '@/api/trpg'
import { readEndingPayload, type TavernEnding } from '@/composables/useTavernQuest'
import type { TavernRow } from '@/composables/useTavernSession'

import TrpgEndingCard from './TrpgEndingCard.vue'

const props = withDefaults(
  defineProps<{
    state?: TrpgState | null
    /** 消息行（含实时 upsert 的结局行；刷新后由 state.messages 重建） */
    rows?: TavernRow[]
  }>(),
  { state: null, rows: () => [] },
)

const summary = computed(
  () => props.state?.narrative_summary || props.state?.campaign.narrative_summary || null,
)

/** 编年史：最新在前（轮次降序，同轮按 id 降序） */
const events = computed(() =>
  [...(props.state?.events ?? [])].sort((a, b) => b.round - a.round || b.id - a.id),
)

const tasks = computed(() => props.state?.tasks ?? [])
const clues = computed(() => props.state?.clues ?? [])

const TASK_LABELS = { active: '进行中', done: '已完成', failed: '失败' } as const

function clueStatus(clue: { found: boolean; recovered: boolean }): string {
  if (clue.recovered) return '已回收'
  if (clue.found) return '已找到'
  return '未找到'
}

/** 结局卡：实时行与刷新恢复都走 `trpg_sys="ending"` 的 payload（同任务前端已去重） */
const endings = computed<TavernEnding[]>(() =>
  props.rows
    .map((row) => readEndingPayload(row.payload ?? null))
    .filter((ending): ending is TavernEnding => ending != null),
)
</script>

<template>
  <div class="t-chron">
    <section class="t-chron__sec">
      <h2 class="t-chron__title"><IconListCheck /> 本局摘要</h2>
      <p v-if="summary" class="t-chron__sum">{{ summary }}</p>
      <div v-else class="t-chron__empty">还没有摘要——回合结束后会自动生成。</div>
    </section>

    <section class="t-chron__sec">
      <h2 class="t-chron__title">
        <IconTimeline /> 编年史
        <span class="t-chron__count">{{ events.length }}</span>
      </h2>
      <ol v-if="events.length" class="t-chron__events">
        <li v-for="event in events" :key="event.id" class="t-chron__event">
          <span class="t-chron__round">第 {{ event.round }} 回合</span>
          <span class="t-chron__event-text">{{ event.summary }}</span>
        </li>
      </ol>
      <div v-else class="t-chron__empty">还没有编年记录——故事推进时会逐回合写入。</div>
    </section>

    <section class="t-chron__sec">
      <h2 class="t-chron__title">
        <IconFlag /> 任务与线索
      </h2>
      <div v-if="tasks.length || clues.length" class="t-chron__deck">
        <div v-for="task in tasks" :key="`t-${task.id}`" class="t-chron__row">
          <IconFlag />
          <span class="t-chron__row-title">{{ task.title }}</span>
          <span class="t-chron__tag" :class="`is-${task.status}`">
            {{ TASK_LABELS[task.status] }}
          </span>
        </div>
        <div v-for="clue in clues" :key="`c-${clue.id}`" class="t-chron__row">
          <IconKey />
          <span class="t-chron__row-title">
            {{ clue.title }}
            <span v-if="clue.content" class="t-chron__row-sub">{{ clue.content }}</span>
          </span>
          <span class="t-chron__tag" :class="{ 'is-found': clue.found, 'is-recovered': clue.recovered }">
            {{ clueStatus(clue) }}
          </span>
        </div>
      </div>
      <div v-else class="t-chron__empty">还没有任务或线索——和剧中人物多聊聊。</div>
    </section>

    <section class="t-chron__sec">
      <h2 class="t-chron__title">
        <IconBook2 /> 尾声
        <span class="t-chron__count">{{ endings.length }}</span>
      </h2>
      <template v-if="endings.length">
        <TrpgEndingCard
          v-for="ending in endings"
          :key="`${ending.quest}-${ending.outcome}-${ending.title}`"
          :payload="{ trpg_sys: 'ending', ...ending }"
        />
      </template>
      <div v-else class="t-chron__empty">本局还没有尾声——钟满时可主动「收尾本幕」。</div>
    </section>
  </div>
</template>
