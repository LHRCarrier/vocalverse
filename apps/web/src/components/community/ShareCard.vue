<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, useMessage } from 'naive-ui'

import { tokens } from '@/styles/tokens'

const props = defineProps<{
  score: number
  dimensions: Array<{ label: string; value: number }>
}>()

const message = useMessage()
const canvasEl = ref<HTMLCanvasElement | null>(null)

function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const w = 600
  const h = 300 + props.dimensions.length * 34
  canvas.width = w
  canvas.height = h
  ctx.clearRect(0, 0, w, h)

  ctx.fillStyle = tokens.colors.card
  ctx.fillRect(0, 0, w, h)

  ctx.fillStyle = tokens.colors.brand
  ctx.fillRect(0, 0, w, 64)
  ctx.fillStyle = tokens.colors.card
  ctx.font = 'bold 22px system-ui, sans-serif'
  ctx.fillText('VocalVerse 声语界 · 成绩卡', 24, 42)

  ctx.fillStyle = tokens.colors.text
  ctx.font = 'bold 56px system-ui, sans-serif'
  ctx.fillText(String(props.score), 24, 150)
  ctx.fillStyle = tokens.colors.textSecondary
  ctx.font = '16px system-ui, sans-serif'
  ctx.fillText('综合得分', 24, 182)

  let y = 224
  for (const d of props.dimensions) {
    ctx.fillStyle = tokens.colors.textSecondary
    ctx.font = '14px system-ui, sans-serif'
    ctx.fillText(d.label, 24, y)
    ctx.fillStyle = tokens.colors.border
    ctx.fillRect(94, y - 12, 388, 12)
    ctx.fillStyle = tokens.colors.score
    ctx.fillRect(94, y - 12, 388 * Math.min(1, d.value / 100), 12)
    ctx.fillStyle = tokens.colors.text
    ctx.fillText(String(d.value), 492, y)
    y += 34
  }
}

async function download() {
  const canvas = canvasEl.value
  if (!canvas) return
  const a = document.createElement('a')
  a.href = canvas.toDataURL('image/png')
  a.download = 'vocalverse-score.png'
  a.click()
  message.success('图片已下载')
}

async function share() {
  const canvas = canvasEl.value
  if (!canvas) return
  try {
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob((b) => resolve(b), 'image/png'),
    )
    const file =
      blob && blob.size > 0
        ? new File([blob], 'vocalverse-score.png', { type: 'image/png' })
        : null
    if (file && navigator.share && navigator.canShare?.({ files: [file] })) {
      await navigator.share({
        title: 'VocalVerse 成绩卡',
        text: `我的综合得分 ${props.score}`,
        files: [file],
      })
      return
    }
    await navigator.clipboard.writeText(`VocalVerse 综合得分 ${props.score}`)
    message.success('已复制分享文案')
  } catch (e) {
    message.error((e as Error).message)
  }
}

onMounted(draw)
</script>

<template>
  <div>
    <canvas
      ref="canvasEl"
      class="w-full rounded-[12px] border border-[#E5E7EB] bg-white"
    />
    <div class="mt-3 flex gap-2">
      <NButton size="small" round type="primary" @click="download">下载图片</NButton>
      <NButton size="small" round secondary @click="share">分享</NButton>
    </div>
  </div>
</template>