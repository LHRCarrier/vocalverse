/**
 * 社区规范与使用条例页（docs/59）：条款结构是**审核判据的对外锚点**——
 * R1~R9 与 `JevHttpClient.CLAUSE_RULES` / `ModerationService.REASON_CODES` 一一对应，
 * 这个用例把「页面确实列出了全部条款号」钉死（改编号会红，而不是悄悄漂移成无效判据）。
 */
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileGuidelinesView from '@/views/mobile/MobileGuidelinesView.vue'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/guidelines', component: MobileGuidelinesView },
    { path: '/m/home', component: { template: '<div/>' } },
  ],
})

enableAutoUnmount(afterEach)

beforeEach(() => setActivePinia(createPinia()))

async function mountPage() {
  await router.push('/m/guidelines')
  await router.isReady()
  return mount(MobileGuidelinesView, { global: { plugins: [router] } })
}

describe('社区规范与使用条例（docs/59）', () => {
  it('列出 R1~R9 全部条款号与类别名（审核判据锚点）', async () => {
    const wrapper = await mountPage()
    const text = wrapper.text()
    const clauses: [string, string][] = [
      ['R1', '垃圾信息'],
      ['R2', '辱骂骚扰'],
      ['R3', '色情低俗'],
      ['R4', '暴力血腥'],
      ['R5', '涉政敏感'],
      ['R6', '广告引流'],
      ['R7', '版权侵权'],
      ['R8', '虚假信息'],
      ['R9', '其他违规'],
    ]
    for (const [code, title] of clauses) {
      expect(text).toContain(code)
      expect(text).toContain(title)
    }
  })

  it('披露处置口径：AI 只送审、处置由人工决定（透明性承诺）', async () => {
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain('AI 辅助筛选 + 人工复核')
    expect(wrapper.text()).toContain('最终处置由审核员决定')
  })

  it('包含使用条例 3.1~3.6 与申诉入口', async () => {
    const wrapper = await mountPage()
    const text = wrapper.text()
    for (const key of ['3.1', '3.2', '3.3', '3.4', '3.5', '3.6']) {
      expect(text).toContain(key)
    }
    expect(text).toContain('提交工单')
  })
})
