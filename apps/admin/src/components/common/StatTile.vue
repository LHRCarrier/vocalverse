<script setup lang="ts">
/**
 * 统计块（工作台与各总览页的 KPI）。
 * 刻意不做迷你趋势线——总览页的趋势交给专门的 F2/F3 图，
 * 一个数字块里塞一根没有坐标的线会让读者以为读到了趋势（lieflat §7 拒绝装饰性编码）。
 */
withDefaults(
  defineProps<{
    label: string
    value: string | number
    unit?: string
    /** 次要说明（口径、对比期）——必须写清楚，别让读者猜 */
    hint?: string
    /** 状态色：正常留空 */
    tone?: 'ok' | 'warn' | 'danger' | 'info'
    loading?: boolean
  }>(),
  { unit: undefined, hint: undefined, tone: undefined, loading: false },
)
</script>

<template>
  <div class="c-stat">
    <div class="c-stat-label">{{ label }}</div>
    <div class="c-stat-value" :class="tone ? `c-stat-value--${tone}` : undefined">
      <template v-if="loading">—</template>
      <template v-else>
        {{ value }}<span v-if="unit" class="c-stat-unit">{{ unit }}</span>
      </template>
    </div>
    <div v-if="hint" class="c-stat-delta">{{ hint }}</div>
  </div>
</template>

<style scoped>
.c-stat-value--ok {
  color: var(--c-ok);
}
.c-stat-value--warn {
  color: var(--c-warn);
}
.c-stat-value--danger {
  color: var(--c-danger);
}
.c-stat-value--info {
  color: var(--c-primary);
}
</style>
