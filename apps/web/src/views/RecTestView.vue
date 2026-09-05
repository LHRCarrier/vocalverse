<script setup lang="ts">
/**
 * ⚠️ 临时测试页（用完即删）：推荐系统引擎自测。
 *
 * 直接请求 /api/v1/recommendations（Python 8000，dev 下走 Vite 代理），
 * 方便联调 app/rec/service.py 的推荐规则与返回体。还原时删除本文件
 * 并撤掉 router/index.ts 里对应的 `rec-test` 路由即可。
 *
 * 鉴权两种方式：
 * - 默认：Bearer（已登录时 client.ts 自动携带 localStorage 的 vv_token）
 * - 测试头：Python 服务以 APP_TESTING=true 启动时传 X-Test-User-Id 免登录
 */
import { computed, ref } from 'vue'

import { request } from '@/api/client'

interface RecItem {
  id: number
  content_type: string
  title: string
  scene_type?: string | null
  diff_level: string
  mstatus: string
  tag_hit: number
}

const rtype = ref<'scene' | 'shadow'>('scene')
const limit = ref(6)
const authMode = ref<'bearer' | 'test-header'>('bearer')
const testUserId = ref('1')
const loading = ref(false)
const error = ref('')
const raw = ref<unknown>(null)
const items = ref<RecItem[]>([])

// Bearer 依赖登录态（localStorage.vv_token）；无 token 时选 Bearer 必然 401。
const hasToken = computed(() => !!localStorage.getItem('vv_token'))
const needTestHeader = computed(() => authMode.value === 'bearer' && !hasToken.value)

async function run(): Promise<void> {
  loading.value = true
  error.value = ''
  raw.value = null
  items.value = []
  const params = new URLSearchParams({ type: rtype.value, limit: String(limit.value) })
  const headers: Record<string, string> = {}
  if (authMode.value === 'test-header') headers['X-Test-User-Id'] = testUserId.value
  try {
    const resp = await request<{ type: string; items: RecItem[] }>(
      `/api/v1/recommendations?${params.toString()}`,
      { headers },
    )
    raw.value = resp
    items.value = resp.data.items
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    error.value = needTestHeader.value
      ? `${msg} —— 未检测到登录 token：请把「鉴权」切到 X-Test-User-Id 并填 user_id=1/2/3（当前后端 APP_TESTING=true 免登录）；或在 /login 登录后再用 Bearer。`
      : msg
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="rounded-[12px] border border-[#E5E7EB] bg-white p-6">
    <div
      class="mb-4 rounded-[8px] border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
    >
      ⚠️ 临时测试页（用完即删），仅用于联调推荐引擎。还原：删除本文件 + 撤掉
      <code>router/index.ts</code> 的 <code>rec-test</code> 路由。
    </div>

    <h1 class="mb-1 text-xl font-bold">推荐系统自测</h1>
    <p class="mb-5 text-sm text-[#667085]">
      GET /api/v1/recommendations → app/rec/service.py（曝光埋点 events.recommend_impression）
    </p>

    <div class="mb-4 flex flex-wrap items-end gap-3">
      <label class="flex flex-col gap-1 text-sm">
        类型
        <select v-model="rtype" class="rounded-[8px] border border-[#E5E7EB] px-3 py-1.5">
          <option value="scene">scene（场景，默认6）</option>
          <option value="shadow">shadow（影子跟读，默认3）</option>
        </select>
      </label>
      <label class="flex flex-col gap-1 text-sm">
        条数 limit
        <input v-model.number="limit" type="number" min="1" max="20" class="w-20 rounded-[8px] border border-[#E5E7EB] px-3 py-1.5">
      </label>
      <label class="flex flex-col gap-1 text-sm">
        鉴权
        <select v-model="authMode" class="rounded-[8px] border border-[#E5E7EB] px-3 py-1.5">
          <option value="bearer">Bearer（已登录 token）</option>
          <option value="test-header">X-Test-User-Id（APP_TESTING）</option>
        </select>
      </label>
      <label v-if="authMode === 'test-header'" class="flex flex-col gap-1 text-sm">
        user_id
        <input v-model="testUserId" class="w-20 rounded-[8px] border border-[#E5E7EB] px-3 py-1.5">
      </label>
      <button
        class="rounded-full bg-brand px-4 py-1.5 text-sm text-white transition-colors hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-60"
        :disabled="loading"
        @click="run"
      >
        {{ loading ? '请求中…' : '发起请求' }}
      </button>
    </div>

    <p
      v-if="needTestHeader"
      class="mb-4 rounded-[8px] border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800"
    >
      当前未检测到登录 token（<code>vv_token</code>），选 Bearer 会 401。请改为「X-Test-User-Id」并填
      <code>user_id=1/2/3</code>（当前后端 <code>APP_TESTING=true</code> 免登录）；或先到 /login 登录。
    </p>
    <p
      v-else-if="authMode === 'bearer'"
      class="mb-4 rounded-[8px] border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs text-emerald-800"
    >
      已登录：Bearer 会携带当前用户 token（user_id 为登录账号，非演示账号）。
    </p>

    <p v-if="error" class="mb-4 rounded-[8px] bg-red-50 px-4 py-2 text-sm text-red-700">✗ {{ error }}</p>

    <template v-if="items.length">
      <h2 class="mb-2 font-semibold">结果（{{ items.length }} 条）</h2>
      <table class="w-full border-collapse text-left text-sm">
        <thead>
          <tr class="border-b border-[#E5E7EB] text-[#667085]">
            <th class="py-2 pr-3 font-medium">id</th>
            <th class="py-2 pr-3 font-medium">title</th>
            <th class="py-2 pr-3 font-medium">scene_type</th>
            <th class="py-2 pr-3 font-medium">diff_level</th>
            <th class="py-2 pr-3 font-medium">mstatus</th>
            <th class="py-2 font-medium">tag_hit</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="it in items" :key="it.id" class="border-b border-[#F2F4F7]">
            <td class="py-2 pr-3">{{ it.id }}</td>
            <td class="py-2 pr-3">{{ it.title }}</td>
            <td class="py-2 pr-3">{{ it.scene_type ?? '—' }}</td>
            <td class="py-2 pr-3">{{ it.diff_level }}</td>
            <td class="py-2 pr-3">{{ it.mstatus }}</td>
            <td class="py-2">{{ it.tag_hit }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <details v-if="raw !== null" class="mt-4">
      <summary class="cursor-pointer text-sm text-brand-deep">原始响应 JSON</summary>
      <pre class="mt-2 overflow-auto rounded-[8px] bg-[#101828] p-4 text-xs text-green-300">{{ raw }}</pre>
    </details>
  </section>
</template>
