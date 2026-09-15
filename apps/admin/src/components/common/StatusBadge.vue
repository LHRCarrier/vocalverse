<script setup lang="ts">
/**
 * 状态徽标（统一状态 → 文案 + 色调 的映射，避免每个页面各写一套颜色）。
 * 覆盖：内容上架状态 / 审核单状态 / 预警严重级 / trace 状态 / 账号状态。
 */
import { computed } from 'vue'

const props = defineProps<{ kind: string; value: string; label?: string }>()

type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'muted'

interface Meta {
  text: string
  tone: Tone
}

const MAP: Record<string, Record<string, Meta>> = {
  publish: {
    draft: { text: '草稿', tone: 'muted' },
    published: { text: '已上架', tone: 'ok' },
    archived: { text: '已下架', tone: 'warn' },
  },
  moderation: {
    pending: { text: '待处理', tone: 'warn' },
    escalated: { text: '已升级', tone: 'danger' },
    approved: { text: '已处置', tone: 'ok' },
    rejected: { text: '已驳回', tone: 'muted' },
    withdrawn: { text: '已撤回', tone: 'muted' },
  },
  severity: {
    info: { text: '提示', tone: 'info' },
    warn: { text: '警告', tone: 'warn' },
    critical: { text: '严重', tone: 'danger' },
  },
  alertStatus: {
    firing: { text: '未处理', tone: 'danger' },
    acknowledged: { text: '已确认', tone: 'warn' },
    resolved: { text: '已恢复', tone: 'ok' },
  },
  trace: {
    ok: { text: '成功', tone: 'ok' },
    error: { text: '失败', tone: 'danger' },
    aborted: { text: '中断', tone: 'warn' },
    incomplete: { text: '未完成', tone: 'warn' },
  },
  account: {
    active: { text: '启用', tone: 'ok' },
    disabled: { text: '停用', tone: 'muted' },
  },
  media: {
    ready: { text: '正常', tone: 'ok' },
    hidden: { text: '已隐藏', tone: 'warn' },
    deleted: { text: '已删除', tone: 'muted' },
  },
  report: {
    pending: { text: '待处理', tone: 'warn' },
    accepted: { text: '已受理', tone: 'ok' },
    rejected: { text: '不成立', tone: 'muted' },
    duplicate: { text: '重复', tone: 'muted' },
  },
  /** 工单状态机：open → processing → resolved → closed（禁回退，closed 终态） */
  ticket: {
    open: { text: '新建', tone: 'warn' },
    processing: { text: '处理中', tone: 'info' },
    resolved: { text: '已解决', tone: 'ok' },
    closed: { text: '已关闭', tone: 'muted' },
  },
  /** 工单类型 */
  ticketKind: {
    feedback: { text: '反馈', tone: 'info' },
    bug: { text: '报错', tone: 'danger' },
    content_correction: { text: '内容纠误', tone: 'warn' },
  },
  auditResult: {
    ok: { text: '成功', tone: 'ok' },
    denied: { text: '被拒', tone: 'warn' },
    failed: { text: '失败', tone: 'danger' },
  },
}

const meta = computed<Meta>(() => {
  const found = MAP[props.kind]?.[props.value]
  return found ?? { text: props.label ?? props.value, tone: 'muted' }
})
</script>

<template>
  <span class="c-badge" :class="`c-badge--${meta.tone}`">{{ label ?? meta.text }}</span>
</template>
