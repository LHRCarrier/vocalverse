<script setup lang="ts">
/**
 * Placement Lab · 入学测试联调测试台（团队测试用，AGENTS.md rule 3 前后端联动新功能强制项）。
 *
 * 能力：① 一键用 Fake 客户端跑完整入学测试（两维综合分 → 档位）并展示逐题明细
 *       ② 查看指定用户的当前档位/复测冷却
 * 依赖：后端 `/api/v1/placement-lab/*`（test-only，默认关闭；开启 = APP_PLACEMENT_LAB_ENABLED=true）。
 * 删除无影响：本文件 + registry.ts 一行 + router/preview.ts 一行（dev-only，生产零体积）。
 */
import { ref } from 'vue'
import { NAlert, NButton, NCard, NCode, NInputNumber, NTag } from 'naive-ui'

const PYTHON = import.meta.env.VITE_PYTHON_BASE ?? ''

const userId = ref(1)
const errorMsg = ref('')
const loading = ref(false)
const runResult = ref<Record<string, unknown> | null>(null)
const statusResult = ref<Record<string, unknown> | null>(null)

async function post(path: string) {
  const resp = await fetch(`${PYTHON}/api/v1/placement-lab${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  const json = await resp.json()
  if (!resp.ok || json.code !== 0) throw new Error(json.message ?? `HTTP ${resp.status}`)
  return json.data
}

async function runPlacement() {
  loading.value = true
  errorMsg.value = ''
  try {
    runResult.value = await post(`/run?user_id=${userId.value}`)
  } catch (e) {
    errorMsg.value = String(e)
  } finally {
    loading.value = false
  }
}

async function fetchStatus() {
  errorMsg.value = ''
  try {
    const resp = await fetch(`${PYTHON}/api/v1/placement-lab/status?user_id=${userId.value}`)
    const json = await resp.json()
    if (!resp.ok || json.code !== 0) throw new Error(json.message ?? `HTTP ${resp.status}`)
    statusResult.value = json.data
  } catch (e) {
    errorMsg.value = String(e)
  }
}

function fmt(v: unknown) {
  return v == null ? '—' : typeof v === 'number' ? Math.round(v) : String(v)
}
</script>

<template>
  <div class="mx-auto max-w-5xl p-6">
    <header class="mb-4">
      <h1 class="text-xl font-bold">Placement Lab · 入学测试联调测试台</h1>
      <p class="text-sm text-[#667085]">
        本页用 Fake 客户端（APP_TESTING）跑完整入学测试，复现两维综合分 S=0.6·发音+0.4·流利度 → L1~L4。
        后端 test-only 路由默认关闭 —— 开启需 <code>APP_PLACEMENT_LAB_ENABLED=true</code>。
        删除 = 删除本页 + 注册行 + 路由文件，零副作用。
      </p>
    </header>

    <NAlert v-if="errorMsg" type="error" class="mb-4" :show-icon="true">{{ errorMsg }}</NAlert>

    <NCard class="mb-4">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <NInputNumber v-model:value="userId" :min="1" :step="1" />
        <NButton type="primary" :loading="loading" @click="runPlacement">跑一次入学测试 →</NButton>
        <NButton quaternary @click="fetchStatus">查看档位/复测资格</NButton>
      </div>
      <p class="text-xs text-[#667085]">
        说明：read 题走 ISE（发音/流利度/完整度）+LLM 语法；qa 题只 ASR（+语法诊断）；语法不进 S（C1），
        completeness 缺失时 F 仅用 flu（local/20，禁混 0）。
      </p>
    </NCard>

    <NCard v-if="runResult" class="mb-4" title="本次测试结果" size="small">
      <div class="flex flex-wrap items-center gap-3">
        <NTag size="small" type="info">user {{ runResult.user_id }}</NTag>
        <NTag size="small" type="success">档位 {{ runResult.level }}</NTag>
        <NTag size="small">综合分 {{ fmt(runResult.total_score) }}</NTag>
        <NTag size="small">发音 {{ fmt(runResult.pron) }}</NTag>
        <NTag size="small">流利 {{ fmt(runResult.flu) }}</NTag>
        <NTag size="small">语法(诊断) {{ fmt(runResult.gram) }}</NTag>
        <NTag size="small">卷 {{ runResult.exam_revision }}</NTag>
      </div>
      <p class="mt-3 text-sm"><b>逐题明细：</b></p>
      <NCode
        :code="JSON.stringify((runResult.items as unknown[] | undefined) ?? [], null, 2)"
        language="json"
        word-wrap
      />
    </NCard>

    <NCard v-if="statusResult" title="当前档位 / 复测资格" size="small">
      <div class="flex flex-wrap items-center gap-3">
        <NTag size="small" type="info">user {{ statusResult.user_id }}</NTag>
        <NTag size="small" :type="statusResult.has_completed ? 'success' : 'default'">
          {{ statusResult.has_completed ? '已定档' : '未定档' }}
        </NTag>
        <NTag size="small" :type="Number(statusResult.cooldown_remaining_days) > 0 ? 'warning' : 'success'">
          冷却 {{ statusResult.cooldown_remaining_days }} 天
        </NTag>
        <NTag size="small">档位 {{ statusResult.current_level ?? '—' }}</NTag>
      </div>
    </NCard>
  </div>
</template>
