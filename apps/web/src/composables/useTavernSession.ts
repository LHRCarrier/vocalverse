/**
 * 酒馆（TRPG 跑团）会话编排 composable：剧本装载/开局、回合 SSE、主持台动作。
 *
 * 视图只做渲染与用户手势；状态与请求全在本模块（便于单测与文件行数约束）。
 * 音频（逐句 TTS 播放/重听）由 useTavernAudio 承担，本模块只把 audio_chunk URL 转交。
 */
import { computed, ref } from 'vue'

import {
  clearCampaignMessages,
  createCampaign,
  createClue,
  createTask,
  editFact,
  fetchCampaignState,
  fetchCampaigns,
  setScene,
  streamTrpgTurn,
  type TrpgCampaignItem,
  type TrpgState,
} from '@/api/trpg'
import type { TrpgSseEvent } from '@/audio/trpg-sse-types'
import { MIN_RECORD_MS, VoiceRecorder, micErrorMessage } from '@/audio/recorder'
import type { TavernAudio } from '@/composables/useTavernAudio'
import { useTavernCast } from '@/composables/useTavernCast'
import { useTavernConsole } from '@/composables/useTavernConsole'
import { useTavernEncounter } from '@/composables/useTavernEncounter'
import { useTavernQuest } from '@/composables/useTavernQuest'

export interface TavernRow {
  role: 'user' | 'assistant'
  kind: 'text' | 'system'
  content: string
  payload?: Record<string, unknown> | null
  speakable?: boolean
  live?: boolean
}

const STORAGE_KEY = 'vv_trpg_campaign'

