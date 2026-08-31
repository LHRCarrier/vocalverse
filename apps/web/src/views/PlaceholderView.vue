<script setup lang="ts">
import { defineProps } from 'vue'

const props = defineProps<{
  title: string
  desc?: string
}>()

void props
</script>

<template>
  <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-8">
    <h1 class="mb-2 text-xl font-bold">{{ title }}</h1>
    <p class="mb-4 text-sm text-[#667085]">{{ desc ?? '开发中' }}</p>
    <div class="rounded-[8px] bg-[#ECFDF5] px-4 py-3 text-sm text-brand-deep">
      该页面排期见 docs/04 里程碑；完成前由本占位页收敛路由，保证导航可用。
    </div>
  </section>
</template>
