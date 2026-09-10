import { h, ref } from 'vue'
import { NInput, NSelect } from 'naive-ui'
import type { DialogApi, DialogOptions, MessageApi } from 'naive-ui'

import { consoleApi } from '@/api'
import type { TicketRow, TicketStatus } from '@/api'

import { describeActionError, showActionFailure } from './actionReason'

/**
 * 工单状态机与处置弹窗（从 `TicketsView.vue` 抽出，同 `actionReason.ts` 的组织方式）。
 *
 * **前端不复制状态机规则**：这里的 `STATUS_FLOW` 只用于"把非法后继从下拉里去掉"，
 * 真正的权威是服务端 `TicketWorkflowService`（前向流转、禁回退、closed 终态）。
 * 前端即便漏了某条，服务端也会拒绝并返回 40001 —— 那时页面如实显示错误，不假装成功。
 *
 * 两端各有一份状态映射是**有意的**：前端那份只影响可达性（少一次注定失败的往返），
 * 一旦不一致，表现是"多一次失败提示"，不是"数据被写坏"。
 */
export const STATUS_LABEL: Record<TicketStatus, string> = {
  open: '新建',
  processing: '处理中',
  resolved: '已解决',
  closed: '已关闭',
}

/** 合法后继状态；空数组 = 终态，不能再流转 */
const STATUS_FLOW: Record<string, TicketStatus[]> = {
  open: ['processing', 'closed'],
  processing: ['resolved', 'closed'],
  resolved: ['closed'],
  closed: [],
}

export function nextStatuses(current: string): TicketStatus[] {
  return STATUS_FLOW[current] ?? []
}

export const TICKET_STATUS_OPTIONS = [
  { label: '全部状态', value: '' },
  ...Object.entries(STATUS_LABEL).map(([value, label]) => ({ label, value })),
]

export const TICKET_KIND_OPTIONS = [
  { label: '全部类型', value: '' },
  { label: '反馈', value: 'feedback' },
  { label: '报错', value: 'bug' },
  { label: '内容纠误', value: 'content_correction' },
]

export interface TicketHandleContext {
  dialog: DialogApi
  message: MessageApi
  /** 提交成功后刷新列表 */
  onDone: () => void | Promise<void>
}

/**
 * 打开"处置工单"弹窗：状态流转 + **回复用户**。
 *
 * 为什么必须带 `adminReply`：旧管理端的 `TicketPatch` 就含该字段，而旧面已随旧管理端退役
 * （docs/50 §15.5）→ 控制台是唯一工单面，只做状态流转会丢掉"回复用户"这个能力。
 */
export function openTicketHandle(ctx: TicketHandleContext, row: TicketRow): void {
  const successors = nextStatuses(row.status)
  const next = ref<TicketStatus | null>(successors[0] ?? null)
  const reply = ref<string>(row.adminReply ?? '')

  const options: DialogOptions = {
    title: `工单 #${row.id} · 处置`,
    content: () =>
      h('div', [
        h('p', { class: 'm-0 c-muted text-13px' }, row.title ?? row.content.slice(0, 80)),
        h('div', { class: 'mt-3' }, [
          h('div', { class: 'c-muted text-12px mb-1' }, '流转到（禁回退，已关闭为终态）'),
          h(NSelect, {
            value: next.value,
            options: successors.map((s) => ({ label: STATUS_LABEL[s], value: s })),
            placeholder: successors.length ? '请选择' : '该状态已是终态，不能再流转',
            disabled: successors.length === 0,
            'onUpdate:value': (v: TicketStatus | null) => {
              next.value = v
            },
          }),
        ]),
        h('div', { class: 'mt-3' }, [
          h('div', { class: 'c-muted text-12px mb-1' }, '回复用户（用户可见，勿写内部备注）'),
          h(NInput, {
            value: reply.value,
            type: 'textarea',
            rows: 3,
            maxlength: 500,
            showCount: true,
            placeholder: '如：已核实为歌词时间轴偏移，已修正并重新上架。',
            'onUpdate:value': (v: string) => {
              reply.value = v
            },
          }),
        ]),
        h(
          'p',
          { class: 'm-0 mt-2 c-weak text-12px' },
          '本次处置会写入审计日志（谁在什么时候把工单从什么状态改成了什么状态）。',
        ),
      ]),
    positiveText: '提交处置',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (successors.length && !next.value) {
        ctx.message.warning('请选择要流转到的状态')
        return false
      }
      try {
        await consoleApi.updateTicket(row.id, {
          status: next.value ?? undefined,
          adminReply: reply.value.trim() || undefined,
        })
      } catch (err) {
        // 40001（非法流转）/ 46002（无权限）走这里：服务端是状态机与授权的权威
        showActionFailure(ctx.dialog, describeActionError(err))
        return true
      }
      ctx.message.success('工单已更新')
      await ctx.onDone()
      return true
    },
  }
  ctx.dialog.info(options)
}
