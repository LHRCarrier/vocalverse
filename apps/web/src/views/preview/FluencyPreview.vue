<script setup lang="ts">
/**
 * 流利度时间戳特征 · 联调测试台（docs/06 §9.3；test-only，可整体删除）。
 *
 * 链路：上传音频 → POST /api/v1/fluency-preview/analyze（后端真 ASR 词级时间戳
 * → compute_fluency_features → 参考文本非空时真 ISE 评分）→ 特征卡 + 词级时间轴 +
 * 停顿区间 + 「报告呈现」样张（按 lieflat-charts 报告模式 R09 × PORCELAIN 色值）。
 *
 * 依赖开关：后端 APP_FLUENCY_PREVIEW_ENABLED=true（services/python/.env，
 * gitignored；生产禁止开启，关闭时本页提示 404）。
 *
 * 删除清单：
 * 1. 删本文件 + `views/preview/registry.ts` 该行 + `router/preview.ts` 该路由；
 * 2. 删 `services/python/app/api/routes/fluency_preview.py` + `main.py` 注册两行
 *    + `config.py` 的 `fluency_preview_enabled` 一行；
 * 3. 收尾：pytest 全量 / pnpm typecheck / lint / build；契约快照零 diff。
 */
import { computed, onUnmounted, ref } from 'vue'
import { NAlert, NButton, NCheckbox, NInput, NTag } from 'naive-ui'

interface FluencyFeatures {
  word_count: number
  speech_s: number
  total_s: number
  wpm: number
  articulation_rate: number
  pause_count: number
  long_pause_count: number
  pause_total_s: number
  mean_pause_s: number
  max_pause_s: number
  pause_ratio: number
}

interface WordEntry {
  word: string
  start: number
  end: number
  probability: number
}

interface AnalyzeResult {
  text: string
  language: string
  words: WordEntry[]
  duration_s: number
  features: FluencyFeatures
  score: {
    overall: number
    pronunciation: number
    fluency: number
    grammar: number | null
  } | null
  /** ISE 评分参考来源：manual=题卡原文 / transcript=ASR 转写（转写对转写）/ null=未评分 */
  score_ref: 'manual' | 'transcript' | null
}

const file = ref<File | null>(null)
const reference = ref('')
/** 填了参考文本 → 题卡原文优先；否则勾选时用 ASR 转写喂 ISE（生产对话同款转写对转写）。 */
const useTranscriptRef = ref(true)
const loading = ref(false)
const error = ref<string | null>(null)
const result = ref<AnalyzeResult | null>(null)
/** 试听：选中后浏览器本地回放（ObjectURL，不上传；更换/卸载时 revoke 防泄漏）。 */
const previewUrl = ref<string | null>(null)

const fileLabel = computed(() => {
  if (!file.value) return null
  const kb = Math.round(file.value.size / 1024)
  return `${file.value.name} · ${kb} KB`
})

onUnmounted(() => {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
})

const PAUSE_THRESHOLD_S = 0.5

/** 词级时间轴：按有效说话段归一化定位（PORCELAIN 色值，见 vv-learning-report.html）。 */
const timeline = computed(() => {
  const f = result.value?.features
  if (!result.value || !f || f.speech_s <= 0) return []
  const span = f.speech_s
  return result.value.words.map((w, i) => {
    const prevEnd = i > 0 ? result.value!.words[i - 1].end : null
    const gap = prevEnd === null ? null : Math.max(0, w.start - prevEnd)
    return {
      ...w,
      gap,
      paused: gap !== null && gap >= PAUSE_THRESHOLD_S,
      left: `${((w.start - result.value!.words[0].start) / span) * 100}%`,
      width: `${Math.max(1.2, ((w.end - w.start) / span) * 100)}%`,
    }
  })
})

const pauseIntervals = computed(() => timeline.value.filter((w) => w.paused))

function onPick(e: Event) {
  const f = (e.target as HTMLInputElement).files?.[0] ?? null
  file.value = f
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = f ? URL.createObjectURL(f) : null
  error.value = null
}

