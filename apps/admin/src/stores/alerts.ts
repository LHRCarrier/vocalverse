import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { opsApi } from '@/api'
import type { AlertEvent, DependencyItem } from '@/api'

/**
 * 预警/服务健康 store（docs/50 §11.3 顶栏角标 + §6.3）。
 *
 * 为什么是轮询而不是 SSE：控制台是低频人工场景，docs/49 已记录 SSE 的四处坑
 * （ADR 限定 / nginx 四件套 / Tomcat asyncTimeout / 兜底轮询），
 * 为"预警秒级"付这个代价不划算（docs/50 §15.1）。
 *
 * 失败静默：角标拉不到不该弹错误——运维页自己会展示明确错误。
 */
const POLL_MS = 30_000

export const useAlertStore = defineStore('console-alerts', () => {
  const events = ref<AlertEvent[]>([])
  /** 依赖项来自 `/ops/services` 的 `items`——该端点返回对象，不是数组（ops.py:115-121） */
  const probes = ref<DependencyItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  const firing = computed(() => events.value.filter((e) => e.status === 'firing').length)
  const critical = computed(
    () => events.value.filter((e) => e.status === 'firing' && e.severity === 'critical').length,
  )
  const unhealthy = computed(() => probes.value.filter((p) => !p.ok).length)

  async function refresh(): Promise<void> {
    loading.value = true
    try {
      const page = await opsApi.listEvents({ status: 'firing', page_size: 50 })
      events.value = page.items
      error.value = null
    } catch (err) {
      error.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function refreshProbes(): Promise<void> {
    try {
      probes.value = (await opsApi.services()).items
    } catch {
      // 探测失败本身可能是"服务不可用"——保留上一次结果，不覆盖成空
    }
  }

  function start(): void {
    if (timer) return
    void refresh()
    void refreshProbes()
    timer = setInterval(() => {
      void refresh()
      void refreshProbes()
    }, POLL_MS)
  }

  function stop(): void {
    if (timer) clearInterval(timer)
    timer = null
  }

  return { events, probes, loading, error, firing, critical, unhealthy, refresh, refreshProbes, start, stop }
})
