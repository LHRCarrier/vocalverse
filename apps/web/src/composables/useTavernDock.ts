/**
 * 酒馆 · dock 状态编排（docs/57 §3.2，从 MobileTavernView 拆出以守 fe-08 行数）：
 * 迷你条展开态 / 动作面板填入请求 / 主持台 tab / 收尾本幕（结算 + 回执 + 滚底）。
 */
import { nextTick, ref } from 'vue'

export type TavernConsoleTab = 'state' | 'facts' | 'quests' | 'dice'

export interface TavernDockDeps {
  /** 确定性结算（useTavernSession.settleQuest） */
  settle: (quest: string) => Promise<boolean>
  toast: (message: string) => void
  /** 保证一次滚底（结算后定位尾声卡） */
  pinToBottom: () => void
}

export function useTavernDock(deps: TavernDockDeps) {
  const stripExpanded = ref(false)
  const dockPrefill = ref<{ text: string; seq: number } | null>(null)
  const consoleOpen = ref(false)
  const consoleTab = ref<TavernConsoleTab>('state')

  function toggleStrip() {
    stripExpanded.value = !stripExpanded.value
  }

  /** 动作面板建议 chip → 填入输入框（seq 递增，重复点同一条也生效） */
  function onPrefill(text: string) {
    dockPrefill.value = { text, seq: (dockPrefill.value?.seq ?? 0) + 1 }
  }

  function openConsole(tab: TavernConsoleTab = 'state') {
    consoleTab.value = tab
    consoleOpen.value = true
  }

  async function onSettle(quest: string) {
    const ok = await deps.settle(quest)
    deps.toast(ok ? '本幕已收尾' : '结算失败，已改为文本行动')
    if (ok) {
      await nextTick()
      deps.pinToBottom()
    }
  }

  return {
    stripExpanded,
    dockPrefill,
    consoleOpen,
    consoleTab,
    toggleStrip,
    onPrefill,
    openConsole,
    onSettle,
  }
}
