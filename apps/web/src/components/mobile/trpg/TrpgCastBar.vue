<script setup lang="ts">
/**
 * 酒馆 · 在场角色条（docs/56 §6）：头像 + 名字横滑。
 * arriving 显示脉冲「正在赶来…」；departed 置灰；点头像上抛 select（开立绘展台）。
 * 立绘 URL 由 useTavernCast 解析（实体挂图 → 内置素材 → 首字占位）。
 */
import type { TavernCastMember } from '@/composables/useTavernCast'

const props = withDefaults(defineProps<{ members?: TavernCastMember[] }>(), {
  members: () => [],
})

const emit = defineEmits<{ select: [member: TavernCastMember] }>()

function titleOf(member: TavernCastMember): string {
  if (member.status === 'arriving') return `${member.name} 正在赶来…`
  if (member.status === 'departed') return `${member.name}（已离场）`
  return `查看 ${member.name} 立绘`
}
</script>

<template>
  <div v-if="props.members.length" class="t-cast" aria-label="在场角色">
    <button
      v-for="member in props.members"
      :key="member.name"
      class="t-cast__item"
      :class="[`is-${member.status}`, `t-cast__item--${member.kind}`]"
      type="button"
      :title="titleOf(member)"
      @click="emit('select', member)"
    >
      <span class="t-cast__ava" aria-hidden="true">
        <img v-if="member.portraitUrl" :src="member.portraitUrl" alt="">
        <template v-else>{{ member.name.slice(0, 1) }}</template>
      </span>
      <span class="t-cast__name">{{ member.name }}</span>
      <span v-if="member.status === 'arriving'" class="t-cast__note">正在赶来…</span>
      <span v-else-if="member.status === 'departed'" class="t-cast__note">已离场</span>
    </button>
  </div>
</template>