async function analyze() {
  if (!file.value) {
    error.value = '请先选择录音文件（webm/wav/mp3，≤20MB）'
    return
  }
  loading.value = true
  error.value = null
  try {
    const form = new FormData()
    form.append('audio', file.value)
    if (reference.value.trim()) {
      form.append('reference', reference.value.trim())
    } else if (useTranscriptRef.value) {
      form.append('use_transcript_ref', 'true')
    }
    const resp = await fetch('/api/v1/fluency-preview/analyze', { method: 'POST', body: form })
    const body = (await resp.json()) as { code: number; message: string; data?: AnalyzeResult }
    if (!resp.ok || body.code !== 0 || !body.data) {
      throw new Error(body.message ?? `HTTP ${resp.status}`)
    }
    result.value = body.data
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

/** 演示数据（与后端 FakeASRClient 词表同源）：离线看版式用。 */
function fillDemo() {
  result.value = {
    text: 'hello, I would like a coffee, please.',
    language: 'en',
    duration_s: 3.2,
    words: [
      { word: 'hello', start: 0.1, end: 0.34, probability: 0.98 },
      { word: 'I', start: 0.42, end: 0.5, probability: 0.97 },
      { word: 'would', start: 0.58, end: 0.86, probability: 0.99 },
      { word: 'like', start: 0.94, end: 1.14, probability: 0.98 },
      { word: 'a', start: 1.22, end: 1.3, probability: 0.95 },
      { word: 'coffee,', start: 2.35, end: 2.72, probability: 0.99 },
      { word: 'please.', start: 2.8, end: 2.98, probability: 0.98 },
    ],
    features: {
      word_count: 7,
      speech_s: 2.88,
      total_s: 3.2,
      wpm: 145.83,
      articulation_rate: 229.51,
      pause_count: 1,
      long_pause_count: 1,
      pause_total_s: 1.05,
      mean_pause_s: 1.05,
      max_pause_s: 1.05,
      pause_ratio: 0.3646,
    },
    score: { overall: 90.9, pronunciation: 92.59, fluency: 87.7, grammar: null },
    score_ref: 'transcript',
  }
  error.value = null
}

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? '—' : v.toFixed(digits)
}

// ── PORCELAIN token（与 src/assets/lieflat/vv-learning-report.html 一致，未新增色值）──
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
</script>

<template>
  <div class="mx-auto max-w-[1280px]">
    <header class="mb-4">
      <h1 class="text-xl font-bold">流利度时间戳特征 · 联调测试台</h1>
      <p class="mt-1 text-sm text-[#667085]">
        ASR 词级时间戳 → 语速/停顿特征（docs/06 §9.3 辅助口径）→ 报告呈现样张
      </p>
    </header>

    <NAlert class="mb-4" type="info" :show-icon="false">
      <div class="space-y-1 text-xs leading-relaxed">
        <div>
          <NTag class="mr-2" size="small" :bordered="false">开关</NTag>
          后端 <code class="rounded bg-[#F0EFEB] px-1">APP_FLUENCY_PREVIEW_ENABLED=true</code>
          （<code class="rounded bg-[#F0EFEB] px-1">services/python/.env</code>，gitignored；
          生产禁止开启；关闭时路由 404、本页报错）
        </div>
        <div>
          <NTag class="mr-2" size="small" :bordered="false">链路</NTag>
          真 ASR（faster-whisper small · 词级时间戳）+ 真 ISE（参考文本非空时触发）；
          「参考文本」填题卡原文可复现「转写对转写」的发音对齐
        </div>
        <div>
          <NTag class="mr-2" size="small" :bordered="false">口径</NTag>
          语速 = 词数/(说话段/60)（排除首尾静默）；停顿 = 相邻词间隙 ≥0.5s（仅词间）；
          长停顿 ≥1.0s；暂停占比 = 停顿总时长/说话段
        </div>
      </div>
    </NAlert>

    <div class="mb-4 rounded-[16px] border border-[#E5E7EB] bg-white p-4">
      <div class="flex flex-wrap items-center gap-3">
        <input
          class="block w-72 text-sm file:mr-3 file:rounded-[8px] file:border-0 file:bg-[#F0EFEB] file:px-3 file:py-1.5 file:text-sm file:font-semibold file:text-[#081F5C]"
          type="file"
          accept="audio/*,.webm,.wav,.mp3"
          @change="onPick"
        >
        <NInput
          v-model:value="reference"
          class="w-72"
          placeholder="参考文本（留空 = 用转写对转写）"
        />
        <NCheckbox v-model:checked="useTranscriptRef" :disabled="!!reference.trim()">
          用 ASR 转写作为参考（转写对转写，与生产对话一致）
        </NCheckbox>
        <NButton type="primary" :loading="loading" @click="analyze">分析</NButton>
        <NButton secondary @click="fillDemo">演示数据（离线看版式）</NButton>
      </div>
      <div v-if="previewUrl" class="mt-3 flex flex-wrap items-center gap-3">
        <span class="text-xs text-[#667085]">{{ fileLabel }}</span>
        <audio :src="previewUrl" controls preload="none" class="h-9 max-w-[320px]" />
        <span class="text-[11px] text-[#98A2B3]">本地试听（浏览器回放，不上传）</span>
      </div>
      <p v-if="error" class="mt-2 text-xs text-[#B91C1C]">{{ error }}</p>
    </div>

    <template v-if="result">
      <!-- 特征卡（PORCELAIN KPI 风格） -->
      <div class="mb-4 rounded-[24px] p-5" :style="{ background: C.bg, color: C.txt }">
        <div class="mb-3 flex items-baseline justify-between border-b pb-2" :style="{ borderColor: C.txt }">
          <span class="text-sm font-extrabold tracking-[.2em]">FLUENCY FEATURES</span>
          <span class="text-[10px] font-semibold tracking-widest" :style="{ color: C.mut }">
            {{ result.words.length }} WORDS · {{ fmt(result.duration_s, 2) }}s AUDIO
          </span>
        </div>
        <div class="grid grid-cols-2 gap-4 md:grid-cols-4">
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">语速 WPM</div>
            <div class="text-3xl font-extrabold">{{ fmt(result.features.wpm) }}</div>
            <div class="text-[10px]" :style="{ color: C.mut }">词/分 · 说话段口径</div>
          </div>
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">纯发音速率</div>
            <div class="text-3xl font-extrabold">{{ fmt(result.features.articulation_rate) }}</div>
            <div class="text-[10px]" :style="{ color: C.mut }">词/分 · 去除停顿</div>
          </div>
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">停顿</div>
            <div class="text-3xl font-extrabold">
              {{ result.features.pause_count }}
              <span class="text-base font-bold" :style="{ color: C.data2 }"> 次</span>
            </div>
            <div class="text-[10px]" :style="{ color: C.mut }">
              长停顿 {{ result.features.long_pause_count }} · 最长 {{ fmt(result.features.max_pause_s) }}s
            </div>
          </div>
          <div>
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">停顿占比</div>
            <div class="text-3xl font-extrabold">{{ (result.features.pause_ratio * 100).toFixed(1) }}%</div>
            <div class="text-[10px]" :style="{ color: C.mut }">
              合计 {{ fmt(result.features.pause_total_s) }}s / 说话 {{ fmt(result.features.speech_s) }}s
            </div>
          </div>
        </div>

        <div class="mt-5 border-t border-dotted pt-4" :style="{ borderColor: C.faint }">
          <div class="mb-2 text-xs font-bold" :style="{ color: C.mut }">词级时间轴（宽度=词长，红=其后停顿 ≥0.5s）</div>
          <div
            class="relative h-9 overflow-hidden rounded-[8px]"
            :style="{ background: C.panel }"
          >
            <span
              v-for="(w, i) in timeline"
              :key="i"
              class="absolute top-1.5 h-6 rounded-[4px] px-1 text-[10px] font-bold leading-6"
              :style="{
                left: w.left,
                width: w.width,
                background: w.paused ? C.faintdata : C.data,
                color: w.paused ? '#081F5C' : C.bg,
              }"
            >{{ w.word }}</span>
          </div>
          <div
            v-if="pauseIntervals.length"
            class="mt-3 space-y-1 text-xs"
            :style="{ color: C.txt }"
          >
            <div v-for="(w, i) in pauseIntervals" :key="i">
              <b>停顿 {{ i + 1 }}</b>：{{ fmt(w.gap ?? 0) }}s（{{ w.word }} 前）—— {{ (w.gap ?? 0) >= 1 ? '长停顿：明显的卡壳/忘词信号' : '普通停顿：换气/组织语言' }}
            </div>
          </div>
          <div v-else class="mt-3 text-xs" :style="{ color: C.mut }">无 ≥0.5s 跨词停顿。</div>
        </div>
      </div>

      <!-- 报告呈现样张（lieflat R09 × PORCELAIN；与 ReportView 真实页同数据口径） -->
      <div class="mb-4 rounded-[24px] p-5" :style="{ background: C.bg, color: C.txt }">
        <div class="mb-4 flex items-baseline justify-between border-b pb-2" :style="{ borderColor: C.txt }">
          <span class="text-sm font-extrabold tracking-[.2em]">报告呈现 · 流利度维度</span>
          <span class="text-[10px] font-semibold tracking-widest" :style="{ color: C.mut }">
            按 lieflat-charts R09 × PORCELAIN（样张）
          </span>
        </div>
        <div class="grid grid-cols-3 gap-4">
          <div class="rounded p-3" :style="{ background: C.panel }">
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">流利度 · ISE</div>
            <div class="text-3xl font-extrabold">
              {{ result.score ? fmt(result.score.fluency) : '—' }}
            </div>
            <div class="mt-2 flex h-[10px] overflow-hidden">
              <span :style="{ width: `${Math.min(100, result.score ? result.score.fluency : 0)}%`, background: C.data }" />
            </div>
          </div>
          <div class="rounded p-3" :style="{ background: C.panel }">
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">语速（辅助）</div>
            <div class="text-3xl font-extrabold">{{ fmt(result.features.wpm) }}</div>
            <div class="text-[10px]" :style="{ color: C.mut }">≈ 词/分 · 慢于 110 可提示放慢节奏</div>
          </div>
          <div class="rounded p-3" :style="{ background: C.panel }">
            <div class="text-[10px] font-bold" :style="{ color: C.mut }">停顿（辅助）</div>
            <div class="text-3xl font-extrabold">
              {{ result.features.pause_count }} 次
            </div>
            <div class="text-[10px]" :style="{ color: C.mut }">
              最长 {{ fmt(result.features.max_pause_s) }}s · 占比 {{ (result.features.pause_ratio * 100).toFixed(1) }}%
            </div>
          </div>
        </div>
      </div>

      <!-- 明细：转写 / 词表 / ISE -->
      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div class="rounded-[16px] border border-[#E5E7EB] bg-white p-4 text-sm">
          <div class="mb-2 text-xs font-semibold text-[#667085]">转写（{{ result.language }}）</div>
          <p>{{ result.text }}</p>
          <div class="mt-3 mb-2 text-xs font-semibold text-[#667085]">词级时间戳</div>
          <table class="w-full text-xs">
            <thead>
              <tr class="text-left text-[#667085]">
                <th class="py-1">词</th>
                <th>start</th>
                <th>end</th>
                <th>间隔</th>
                <th>概率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(w, i) in result.words" :key="i" :class="w.start - (result.words[i - 1]?.end ?? w.start) >= PAUSE_THRESHOLD_S ? 'bg-[#FEF3C7]' : ''">
                <td class="py-1 font-semibold">{{ w.word }}</td>
                <td>{{ fmt(w.start, 2) }}</td>
                <td>{{ fmt(w.end, 2) }}</td>
                <td>{{ i ? fmt(Math.max(0, w.start - result.words[i - 1].end), 2) : '—' }}</td>
                <td>{{ fmt(w.probability, 2) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="rounded-[16px] border border-[#E5E7EB] bg-white p-4 text-sm">
          <div class="mb-2 text-xs font-semibold text-[#667085]">
            ISE 发音评分 ·
            {{
              result.score_ref === 'manual'
                ? '参考：题卡原文（手动填写）'
                : result.score_ref === 'transcript'
                  ? '参考：ASR 转写（转写对转写）'
                  : '未评分（填参考文本或勾选转写对转写）'
            }}
          </div>
          <template v-if="result.score">
            <div class="grid grid-cols-3 gap-3">
              <div>
                <div class="text-xs text-[#667085]">总体</div>
                <div class="text-xl font-bold text-[#081F5C]">{{ fmt(result.score.overall) }}</div>
              </div>
              <div>
                <div class="text-xs text-[#667085]">发音</div>
                <div class="text-xl font-bold">{{ fmt(result.score.pronunciation) }}</div>
              </div>
              <div>
                <div class="text-xs text-[#667085]">流利度</div>
                <div class="text-xl font-bold">{{ fmt(result.score.fluency) }}</div>
              </div>
            </div>
          </template>
          <p v-else class="text-xs text-[#667085]">无参考文本（评分降级）→ 不展示 ISE 分。</p>
          <div class="mt-4 mb-2 text-xs font-semibold text-[#667085]">口径说明</div>
          <ul class="list-inside list-disc space-y-1 text-xs text-[#667085]">
            <li>语速/停顿是 <b>辅助指标</b>；流利度权威分仍为 ISE fluency（docs/07 Q30）。</li>
            <li>首词前/末词后静默不计停顿（录音边沿噪声）。</li>
            <li>测试台默认「转写对转写」（与生产对话链路一致）；填了参考文本则题卡原文优先。</li>
            <li>
              数据落 <code>attempts.wpm</code> + <code>attempts.details.fluency</code>，报告经
              <code>metrics.attempts[].wpm / fluency_features</code> 透出。
            </li>
          </ul>
        </div>
      </div>
    </template>
  </div>
</template>
