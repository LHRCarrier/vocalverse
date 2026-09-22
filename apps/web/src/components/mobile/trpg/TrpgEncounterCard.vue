<script setup lang="ts">
/**
 * 酒馆 · 遭遇卡（docs/56 §6）：第几轮 + 先攻序（当前行动者高亮）+ 参战者 HP。
 * 纯展示：数据来自 useTavernEncounter（encounter facts + 事件 / npc.*.hp）。
 */
import type { TavernEncounter, TavernParticipant } from '@/composables/useTavernEncounter'

const props = withDefaults(
  defineProps<{ encounter: TavernEncounter; participants?: TavernParticipant[] }>(),
  { participants: () => [] },
)
</script>

<template>
  <div class="t-enc" aria-label="遭遇战况">
    <div class="t-enc__head">
      <span class="t-enc__title">⚔ 遭遇战</span>
      <span class="t-enc__round">第 {{ props.encounter.round }} 轮</span>
      <span v-if="props.encounter.currentName" class="t-enc__turn">
        当前：{{ props.encounter.currentName }}
      </span>
    </div>
    <div class="t-enc__order">
      <template v-for="(member, i) in props.participants" :key="member.key">
        <span
          class="t-enc__pip"
          :class="{ 'is-current': member.current, 'is-npc': member.kind === 'npc' }"
          :title="`${member.name}${member.hp != null ? ` HP ${member.hp}` : ''}`"
        >
          <span class="t-enc__pip-name">{{ member.name }}</span>
          <span v-if="member.hp != null" class="t-enc__hp">HP {{ member.hp }}</span>
          <span v-else class="t-enc__hp t-enc__hp--none">—</span>
        </span>
        <span v-if="i < props.participants.length - 1" class="t-enc__sep" aria-hidden="true">›</span>
      </template>
    </div>
  </div>
</template>
