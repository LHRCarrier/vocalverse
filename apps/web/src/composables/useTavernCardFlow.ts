/**
 * 酒馆 · 场景卡流程（从 MobileTavernView 拆出以守 fe-08 行数）：
 * 打开卡片抽屉 / 从卡片开局（切到新 campaign）/ 保存草稿即开局 / 手动建卡即开局。
 */
import type { TavernCards } from './useTavernCards'

export interface TavernCardFlowDeps {
  cards: TavernCards
  refreshCampaigns: () => Promise<void>
  selectCampaign: (id: number) => Promise<void>
  open: () => void
  close: () => void
}

export function useTavernCardFlow(deps: TavernCardFlowDeps) {
  function openCards() {
    deps.open()
    void deps.cards.loadCards()
  }

  async function onStartCard(id: number) {
    const newCampaignId = await deps.cards.startFromCard(id)
    if (newCampaignId == null) return
    deps.close()
    await deps.refreshCampaigns()
    await deps.selectCampaign(newCampaignId)
  }

  async function onSaveDraftAndStart() {
    const card = await deps.cards.saveDraft()
    if (card) await onStartCard(card.id)
  }

  async function onCreateCard(payload: { title: string; scene: string; opening_line: string }) {
    const card = await deps.cards.createManual(payload)
    if (card) await onStartCard(card.id)
  }

  return { openCards, onStartCard, onSaveDraftAndStart, onCreateCard }
}
