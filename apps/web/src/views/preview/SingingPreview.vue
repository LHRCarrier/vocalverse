<script setup lang="ts">
/**
 * 唱歌评分 · 联调测试页（M3 唱歌 P0 全链路；test-only，可整体删除）。
 *
 * 流程：选歌（列表/详情 + 40905 就绪门禁）→ 整首录音（≤180s）→ 上传 →
 * 轮询任务态（queued→processing→done|failed）→ 逐句评分 + D3 对齐图 + 报告。
 * 依赖：Python 服务（app.sing 管线）+ Java 服务（歌曲/LRC 管理 + 提取状态委托），
 * 无独立开关（接口为正式 C 端契约，非 test-only——与本页配套的删除清单仅含前端三行）。
 *
 * 删除清单：
 * 1. 删本文件；`views/preview/registry.ts` 删除该行；`router/preview.ts` 删除该路由；
 * 2. 后端唱歌端点/管线为正式功能（docs/21 §2.1 op 20~24），不回滚；
 * 3. 收尾：pnpm lint / typecheck / test:run / build 全绿。
 */
import { nextTick, onMounted, ref } from 'vue'
import {
  NAlert,
  NButton,
  NCard,
  NProgress,
  NSelect,
  NSpace,
  NTag,
  NText,
} from 'naive-ui'

import { useSingPlay } from '@/composables/sing'
import { renderSingChart } from '@/lib/sing-chart'

const play = useSingPlay()

const selectedId = ref<number | null>(null)
const chartEl = ref<HTMLElement | null>(null)
const scoreColor = (v: number | null) => (v == null ? '#888' : v >= 85 ? '#18a058' : v >= 60 ? '#f2a43a' : '#d03050')

const songOptions = () =>
  play.songs.value.map((s) => ({
    label: `${s.title} · 就绪${s.pitch_ref_status === 'ready' ? '✓' : '✗'} · ${s.expected_lines} 句`,
    value: s.id,
  }))

async function onSelect(songId: number) {
  selectedId.value = songId
  await play.openSong(songId)
}

async function renderChart() {
  await nextTick()
  if (chartEl.value && play.detail.value && play.result.value) {
    renderSingChart(chartEl.value, play.detail.value, play.result.value)
  }
}

onMounted(async () => {
  await play.loadSongs()
  if (play.songs.value.length) {
    selectedId.value = play.songs.value[0].id
    await play.openSong(play.songs.value[0].id)
  }
})

defineExpose({ renderChart })
</script>

<template>
  <div style="max-width: 720px; margin: 0 auto; padding: 16px">
    <h2 style="margin: 0 0 8px">唱歌评分 · 联调测试台（M3 P0）</h2>
    <p style="color: #888; margin: 0 0 16px">
      选歌 → 整首跟唱（≤180s）→ 上传 → 轮询 → 逐句评分 + D3 对齐图。Fake 环境同样可跑
      （CI 零模型；评分为结构验证值）。错误码：40905 未就绪 / 41302 超长 / 42901 限流。
    </p>

    <NAlert v-if="play.error.value" type="error" :show-icon="false" style="margin-bottom: 12px">
      {{ play.error.value }}
    </NAlert>

    <NCard title="① 选歌" size="small" style="margin-bottom: 12px">
      <NSelect
        :value="selectedId"
        :options="songOptions()"
        placeholder="从已发布歌曲中选择（含就绪状态）"
        @update:value="(v: number) => onSelect(v)"
      />
      <div v-if="play.detail.value" style="margin-top: 10px">
        <NSpace>
          <NTag :type="play.detail.value.pitch_ref_status === 'ready' ? 'success' : 'warning'">
            {{ play.detail.value.pitch_ref_status }}
          </NTag>
          <NTag>预计 {{ play.detail.value.expected_lines }} 句</NTag>
          <NTag v-if="play.detail.value.bpm">BPM {{ play.detail.value.bpm }}</NTag>
        </NSpace>
      </div>
    </NCard>

    <NCard title="② 整首跟唱（≤180s）" size="small" style="margin-bottom: 12px">
      <NSpace align="center">
        <NButton
          type="primary"
          :disabled="play.phase.value === 'recording' || play.phase.value === 'processing'"
          @click="play.startRecording()"
        >
          {{ play.phase.value === 'recording' ? '录音中... 再点停止' : '开始跟唱' }}
        </NButton>
        <NButton
          v-if="play.phase.value === 'recording'"
          @click="play.cancelRecording()"
        >
          放弃重录
        </NButton>
        <NButton v-if="play.phase.value === 'idle' || play.phase.value === 'failed'" @click="play.retry()">
          重试
        </NButton>
        <NText depth="3">移动端注意：授权后 AudioContext resume；保持前台（iOS 锁屏断录）。</NText>
      </NSpace>
      <template v-if="play.phase.value === 'processing'">
        <NProgress
          :percentage="play.progressPct.value"
          :indicator-placement="'inside'"
          style="margin-top: 10px"
        />
        <NText depth="3">评分计算中...（约 10~30 秒，长歌约 1 分钟）</NText>
      </template>
    </NCard>

    <NCard v-if="play.result.value" title="③ 评分报告" size="small">
      <NSpace align="center" style="margin-bottom: 8px">
        <NTag type="success" size="large">综合 {{ play.result.value.overall?.toFixed(1) ?? '—' }}</NTag>
        <NTag>音准 {{ play.result.value.pitch?.toFixed(1) ?? '—' }}</NTag>
        <NTag>节奏 {{ play.result.value.rhythm?.toFixed(1) ?? '—' }}</NTag>
        <NTag>发音 {{ play.result.value.pron?.toFixed(1) ?? '—' }}</NTag>
        <NTag v-if="!play.result.value.is_complete" type="warning">
          未评测 {{ play.result.value.expected_lines - play.result.value.lines.filter((l) => !l.skipped).length }} 句
        </NTag>
      </NSpace>
      <div ref="chartEl" style="width: 100%; height: 150px; margin: 8px 0" />
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px 16px">
        <div v-for="(l, i) in play.result.value.lines" :key="l.seq" style="display: flex; justify-content: space-between">
          <span style="color: #888">{{ i + 1 }}. {{ l.skipped ? `未评测(${l.reason ?? 'skipped'})` : '完成' }}</span>
          <span>
            <span :style="{ color: scoreColor(l.pitch_score) }">音准{{ l.pitch_score?.toFixed(0) ?? '—' }}</span>
            <span style="margin-left: 8px; color: #888">节奏{{ l.rhythm_score?.toFixed(0) ?? '—' }}</span>
          </span>
        </div>
      </div>
      <NAlert type="info" style="margin-top: 8px">
        发音 = 抽样句评分（默认前 3 句，APP_SING_PRON_SAMPLES 可调）；alignment:
        {{ JSON.stringify(play.result.value.alignment) }}
      </NAlert>
      <div style="margin-top: 8px">
        <NButton size="small" @click="renderChart">重绘 D3 图</NButton>
        <NButton size="small" style="margin-left: 8px" @click="play.reset()">再来一遍</NButton>
      </div>
    </NCard>
  </div>
</template>
