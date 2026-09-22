/**
 * 酒馆 · 动态推荐行动（docs/57 §3.2「推荐行动动态化」）：
 *
 * 按 场景 / 在场名单 / 进行中任务 / 遭遇 生成 2~3 条情境建议，
 * 状态变化（computed 依赖）即自动刷新——取代原静态三条（观察四周/找人搭话/握紧武器）。
 * 纯函数供单测；`useTavernSuggestions` 只是对响应式输入的包装。
 */
import { computed, type ComputedRef, type Ref } from 'vue'

export type TavernQuickActionKind = 'observe' | 'talk' | 'advance'

export interface TavernQuickAction {
  kind: TavernQuickActionKind
  label: string
  /** 点击后填入输入框的台词 */
  text: string
}

export interface SuggestionInput {
  scene?: string | null
  /** 在场成员（kind=pc/npc；顺带决定「与谁交谈」） */
  present?: ReadonlyArray<{ name: string; kind: 'pc' | 'npc' }>
  /** 进行中的任务（`status=active`） */
  quests?: ReadonlyArray<{ name: string; status: string }>
  /** 遭遇（有当前行动者时优先与 TA 交谈） */
  encounter?: { currentName?: string | null } | null
}

/** 按场景/在场/任务生成建议行动（通用三条常驻，有情境时升级文案；最多 3 条） */
export function buildQuickActions(input: SuggestionInput): TavernQuickAction[] {
  const out: TavernQuickAction[] = []
  const scene = String(input.scene ?? '').trim()

  out.push(
    scene
      ? { kind: 'observe', label: `观察${scene}`, text: `我仔细观察${scene}` }
      : { kind: 'observe', label: '观察四周', text: '我仔细观察四周' },
  )

  // 最近 NPC：遭遇当前行动者（若为 NPC）优先，否则取在场 NPC 末位（最近入场/发言者）
  const npcs = (input.present ?? []).filter((m) => m.kind === 'npc')
  const current = String(input.encounter?.currentName ?? '').trim()
  const nearest =
    current && npcs.some((n) => n.name === current)
      ? current
      : (npcs[npcs.length - 1]?.name ?? '')
  out.push(
    nearest
      ? { kind: 'talk', label: `与${nearest}交谈`, text: `我试着与${nearest}交谈` }
      : { kind: 'talk', label: '交谈', text: '我试着与在场的人交谈' },
  )

  const quest = (input.quests ?? []).find((q) => q.status === 'active')
  out.push(
    quest
      ? { kind: 'advance', label: `推进${quest.name}`, text: `我继续推进：${quest.name}` }
      : { kind: 'advance', label: '前进', text: '我继续向前推进' },
  )

  return out
}

export interface SuggestionSources {
  scene: Ref<string | null | undefined>
  present: Ref<ReadonlyArray<{ name: string; kind: 'pc' | 'npc' }>>
  quests: Ref<ReadonlyArray<{ name: string; status: string }>>
  encounter: Ref<{ currentName?: string | null } | null>
}

export function useTavernSuggestions(sources: SuggestionSources): ComputedRef<TavernQuickAction[]> {
  return computed(() =>
    buildQuickActions({
      scene: sources.scene.value,
      present: sources.present.value,
      quests: sources.quests.value,
      encounter: sources.encounter.value,
    }),
  )
}
