<script setup lang="ts">
/**
 * 酒馆 · 主持台（迁移自 ai4u DmConsole）：底部抽屉四 tab —— 状态 / 事实表 / 任务线索 / 桌骰。
 * 纯展示 + 事件上抛（API 调用与刷新由页面负责）：用户手改/删除事实、增改任务线索、
 * 切场景、掷骰、重渲染摘要。
 */
import { computed, ref, watch } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'

import type { TrpgClueItem, TrpgFactItem, TrpgEventItem, TrpgTaskItem } from '@/api/trpg'

const props = withDefaults(
  defineProps<{
    open: boolean
    campaignName: string
    scene?: string | null
    snapshot: string
    narrativeSummary?: string | null
    facts: TrpgFactItem[]
    tasks: TrpgTaskItem[]
    clues: TrpgClueItem[]
    events: TrpgEventItem[]
    dangling: Array<{ type: string; title: string }>
  }>(),
  { scene: null, narrativeSummary: null },
)

const emit = defineEmits<{
  close: []
  'edit-fact': [key: string, value: string]
  'delete-fact': [key: string]
  'create-task': [title: string]
  'set-task-status': [taskId: number, status: string]
  'create-clue': [title: string]
  'recover-clue': [clueId: number, recovered: boolean]
  'set-scene': [scene: string]
  roll: [payload: { dice: string; modifier?: number; vs?: number; effectsText?: string }]
  'refresh-narrative': []
}>()

type Tab = 'state' | 'facts' | 'quests' | 'dice'
const tab = ref<Tab>('state')
const factFilter = ref<'all' | 'state' | 'fact'>('all')

const newFactKey = ref('')
const newFactValue = ref('')
const editingKey = ref<string | null>(null)
const editingValue = ref('')

const newTask = ref('')
const newClue = ref('')
const newScene = ref('')

const dice = ref('d20')
const diceModifier = ref('')
const diceVs = ref('')
const diceEffects = ref('')

const filteredFacts = computed(() =>
  props.facts.filter((f) => factFilter.value === 'all' || f.kind === factFilter.value),
)
const stateFacts = computed(() => props.facts.filter((f) => f.kind === 'state'))

watch(
  () => props.open,
  (open) => {
    if (open) tab.value = 'state'
  },
)

function startEdit(fact: TrpgFactItem) {
  editingKey.value = fact.key
  editingValue.value = fact.value
}

function saveEdit() {
  if (!editingKey.value) return
  const key = editingKey.value
  const value = editingValue.value.trim()
  editingKey.value = null
  if (value) emit('edit-fact', key, value)
}

function submitRoll() {
  const modifier = diceModifier.value.trim() === '' ? undefined : Number(diceModifier.value)
  const vs = diceVs.value.trim() === '' ? undefined : Number(diceVs.value)
  emit('roll', { dice: dice.value.trim(), modifier, vs, effectsText: diceEffects.value })
  diceEffects.value = ''
}
</script>

