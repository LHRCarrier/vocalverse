/**
 * 酒馆 · 立绘展台状态（从 MobileTavernView 拆出以守 fe-08 行数）：
 * 开合/聚焦角色（DM/PC/NPC）、在场角色条点选、portrait 事件自动开、属性检定（D20 桌骰）。
 */
import { ref, watch, type Ref } from 'vue'

import type { TavernCastMember } from './useTavernCast'

export type StandeeHero = 'dm' | 'pc' | 'npc'
export type StandeeStatus = 'active' | 'arriving' | 'departed'

export interface StandeeNpc {
  name: string
  kind: string
  portraitUrl: string | null
  note?: string | null
  status?: StandeeStatus | null
}

export interface TavernStandeeDeps {
  portrait: Ref<{ entity: string; kind: string; url: string | null } | null>
  dismissPortrait: () => void
  toast: (message: string) => void
  roll: (payload: { dice: string }) => void
}

export function useTavernStandee(deps: TavernStandeeDeps) {
  const open = ref(false)
  const hero = ref<StandeeHero>('dm')
  const npc = ref<StandeeNpc | null>(null)

  function openStandee(target: StandeeHero) {
    hero.value = target
    open.value = true
  }

  /** 聚焦任意角色开立绘展台（在场角色条点选 / portrait 事件；立绘回退在展台内完成） */
  function openFor(
    name: string,
    kind: string,
    url: string | null,
    note: string | null = null,
    status: StandeeStatus | null = null,
  ) {
    npc.value = { name, kind, portraitUrl: url, note, status }
    openStandee('npc')
  }

  const onCastSelect = (member: TavernCastMember) =>
    openFor(member.name, member.kind, member.portraitUrl, member.note, member.status)

  /** 立绘事件（关键节点信号）：开立绘展台聚焦该角色，消费后清空 */
  watch(deps.portrait, (portrait) => {
    if (!portrait) return
    openFor(portrait.entity, portrait.kind, portrait.url)
    deps.dismissPortrait()
  })

  /** 属性检定 → 现有 D20 桌骰（真实请求；属性系统为占位，见展台组件注释） */
  function onRoll() {
    open.value = false
    deps.toast('🎲 检定已触发')
    deps.roll({ dice: 'd20' })
  }

  return { open, hero, npc, openStandee, openFor, onCastSelect, onRoll }
}
