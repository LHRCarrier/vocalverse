<script setup lang="ts">
/**
 * 影子跟读 · 联调测试台（DoD ④；test-only，可整体删除）。
 *
 * 流程：选素材 → 听示范（edge-tts）→ 录音跟读 → 三维评分（发音/语速匹配/停顿密度
 * + 整体，app/practice/shadow.py 同款口径）→ 下一句。
 * 后端：GET /materials、POST /tts、POST /analyze（test-only，见 shadow_preview.py）。
 * 依赖开关：APP_SHADOW_PREVIEW_ENABLED=true（services/python/.env，gitignored；
 * 生产禁止开启，关闭时接口 404、本页报错）。
 *
 * 删除清单：
 * 1. 删本文件 + `views/preview/registry.ts` 该行 + `router/preview.ts` 该路由；
 * 2. 删 `services/python/app/api/routes/shadow_preview.py` + `main.py` 注册两行
 *    + `config.py` 的 `shadow_preview_enabled` 一行；
 * 3. 收尾：pytest 全量 / pnpm typecheck / lint / build；契约快照零 diff。
 */
import { computed, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NSelect, NTag } from 'naive-ui'

import { VoiceRecorder, micErrorMessage } from '@/audio/recorder'

interface Material {
  id: number
  title: string
  level: number
  wpm: number | null
  duration_s: number | null
  text_content: string
  sentence_count: number
}

interface ShadowResult {
  material: { id: number; title: string; wpm: number | null }
  sentence: string
  transcript: string
  shadow: {
    pron: number | null
    speed_match: number | null
    pause_score: number | null
    overall: number | null
    user_wpm: number | null
    ref_wpm: number | null
  }
  coach: string | null
  features: Record<string, number>
  ise: { overall: number; pron: number; flu: number; word_level: Array<{ word: string; score: number; error_type: string }> } | null
}

const materials = ref<Material[]>([])
const materialId = ref<number | null>(null)
const sentenceIndex = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)
const recording = ref(false)
const result = ref<ShadowResult | null>(null)
const demoUrl = ref<string | null>(null)

const sentences = computed(() => {
  const m = materials.value.find((x) => x.id === materialId.value)
  return m ? m.text_content.split('\n').filter((s) => s.trim()) : []
})
const currentSentence = computed(() => sentences.value[sentenceIndex.value] ?? null)

const recorder = new VoiceRecorder()
recorder.onStateChange = (s) => {
  recording.value = s === 'recording'
}

