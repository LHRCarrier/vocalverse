<script setup lang="ts">
/**
 * 逐句音准对齐图（docs/06 §9.4 / docs/13 §4）：用户音高轮廓 vs 参考旋律。
 * 全项目唯一 D3 落点——动态 import('d3')、卸载清理、失败降级 CSS 提示。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'

import { tokens } from '@/styles/tokens'

const props = withDefaults(
  defineProps<{
    reference: number[]
    user: number[]
    height?: number
  }>(),
  { height: 240 },
)

const el = ref<HTMLElement | null>(null)
const failed = ref(false)
let cleanup: (() => void) | null = null

onMounted(async () => {
  const node = el.value
  if (!node || props.reference.length === 0) {
    failed.value = true
    return
  }
  try {
    const d3 = await import('d3')
    let observer: ResizeObserver | null = null

    const render = () => {
      node.replaceChildren()
      const width = Math.max(node.clientWidth, 280)
      const height = props.height
      const margin = { top: 12, right: 14, bottom: 24, left: 32 }
      const innerW = width - margin.left - margin.right
      const innerH = height - margin.top - margin.bottom

      const all = [...props.reference, ...props.user]
      const x = d3
        .scaleLinear()
        .domain([0, Math.max(props.reference.length - 1, 1)])
        .range([0, innerW])
      const y = d3
        .scaleLinear()
        .domain([Math.min(...all) - 6, Math.max(...all) + 6])
        .range([innerH, 0])

      const gen = d3
        .line<number>()
        .x((_d, i) => x(i))
        .y((d) => y(d))

      const svg = d3.select(node).append('svg').attr('width', width).attr('height', height)
      const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`)

      g.append('path')
        .datum(props.reference)
        .attr('fill', 'none')
        .attr('stroke', tokens.colors.brand)
        .attr('stroke-width', 2.5)
        .attr('d', gen)

      g.append('path')
        .datum(props.user)
        .attr('fill', 'none')
        .attr('stroke', tokens.colors.score)
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', '4 4')
        .attr('d', gen)

      g.append('g')
        .selectAll('circle')
        .data(props.user)
        .join('circle')
        .attr('cx', (_d, i) => x(i))
        .attr('cy', (d) => y(d))
        .attr('r', 3)
        .attr('fill', tokens.colors.score)

      g.append('g')
        .attr('transform', `translate(0,${innerH})`)
        .call(d3.axisBottom(x).ticks(Math.min(props.reference.length - 1, 6)).tickFormat(() => ''))
      g.append('g').call(d3.axisLeft(y).ticks(4))
    }

    render()
    observer = new ResizeObserver(() => render())
    observer.observe(node)
    cleanup = () => {
      observer?.disconnect()
      observer = null
      node.replaceChildren()
    }
  } catch {
    failed.value = true
  }
})

onBeforeUnmount(() => cleanup?.())
</script>

<template>
  <div>
    <div class="mb-2 flex items-center gap-4 text-xs text-[#667085]">
      <span class="flex items-center gap-1">
        <span class="inline-block h-0.5 w-4 rounded-full bg-brand" />参考旋律
      </span>
      <span class="flex items-center gap-1">
        <span class="inline-block h-0.5 w-4 rounded-full bg-score" />你的音高
      </span>
    </div>
    <div ref="el" class="w-full" :style="{ height: `${height}px` }" />
    <p v-if="failed" class="mt-2 rounded-[8px] bg-[#FEF2F2] px-3 py-2 text-xs text-[#B91C1C]">
      音高对齐图加载失败（依赖未就绪），已降级为文字提示。
    </p>
  </div>
</template>