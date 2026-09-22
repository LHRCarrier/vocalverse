import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { buildQuickActions, useTavernSuggestions } from '@/composables/useTavernSuggestions'

describe('useTavernSuggestions · 动态推荐行动（docs/57 §3.2）', () => {
  it('无实体/无任务：通用三条常驻（观察/交谈/前进）', () => {
    const actions = buildQuickActions({})
    expect(actions.map((a) => a.kind)).toEqual(['observe', 'talk', 'advance'])
    expect(actions.map((a) => a.label)).toEqual(['观察四周', '交谈', '前进'])
    expect(actions[0]!.text).toBe('我仔细观察四周')
  })

  it('按场景/在场 NPC/进行中任务升级文案', () => {
    const actions = buildQuickActions({
      scene: '酒馆',
      present: [
        { name: '主角', kind: 'pc' },
        { name: '莉亚', kind: 'npc' },
      ],
      quests: [{ name: '寻找戒指', status: 'active' }],
    })
    expect(actions.map((a) => a.label)).toEqual(['观察酒馆', '与莉亚交谈', '推进寻找戒指'])
    expect(actions[1]!.text).toBe('我试着与莉亚交谈')
    expect(actions[2]!.text).toBe('我继续推进：寻找戒指')
  })

  it('最近 NPC：遭遇当前行动者优先；已结算任务不参与推进', () => {
    const actions = buildQuickActions({
      scene: '地城',
      present: [
        { name: '莉亚', kind: 'npc' },
        { name: '地精', kind: 'npc' },
      ],
      quests: [
        { name: '旧案', status: 'done' },
        { name: '逃出地城', status: 'active' },
      ],
      encounter: { currentName: '莉亚' },
    })
    expect(actions[1]!.label).toBe('与莉亚交谈')
    expect(actions[2]!.label).toBe('推进逃出地城')
  })

  it('useTavernSuggestions：依赖变化即刷新（场景/在场/任务）', () => {
    const scene = ref<string | null>('酒馆')
    const present = ref<Array<{ name: string; kind: 'pc' | 'npc' }>>([])
    const quests = ref<Array<{ name: string; status: string }>>([])
    const encounter = ref<{ currentName?: string | null } | null>(null)
    const actions = useTavernSuggestions({ scene, present, quests, encounter })

    expect(actions.value[0]!.label).toBe('观察酒馆')
    expect(actions.value[1]!.label).toBe('交谈')

    present.value = [{ name: '老陈', kind: 'npc' }]
    quests.value = [{ name: '找猫', status: 'active' }]
    expect(actions.value[1]!.label).toBe('与老陈交谈')
    expect(actions.value[2]!.label).toBe('推进找猫')

    scene.value = '后院'
    expect(actions.value[0]!.label).toBe('观察后院')
  })
})