<template>
  <div v-if="open" class="t-sheet">
    <div class="t-sheet__backdrop" role="presentation" @click="emit('close')" />
    <section class="t-sheet__panel" role="dialog" aria-label="主持台">
      <header class="t-sheet__head">
        <div>
          <div class="t-sheet__title">主持台</div>
          <div class="t-sheet__sub">{{ campaignName }}</div>
        </div>
        <button class="t-sheet__close" type="button" title="关闭" aria-label="关闭" @click="emit('close')">
          <MobileIcon name="x" :size="18" />
        </button>
      </header>

      <nav class="t-sheet__tabs">
        <button type="button" :class="{ 'is-on': tab === 'state' }" @click="tab = 'state'">状态</button>
        <button type="button" :class="{ 'is-on': tab === 'facts' }" @click="tab = 'facts'">事实表</button>
        <button type="button" :class="{ 'is-on': tab === 'quests' }" @click="tab = 'quests'">任务线索</button>
        <button type="button" :class="{ 'is-on': tab === 'dice' }" @click="tab = 'dice'">桌骰</button>
      </nav>

      <div class="t-sheet__body">
        <!-- 状态 -->
        <template v-if="tab === 'state'">
          <div class="t-sheet__label">当前状态（注入视图 · 所见即 DM 所见）</div>
          <pre class="t-sheet__pre">{{ snapshot || '（暂无状态）' }}</pre>
          <div class="t-sheet__label">叙事摘要</div>
          <p class="t-sheet__text">{{ narrativeSummary || '（暂无摘要，回合后自动刷新）' }}</p>
          <button class="u-btn u-btn--secondary u-btn--block" type="button" @click="emit('refresh-narrative')">
            重新渲染摘要
          </button>
          <template v-if="dangling.length">
            <div class="t-sheet__label">悬空项（超窗未推进/未回收）</div>
            <div v-for="(d, i) in dangling" :key="i" class="t-sheet__row">
              <span class="t-chip t-chip--warn">{{ d.type === 'task' ? '任务' : '线索' }}</span>
              <span class="t-sheet__grow">{{ d.title }}</span>
            </div>
          </template>
        </template>

        <!-- 事实表 -->
        <template v-else-if="tab === 'facts'">
          <div class="t-sheet__filter">
            <button type="button" :class="{ 'is-on': factFilter === 'all' }" @click="factFilter = 'all'">全部</button>
            <button type="button" :class="{ 'is-on': factFilter === 'state' }" @click="factFilter = 'state'">State</button>
            <button type="button" :class="{ 'is-on': factFilter === 'fact' }" @click="factFilter = 'fact'">事实</button>
          </div>
          <div v-for="f in filteredFacts" :key="f.key" class="t-fact">
            <template v-if="editingKey === f.key">
              <input v-model="editingValue" class="text-input t-fact__input" aria-label="修改事实值">
              <button class="u-btn u-btn--primary u-btn--sm" type="button" @click="saveEdit">保存</button>
            </template>
            <template v-else>
              <div class="t-fact__main">
                <div class="t-fact__key">
                  {{ f.key }}
                  <span v-if="f.user_touched_at" title="用户手改（AI 不再覆盖）">✏️</span>
                  <span v-if="f.modality !== 'fact'" class="t-chip t-chip--warn">
                    {{ f.speaker || '某人' }} 声称
                  </span>
                </div>
                <div class="t-fact__value">{{ f.value }}</div>
              </div>
              <div class="t-fact__ops">
                <button type="button" title="编辑" aria-label="编辑" @click="startEdit(f)">
                  <MobileIcon name="pencil" :size="16" />
                </button>
                <button type="button" title="删除（墓碑，AI 不再复活）" aria-label="删除" @click="emit('delete-fact', f.key)">
                  <MobileIcon name="trash" :size="16" />
                </button>
              </div>
            </template>
          </div>
          <div class="t-sheet__label">新增 / 覆盖事实</div>
          <input v-model="newFactKey" class="text-input" placeholder="key：pc.主角.hp / rel.莉亚.attitude" aria-label="事实 key">
          <input v-model="newFactValue" class="text-input" placeholder="value：12 / 敌对" aria-label="事实 value">
          <button
            class="u-btn u-btn--primary u-btn--block"
            type="button"
            :disabled="!newFactKey.trim() || !newFactValue.trim()"
            @click="emit('edit-fact', newFactKey.trim(), newFactValue.trim()); newFactKey = ''; newFactValue = ''"
          >
            写入（标记为用户手改）
          </button>
        </template>

        <!-- 任务线索 -->
        <template v-else-if="tab === 'quests'">
          <div class="t-sheet__label">任务</div>
          <div v-for="t in tasks" :key="t.id" class="t-sheet__row">
            <span class="t-sheet__grow">{{ t.title }}</span>
            <select
              class="t-sheet__select"
              :value="t.status"
              :aria-label="`任务状态：${t.title}`"
              @change="emit('set-task-status', t.id, ($event.target as HTMLSelectElement).value)"
            >
              <option value="active">进行中</option>
              <option value="done">已完成</option>
              <option value="failed">失败</option>
            </select>
          </div>
          <div class="t-sheet__inline">
            <input v-model="newTask" class="text-input" placeholder="新任务标题" aria-label="新任务标题">
            <button
              class="u-btn u-btn--secondary u-btn--sm"
              type="button"
              :disabled="!newTask.trim()"
              @click="emit('create-task', newTask.trim()); newTask = ''"
            >
              添加
            </button>
          </div>

          <div class="t-sheet__label">线索</div>
          <div v-for="c in clues" :key="c.id" class="t-sheet__row">
            <span class="t-sheet__grow">{{ c.title }}</span>
            <button
              class="u-btn u-btn--sm"
              :class="c.recovered ? 'u-btn--secondary' : 'u-btn--primary'"
              type="button"
              @click="emit('recover-clue', c.id, !c.recovered)"
            >
              {{ c.recovered ? '已回收' : '标记回收' }}
            </button>
          </div>
          <div class="t-sheet__inline">
            <input v-model="newClue" class="text-input" placeholder="新线索标题" aria-label="新线索标题">
            <button
              class="u-btn u-btn--secondary u-btn--sm"
              type="button"
              :disabled="!newClue.trim()"
              @click="emit('create-clue', newClue.trim()); newClue = ''"
            >
              添加
            </button>
          </div>
        </template>

        <!-- 桌骰 -->
        <template v-else>
          <div class="t-sheet__label">切换场景</div>
          <div class="t-sheet__inline">
            <input v-model="newScene" class="text-input" :placeholder="scene || '如：酒馆 / 地城入口'" aria-label="新场景">
            <button
              class="u-btn u-btn--secondary u-btn--sm"
              type="button"
              :disabled="!newScene.trim()"
              @click="emit('set-scene', newScene.trim()); newScene = ''"
            >
              切换
            </button>
          </div>
          <div v-if="stateFacts.length" class="t-sheet__label">State 速览</div>
          <div v-for="f in stateFacts" :key="f.key" class="t-sheet__row">
            <span class="t-sheet__mono">{{ f.key }}</span>
            <span class="t-sheet__grow">{{ f.value }}</span>
          </div>
          <div class="t-sheet__label">掷骰（系统判定并落表）</div>
          <div class="t-dice-grid">
            <input v-model="dice" class="text-input" placeholder="d20 / 2d6" aria-label="骰子规格">
            <input v-model="diceModifier" class="text-input" placeholder="调整值" aria-label="调整值">
            <input v-model="diceVs" class="text-input" placeholder="对抗值 vs" aria-label="对抗值">
          </div>
          <input
            v-model="diceEffects"
            class="text-input"
            placeholder="效果：pc.主角.hp:-5;scene.current:1（可空）"
            aria-label="状态增量"
          >
          <button class="u-btn u-btn--primary u-btn--block" type="button" :disabled="!dice.trim()" @click="submitRoll">
            掷骰
          </button>
          <div v-if="events.length" class="t-sheet__label">事件日志</div>
          <div v-for="e in events" :key="e.id" class="t-event">第 {{ e.round }} 回合：{{ e.summary }}</div>
        </template>
      </div>
    </section>
  </div>
</template>
