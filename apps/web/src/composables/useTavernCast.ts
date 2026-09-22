/**
 * 酒馆 · 在场名单（docs/56 §6：一域一 composable，规则派生不发请求）。
 *
 * 口径（docs/56 §B）：实体 `pending=true` = 「正在赶来」（arriving）、
 * `status='cleared'` = 已离场（departed），其余为在场（active）。
 * 立绘解析顺序：实体 `portrait.url` → 内置素材（art.ts，PC 用设计稿占位图）→ 首字占位。
 */
import { computed, ref, watch, type Ref } from 'vue'

import type { TrpgEntityItem, TrpgState } from '@/api/trpg'
import type { TrpgCharacterEvent } from '@/audio/trpg-sse-types'

import { TAVERN_ART, npcAvatar } from '@/components/mobile/trpg/art'

export type TavernCastStatus = 'arriving' | 'active' | 'departed'
export type TavernCastKind = 'npc' | 'pc'

export interface TavernCastMember {
  name: string
  kind: TavernCastKind
  status: TavernCastStatus
  pending: boolean
  note: string | null
  entityId: number | null
  /** 解析后的可展示立绘 URL（无则 null → 组件用首字占位） */
  portraitUrl: string | null
}

/** 实体状态归一（后端实体表 → 前端三态） */
export function memberStatus(entity: TrpgEntityItem): TavernCastStatus {
  if (entity.status === 'cleared') return 'departed'
  return entity.pending ? 'arriving' : 'active'
}

function isCastEntity(entity: TrpgEntityItem): boolean {
  return entity.kind === 'npc' || entity.kind === 'pc'
}

export function useTavernCast(state: Ref<TrpgState | null>) {
  /** SSE 增量覆盖（entity 表刷新后清空，以快照为准） */
  const overlays = ref(new Map<string, { kind: TavernCastKind; status: TavernCastStatus; note: string | null }>())

  watch(
    () => state.value,
    () => overlays.value.clear(),
  )

  /** 名字 → 实体（用于立绘解析；同名以快照实体优先） */
  function entityFor(name: string): TrpgEntityItem | null {
    return state.value?.entities.find((e) => e.name === name) ?? null
  }

  /** 立绘解析：实体挂图 url → 内置素材（PC 设计稿占位 / NPC 按名字命中）→ null。 */
  function portraitFor(name: string): string | null {
    const entity = entityFor(name)
    if (entity?.portrait?.url) return entity.portrait.url
    if (entity?.kind === 'pc') return TAVERN_ART.pcAvatar
    return npcAvatar(name)
  }

  function toMember(entity: TrpgEntityItem): TavernCastMember {
    return {
      name: entity.name,
      kind: entity.kind === 'pc' ? 'pc' : 'npc',
      status: memberStatus(entity),
      pending: entity.pending,
      note: null,
      entityId: entity.id,
      portraitUrl: portraitFor(entity.name),
    }
  }

  /** 名单：快照实体 + 事件增量（实体尚未落表时先按事件展示） */
  const members = computed<TavernCastMember[]>(() => {
    const list = (state.value?.entities ?? []).filter(isCastEntity).map(toMember)
    const byName = new Map(list.map((m) => [m.name, m]))
    for (const [name, patch] of overlays.value) {
      const existing = byName.get(name)
      if (existing) {
        existing.kind = patch.kind
        existing.status = patch.status
        existing.pending = patch.status === 'arriving'
        existing.note = patch.note
      } else {
        byName.set(name, {
          name,
          kind: patch.kind,
          status: patch.status,
          pending: patch.status === 'arriving',
          note: patch.note,
          entityId: null,
          portraitUrl: portraitFor(name),
        })
      }
    }
    return [...byName.values()].sort((a, b) => statusRank(a) - statusRank(b))
  })

  const present = computed(() => members.value.filter((m) => m.status === 'active'))
  const arriving = computed(() => members.value.filter((m) => m.status === 'arriving'))
  const departed = computed(() => members.value.filter((m) => m.status === 'departed'))

  /** 应用 `character` 事件：入场/在场/离场三态增量。 */
  function apply(e: TrpgCharacterEvent): void {
    overlays.value.set(e.name, {
      kind: e.kind === 'pc' ? 'pc' : 'npc',
      status: e.status,
      note: e.note ?? null,
    })
  }

  return { members, present, arriving, departed, portraitFor, apply }
}

/** 排序档：在场 → 正在赶来 → 已离场（条上先看得到能用的人） */
function statusRank(member: TavernCastMember): number {
  if (member.status === 'active') return 0
  return member.status === 'arriving' ? 1 : 2
}