export function useTavernSession(audio: TavernAudio) {
  const stage = ref<'loading' | 'onboarding' | 'play' | 'error'>('loading')
  const campaigns = ref<TrpgCampaignItem[]>([])
  const state = ref<TrpgState | null>(null)
  const campaignId = ref<number | null>(null)
  const rows = ref<TavernRow[]>([])
  const inputError = ref<string | null>(null)
  const bootError = ref<string | null>(null)
  const sending = ref(false)
  const recording = ref(false)
  const statusHint = ref<string | null>(null)
  /**
   * 最近一次立绘展示信号（关键节点，docs/54 P1 骨架）：
   * 页面消费后调用 dismissPortrait()；图源未接时 url 为 null（页面按名字命中内置素材）。
   */
  const portrait = ref<{
    entity: string
    kind: string
    mood: string | null
    url: string | null
  } | null>(null)
  const currentAssistant = ref<TavernRow | null>(null)
  /** 最近一条 DM 文本行的下标（系统卡可能在其后插入，音频块到达时不能靠 rows.length 反推） */
  const assistantRowIndex = ref<number | null>(null)

  const recorder = new VoiceRecorder()
  let abort = new AbortController()

  const status = computed<'idle' | 'busy' | 'error'>(() => {
    if (inputError.value) return 'error'
    if (sending.value) return 'busy'
    return 'idle'
  })
  const hp = computed(() => state.value?.facts.find((f) => f.key.endsWith('.hp'))?.value ?? null)
  const location = computed(
    () => state.value?.facts.find((f) => f.key.endsWith('.location'))?.value ?? null,
  )
  const inventory = computed(
    () => state.value?.facts.find((f) => f.key.endsWith('.inventory'))?.value ?? null,
  )
  const activeTasks = computed(
    () => state.value?.tasks.filter((t) => t.status === 'active').length ?? 0,
  )
  const danglingCount = computed(() => state.value?.verify?.dangling?.length ?? 0)
  const npcNames = computed(
    () => new Set(state.value?.entities.filter((e) => e.kind === 'npc').map((e) => e.name) ?? []),
  )

  async function boot() {
    stage.value = 'loading'
    bootError.value = null
    try {
      campaigns.value = await fetchCampaigns()
      if (!campaigns.value.length) {
        stage.value = 'onboarding'
        return
      }
      const remembered = Number(localStorage.getItem(STORAGE_KEY))
      const target = campaigns.value.find((c) => c.id === remembered) ?? campaigns.value[0]!
      await selectCampaign(target.id)
    } catch (e) {
      bootError.value = (e as Error).message
      stage.value = 'error'
    }
  }

  async function selectCampaign(id: number) {
    abort.abort()
    abort = new AbortController()
    audio.flush()
    currentAssistant.value = null
    assistantRowIndex.value = null
    inputError.value = null
    sending.value = false
    campaignId.value = id
    localStorage.setItem(STORAGE_KEY, String(id))
    try {
      const snapshot = await fetchCampaignState(id)
      state.value = snapshot
      rows.value = snapshot.messages.map((m) => ({
        role: m.role,
        kind: m.kind,
        content: m.content,
        payload: m.payload ?? null,
        speakable: m.kind === 'text' && m.role === 'assistant',
      }))
      stage.value = 'play'
    } catch (e) {
      bootError.value = (e as Error).message
      stage.value = 'error'
    }
  }

  /** 仅刷新剧本列表（卡片开局/新建后同步侧栏，不重挂会话） */
  async function refreshCampaigns() {
    try {
      campaigns.value = await fetchCampaigns()
    } catch {
      /* 列表刷新失败保留旧值 */
    }
  }

  async function createAndOpen(options: { name: string; scene: string; demo: boolean }) {
    stage.value = 'loading'
    bootError.value = null
    try {
      const created = await createCampaign(options.name)
      await setScene(created.id, options.scene)
      if (options.demo) {
        await editFact(created.id, 'pc.主角.hp', '12')
        await editFact(created.id, 'pc.主角.location', '吧台')
        await editFact(created.id, 'pc.主角.inventory', '短剑')
        await createTask(created.id, '打听镇上的怪谈')
        await createClue(created.id, '地下室里的暗门', '酒保提到过地下室的门', options.scene)
      }
      campaigns.value = await fetchCampaigns()
      await selectCampaign(created.id)
    } catch (e) {
      bootError.value = (e as Error).message
      stage.value = 'error'
    }
  }

  const startDemo = () => createAndOpen({ name: '迷雾酒馆', scene: '酒馆', demo: true })
  const startCustom = (payload: { name: string; scene: string }) =>
    createAndOpen({ ...payload, demo: false })

  async function switchCampaign(id: number) {
    if (id === campaignId.value) return
    await selectCampaign(id)
  }

  async function restartCampaign() {
    if (campaignId.value == null) return
    if (!window.confirm('重开本剧本？会清空对话流水（事实/任务/线索保留）。')) return
    await clearCampaignMessages(campaignId.value)
    await selectCampaign(campaignId.value)
  }

  function sendTurn(form: FormData, optimistic?: string) {
    if (campaignId.value == null) return
    if (optimistic !== undefined) {
      rows.value.push({ role: 'user', kind: 'text', content: optimistic })
    }
    sending.value = true
    inputError.value = null
    statusHint.value = null
    currentAssistant.value = null
    streamTrpgTurn(
      campaignId.value,
      form,
      onSseEvent,
      (err) => {
        inputError.value = (err as Error).message
        sending.value = false
        statusHint.value = null
      },
      () => {
        sending.value = false
        statusHint.value = null
        currentAssistant.value = null
        void refreshState()
      },
      abort.signal,
    )
  }

  function sendText(text: string) {
    const form = new FormData()
    form.append('text', text)
    sendTurn(form, text)
  }

  function toggleMic() {
    if (sending.value) return
    if (recording.value) {
      if (recorder.state === 'recording') recorder.stop()
      else recorder.cancel()
      return
    }
    inputError.value = null
    recording.value = true
    void recorder.start(30_000).catch((e) => {
      recording.value = false
      inputError.value = micErrorMessage(e)
    })
  }

  recorder.onStateChange = (s) => {
    if (s !== 'recording') recording.value = false
  }
  recorder.onStop = (blob, _mime, durationMs) => {
    if (durationMs < MIN_RECORD_MS) {
      inputError.value = `录音太短（${(durationMs / 1000).toFixed(1)}s），请说满约 ${MIN_RECORD_MS / 1000} 秒后再点 ■ 停止`
      return
    }
    const form = new FormData()
    form.append('audio', blob, 'recording.webm')
    sendTurn(form, '🎙 语音行动…')
  }

  function onSseEvent(e: TrpgSseEvent) {
    switch (e.type) {
      case 'user_transcript': {
        const lastUser = [...rows.value].reverse().find((r) => r.role === 'user')
        if (lastUser) lastUser.content = e.text
        break
      }
      case 'text_delta':
        if (!currentAssistant.value) {
          rows.value.push({ role: 'assistant', kind: 'text', content: '', live: true })
          currentAssistant.value = rows.value[rows.value.length - 1]!
          assistantRowIndex.value = rows.value.length - 1
        }
        currentAssistant.value.content += e.text
        break
      case 'status':
        statusHint.value = e.stage === 'rolling' ? '掷骰判定中…' : '切换场景…'
        break
      case 'portrait':
        portrait.value = {
          entity: e.entity,
          kind: e.kind,
          mood: e.mood ?? null,
          url: e.url ?? null,
        }
        break
      case 'system':
        rows.value.push({
          role: 'assistant',
          kind: 'system',
          content: '',
          payload: { trpg_sys: e.trpg_sys, ...e.payload },
        })
        break
      /* 闭环事件（docs/56 §5）：本层只做委派，派生在各自领域 composable */
      case 'quest':
        questDomain.apply(e)
        break
      case 'ending':
        questDomain.applyEnding(e)
        break
      case 'character':
        castDomain.apply(e)
        break
      case 'encounter':
        encounterDomain.apply(e)
        break
      case 'audio_chunk':
        // 逐词高亮：服务端带句子文本与偏移（docs/52 §12.3）
        audio.queueChunk(
          e.url,
          assistantRowIndex.value ?? rows.value.length - 1,
          e.text ?? null,
          e.offset ?? null,
          e.duration ?? null,
        )
        break
      case 'turn_end':
        if (currentAssistant.value) {
          currentAssistant.value.live = false
          currentAssistant.value.speakable = true
        }
        break
      case 'error':
        inputError.value = `酒馆提示：${e.code}`
        break
    }
  }

  async function refreshState() {
    if (campaignId.value == null) return
    try {
      state.value = await fetchCampaignState(campaignId.value)
    } catch {
      /* 刷新失败保留旧快照（下一动作/重进页面再对齐） */
    }
  }

  const consoleActions = useTavernConsole({
    campaignId,
    rows,
    scene: () => state.value?.scene,
    refresh: refreshState,
    onError: (message) => {
      inputError.value = message
    },
  })

  /** 闭环领域状态（docs/56 §6：一域一 composable；本层只转发事件 + 暴露） */
  const questDomain = useTavernQuest(state)
  const castDomain = useTavernCast(state)
  const encounterDomain = useTavernEncounter(state)

  function dispose() {
    abort.abort()
    audio.flush()
    audio.releaseAll()
  }

  function dismissPortrait() {
    portrait.value = null
  }

  return {
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
    portrait,
    status,
    hp,
    location,
    inventory,
    activeTasks,
    danglingCount,
    npcNames,
    dismissPortrait,
    boot,
    refreshCampaigns,
    selectCampaign,
    startDemo,
    startCustom,
    switchCampaign,
    restartCampaign,
    sendText,
    toggleMic,
    dispose,
    quest: questDomain,
    cast: castDomain,
    encounter: encounterDomain,
    ...consoleActions,
  }
}
