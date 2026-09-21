/**
 * 酒馆场景卡 + 用户偏好 composable（docs/52 §12）。
 *
 * - 场景卡：平台固定卡（source=admin）+ 我的私有卡（source=user）；支持按关键词 LLM 生成草稿
 *   （不落库 → 预览 → 保存/重生成）、手动新建、改名/改场景/改开场、删除（归档）、开局；
 * - 偏好：语言（zh/en，作用 DM 输出）/ 语音自动朗读 / 音色（预留，仅展示）；服务端持久化跨设备。
 */
import { computed, ref } from 'vue'

import {
  createCard,
  deleteCard,
  fetchCards,
  fetchPrefs,
  generateCard,
  startCard,
  updateCard,
  updatePrefs,
  type TrpgCard,
  type TrpgCardUpsert,
  type TrpgPrefs,
} from '@/api/trpg'

export function useTavernCards() {
  const cards = ref<TrpgCard[]>([])
  const cardsLoading = ref(false)
  const prefs = ref<TrpgPrefs>({ lang: 'zh', voice_enabled: true, voice_name: null })
  const prefsSaving = ref(false)
  const generating = ref(false)
  const draft = ref<TrpgCardUpsert | null>(null)
  const error = ref<string | null>(null)

  const myCards = computed(() => cards.value.filter((c) => c.source === 'user'))
  const platformCards = computed(() => cards.value.filter((c) => c.source === 'admin'))

  async function loadCards() {
    cardsLoading.value = true
    error.value = null
    try {
      cards.value = await fetchCards()
    } catch (e) {
      error.value = (e as Error).message
    } finally {
      cardsLoading.value = false
    }
  }

  async function loadPrefs() {
    try {
      prefs.value = await fetchPrefs()
    } catch {
      /* 偏好读取失败走默认（不阻塞游玩） */
    }
  }

  async function savePrefs(patch: Partial<TrpgPrefs>) {
    const previous = prefs.value
    prefs.value = { ...prefs.value, ...patch } // 乐观更新（开关即时反馈）
    prefsSaving.value = true
    error.value = null
    try {
      prefs.value = await updatePrefs(patch)
    } catch (e) {
      prefs.value = previous // 失败回滚
      error.value = (e as Error).message
    } finally {
      prefsSaving.value = false
    }
  }

  /** 按关键词生成草稿（保存于 draft，不落库） */
  async function generateFromKeywords(keywords: string) {
    generating.value = true
    error.value = null
    draft.value = null
    try {
      draft.value = await generateCard(keywords, prefs.value.lang)
      return draft.value
    } catch (e) {
      error.value = (e as Error).message
      return null
    } finally {
      generating.value = false
    }
  }

  /** 保存草稿为我的卡；成功返回卡片（调用方决定是否接着开局） */
  async function saveDraft(): Promise<TrpgCard | null> {
    if (!draft.value) return null
    try {
      const card = await createCard({ ...draft.value, language: prefs.value.lang })
      draft.value = null
      await loadCards()
      return card
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  async function createManual(payload: TrpgCardUpsert): Promise<TrpgCard | null> {
    try {
      const card = await createCard(payload)
      await loadCards()
      return card
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  async function updateCardFields(cardId: number, patch: TrpgCardUpsert): Promise<boolean> {
    try {
      await updateCard(cardId, patch)
      await loadCards()
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    }
  }

  async function removeCard(cardId: number): Promise<boolean> {
    try {
      await deleteCard(cardId)
      await loadCards()
      return true
    } catch (e) {
      error.value = (e as Error).message
      return false
    }
  }

  /** 从卡片开局：返回新 campaign id（调用方负责切到该剧本） */
  async function startFromCard(cardId: number): Promise<number | null> {
    try {
      return await startCard(cardId)
    } catch (e) {
      error.value = (e as Error).message
      return null
    }
  }

  function clearDraft() {
    draft.value = null
  }

  return {
    cards,
    myCards,
    platformCards,
    cardsLoading,
    prefs,
    prefsSaving,
    generating,
    draft,
    error,
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
  }
}

export type TavernCards = ReturnType<typeof useTavernCards>