async function loadMaterials() {
  loading.value = true
  error.value = null
  try {
    const resp = await fetch('/api/v1/shadow-preview/materials')
    const body = (await resp.json()) as { code: number; message: string; data?: Material[] }
    if (!resp.ok || body.code !== 0 || !body.data) throw new Error(body.message ?? `HTTP ${resp.status}`)
    materials.value = body.data
    if (body.data.length && materialId.value === null) materialId.value = body.data[0].id
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}
loadMaterials()

function pickSentence() {
  sentenceIndex.value = 0
  result.value = null
  stopDemo()
}

async function playDemo() {
  const text = currentSentence.value
  if (!text) return
  stopDemo()
  error.value = null
  try {
    const resp = await fetch('/api/v1/shadow-preview/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
    if (!resp.ok) throw new Error(`示范合成失败（HTTP ${resp.status}）`)
    const blob = await resp.blob()
    demoUrl.value = URL.createObjectURL(blob)
    const audio = new Audio(demoUrl.value)
    audio.onended = () => stopDemo()
    await audio.play()
  } catch (e) {
    error.value = (e as Error).message
  }
}

function stopDemo() {
  if (demoUrl.value) {
    URL.revokeObjectURL(demoUrl.value)
    demoUrl.value = null
  }
}

async function startRecord() {
  error.value = null
  try {
    await recorder.start(60_000)
  } catch (e) {
    error.value = micErrorMessage(e)
  }
}

function stopRecord() {
  if (!recording.value) return
  recorder.stop()
}

function recordAndSubmit() {
  recorder.onStop = (blob: Blob) => {
    recorder.onStop = null
    void analyze(blob)
  }
  void startRecord()
}

async function analyze(blob: Blob) {
  if (materialId.value === null) return
  loading.value = true
  error.value = null
  try {
    const form = new FormData()
    form.append('audio', blob, 'shadow.webm')
    form.append('material_id', String(materialId.value))
    form.append('sentence_index', String(sentenceIndex.value))
    const resp = await fetch('/api/v1/shadow-preview/analyze', { method: 'POST', body: form })
    const body = (await resp.json()) as { code: number; message: string; data?: ShadowResult }
    if (!resp.ok || body.code !== 0 || !body.data) throw new Error(body.message ?? `HTTP ${resp.status}`)
    result.value = body.data
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function nextSentence() {
  if (sentenceIndex.value + 1 < sentences.value.length) {
    sentenceIndex.value += 1
    result.value = null
  }
}

onUnmounted(() => {
  stopDemo()
  recorder.cancel()
})

// ── PORCELAIN token（与 lieflat vv-learning-report.html 一致）──
const C = {
  bg: '#F7F2EB',
  txt: '#081F5C',
  data: '#334EAC',
  data2: '#7096D1',
  faintdata: '#BAD6EB',
  panel: 'rgba(8,31,92,.045)',
  mut: 'rgba(8,31,92,.60)',
  faint: 'rgba(8,31,92,.32)',
}

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits)
}
</script>

<template>
  <div class="mx-auto max-w-[1280px]">
    <header class="mb-4">
      <h1 class="text-xl font-bold">影子跟读 · 联调测试台</h1>
      <p class="mt-1 text-sm text-[#667085]">
        素材 → 示范 → 跟读 → 三维评分（发音 / 语速匹配 / 停顿密度，docs/06 §9.3）
      </p>
    </header>

    <NAlert class="mb-4" type="info" :show-icon="false">
      <div class="space-y-1 text-xs leading-relaxed">
        <div>
          <NTag class="mr-2" size="small" :bordered="false">开关</NTag>
          后端 <code class="rounded bg-[#F0EFEB] px-1">APP_SHADOW_PREVIEW_ENABLED=true</code>
          （<code class="rounded bg-[#F0EFEB] px-1">services/python/.env</code>；生产禁止开启）
        </div>
        <div>
          <NTag class="mr-2" size="small" :bordered="false">口径</NTag>
          发音 = ISE accuracy；语速匹配 = 用户 wpm vs 素材原声 wpm（≤10% 偏差 95 分档）；
          停顿密度 = pause_ratio 越低越好；整体 = 0.4/0.3/0.3 加权；素材缺 wpm 则该维不展示
        </div>
      </div>
    </NAlert>

    <div class="mb-4 rounded-[16px] border border-[#E5E7EB] bg-white p-4">
      <div class="flex flex-wrap items-center gap-3">
        <NSelect
          v-model:value="materialId"
          class="w-96"
          :options="
            materials.map((m) => ({
              label: `${m.title}（L${m.level}${m.wpm ? ` · 原声 ${m.wpm} wpm` : ''} · ${m.sentence_count} 句）`,
              value: m.id,
            }))
          "
          @update:value="pickSentence"
        />
        <NButton secondary :loading="loading" @click="loadMaterials">刷新素材</NButton>
      </div>

      <template v-if="currentSentence">
        <div class="mt-4 rounded-[12px] p-4" :style="{ background: C.bg, color: C.txt }">
          <div class="text-[10px] font-bold tracking-widest" :style="{ color: C.mut }">
            第 {{ sentenceIndex + 1 }} / {{ sentences.length }} 句 · 跟读原文
          </div>
          <div class="mt-1 text-lg font-bold">{{ currentSentence }}</div>
          <div class="mt-3 flex flex-wrap items-center gap-2">
            <NButton size="small" type="primary" :loading="loading" @click="playDemo">🔊 听示范</NButton>
            <NButton size="small" :type="recording ? 'error' : 'default'" @click="recording ? stopRecord() : recordAndSubmit()">
              {{ recording ? '■ 停止并提交评分' : '🎙 录音跟读（提交评分）' }}
            </NButton>
            <NButton size="small" secondary :disabled="sentenceIndex + 1 >= sentences.length" @click="nextSentence">
              下一句 →
            </NButton>
          </div>
        </div>
        <p v-if="error" class="mt-2 text-xs text-[#B91C1C]">{{ error }}</p>
      </template>
      <p v-else-if="!materials.length && !loading" class="mt-2 text-xs text-[#667085]">
        无已发布素材：请先跑 seed（<code>uv run python -m app.db.seed</code>）或由 Java 管理端上架。
      </p>
    </div>

    <template v-if="result">
      <div class="mb-4 rounded-[24px] p-5" :style="{ background: C.bg, color: C.txt }">
        <div class="mb-3 flex items-baseline justify-between border-b pb-2" :style="{ borderColor: C.txt }">
          <span class="text-sm font-extrabold tracking-[.2em]">SHADOW SCORE · 三维评分</span>
          <span class="text-[10px] font-semibold tracking-widest" :style="{ color: C.mut }">
            整体 {{ result.shadow.overall ?? '—' }} 分
          </span>
        </div>
        <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">发音 · ISE</div>
            <div class="text-3xl font-extrabold">{{ fmt(result.shadow.pron) }}</div>
          </div>
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">语速匹配</div>
            <div class="text-3xl font-extrabold">{{ fmt(result.shadow.speed_match) }}</div>
            <div class="text-[10px]" :style="{ color: C.mut }">
              {{ fmt(result.shadow.user_wpm) }} vs {{ result.shadow.ref_wpm ?? '素材无' }} wpm
            </div>
          </div>
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">停顿密度</div>
            <div class="text-3xl font-extrabold">{{ fmt(result.shadow.pause_score) }}</div>
            <div class="text-[10px]" :style="{ color: C.mut }">
              占比 {{ ((result.features.pause_ratio ?? 0) * 100).toFixed(1) }}%
            </div>
          </div>
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">整体</div>
            <div class="text-3xl font-extrabold">{{ result.shadow.overall ?? '—' }}</div>
          </div>
        </div>
        <div class="mt-4 border-t border-dotted pt-3 text-sm" :style="{ borderColor: C.faint }">
          <b>教练笔记</b>：{{ result.coach ?? '—' }}
        </div>
      </div>

      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div class="rounded-[16px] border border-[#E5E7EB] bg-white p-4 text-sm">
          <div class="mb-2 text-xs font-semibold text-[#667085]">转写与特征</div>
          <p class="text-sm">{{ result.transcript || '—（未识别到语音）' }}</p>
          <div class="mt-2 grid grid-cols-3 gap-2 text-xs text-[#667085]">
            <div>wpm：{{ fmt(result.shadow.user_wpm) }}</div>
            <div>停顿：{{ result.features.pause_count ?? 0 }} 次</div>
            <div>最长：{{ fmt(result.features.max_pause_s) }}s</div>
          </div>
        </div>
        <div class="rounded-[16px] border border-[#E5E7EB] bg-white p-4 text-sm">
          <div class="mb-2 text-xs font-semibold text-[#667085]">ISE 明细（题卡原文参考）</div>
          <p v-if="result.ise" class="text-sm">
            总体 {{ fmt(result.ise.overall) }} · 发音 {{ fmt(result.ise.pron) }} · 流利度 {{ fmt(result.ise.flu) }}
          </p>
          <p v-else class="text-xs text-[#667085]">无转写/评分降级 → 不展示。</p>
        </div>
      </div>
    </template>
  </div>
</template>
