<script setup lang="ts">
/**
 * 上架 / 下架按钮（歌曲、听力素材、场景、书籍共用；docs/50 §6.1 + §10.2 / §10.3）。
 *
 * 三个刻意的设计：
 * 1. **按钮自带 `PermissionGate`**（docs/50 §4.3）：没有 `content:*:publish` 的账号看不到按钮，
 *    而不是点了才吃 46002；后端仍逐请求校验，前端裁剪不构成授权。
 * 2. 点击先弹确认框并**必选原因**（docs/50 §11.4），原因枚举见 `actionReason.ts`。
 * 3. 书籍走 Python 端点（`opsApi.publishBook`），故提交动作可由外部注入，
 *    避免为同一种交互再写一个几乎一样的按钮组件。
 */
import { computed } from 'vue'
import { NButton, useDialog, useMessage } from 'naive-ui'

import { consoleApi } from '@/api'
import type { PublishDomain, PublishStatus } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { PUBLISH_REASONS, UNPUBLISH_REASONS, confirmWithReason } from './actionReason'

const props = defineProps<{
  /** 内容域 code（Java `PublishService.DOMAIN_*`：song / listening / scenario）；书籍等 Python 侧内容改传 `submit` */
  domain?: PublishDomain
  id: number
  title: string
  /** 后端行状态（Java `SongRow.status` / Python 书籍行为字符串；只在下方安全收窄后下发） */
  status: string
  /** 上下架权限码（与路由 meta 的 read 权限是两个码） */
  permission: string
  /** 下架无用户侧消费者时的补充提示（docs/50 §15.2 G-2） */
  consumerNote?: string
  submit?: (id: number, status: PublishStatus) => Promise<unknown>
}>()

const emit = defineEmits<{ done: [] }>()

const dialog = useDialog()
const message = useMessage()

/** 已上架 → 下架；草稿 / 已下架 → 上架（docs/50 §6.1 状态迁移表） */
const nextStatus = computed<PublishStatus>(() => (props.status === 'published' ? 'archived' : 'published'))
const isPublish = computed(() => nextStatus.value === 'published')

/**
 * 收窄到后端受理的三态。
 *
 * 按钮的 `status` 入参来自行数据（`SongRow.status` 等是后端字符串列）；只有该列的取值域
 * 等于 `draft|published|archived` 时才把**行状态**原样发回去。异常值直接返回 null，
 * 由调用方改用 `nextStatus` —— 与其把 `'unknown'` 发给服务端吃 46007，不如本地确定一个合法动作。
 */
function asPublishStatus(value: string): PublishStatus | null {
  return value === 'draft' || value === 'published' || value === 'archived' ? value : null
}

async function run(id: number, status: PublishStatus): Promise<unknown> {
  if (props.submit) return props.submit(id, status)
  if (!props.domain) throw new Error('PublishActionButton 需要 domain 或 submit 之一')
  return consoleApi.publish(props.domain, id, status)
}

function onClick(): void {
  confirmWithReason(
    { dialog, message },
    {
      title: isPublish.value ? `确认上架《${props.title}》？` : `确认下架《${props.title}》？`,
      detail: isPublish.value
        ? '上架前服务端会做前置校验（缺 lrc / 音频等会逐字段报回来），校验不通过不会改动状态。'
        : '下架 = 归档：内容对用户不可见但保留数据行，控制台不提供物理删除（docs/50 §6.1）。',
      reasons: isPublish.value ? PUBLISH_REASONS : UNPUBLISH_REASONS,
      positiveText: isPublish.value ? '上架' : '下架',
      successText: isPublish.value ? `《${props.title}》已上架` : `《${props.title}》已下架`,
      danger: !isPublish.value,
      note: isPublish.value ? undefined : props.consumerNote,
      submit: () => run(props.id, asPublishStatus(props.status) ?? nextStatus.value),
      onSuccess: () => emit('done'),
    },
  )
}
</script>

<template>
  <PermissionGate :code="permission">
    <n-button size="small" :type="isPublish ? 'primary' : 'default'" @click="onClick">
      {{ isPublish ? '上架' : '下架' }}
    </n-button>
  </PermissionGate>
</template>
