<script setup lang="ts">
/**
 * 内容表单弹窗的**外壳**：标题 + 滚动区 + 错误条 + 底部按钮（四个弹窗共用）。
 *
 * 为什么抽出来：四个弹窗的差异只有"字段长什么样"和"提交打哪个接口"，
 * 而下面这些**必须一致**（否则又会出现某个弹窗悄悄把错误吞掉）：
 * 1. 提交中禁止关闭（`mask-closable=false` + 取消按钮 disabled）——半途关掉会让人
 *    以为没提交成功，再点一次就写两条；
 * 2. 未归位到字段的失败（46002 缺权限码 / 网络失败 / 50002）一定要显示在弹窗里，
 *    且带错误码 —— 任务书明确要求不能只 toast；
 * 3. 「已按字段标红」时给出引导语，否则运营会以为提交没反应。
 */
import { NModal } from 'naive-ui'

import { failureLines } from '@/views/content/actionReason'
import type { ActionFailure } from '@/views/content/actionReason'

defineProps<{
  title: string
  /** 宽（UnoCSS class，如 `w-140`）；不同表单字段多少不同 */
  widthClass?: string
  submitting?: boolean
  /** 未归位的失败；已归位的错误由各字段红字呈现 */
  failure?: ActionFailure | null
  /** 是否有字段级错误（决定是否显示"已标红"引导语） */
  hasFieldErrors?: boolean
  /** 保存按钮文案 */
  submitText?: string
}>()

const show = defineModel<boolean>('show', { required: true })
const emit = defineEmits<{ submit: []; cancel: [] }>()

function onCancel(): void {
  emit('cancel')
  show.value = false
}
</script>

<template>
  <n-modal
    v-model:show="show"
    preset="card"
    :title="title"
    :class="widthClass ?? 'w-160'"
    :mask-closable="false"
    :closable="!submitting"
  >
    <div class="c-modal-body">
      <slot />

      <div v-if="hasFieldErrors" class="c-form-note text-12px mt-1" role="status">
        已把服务端返回的校验原因标在对应输入框下方，请逐项修正后重新提交。
      </div>

      <div v-if="failure" class="c-form-failure mt-3 text-12px" role="alert">
        <p v-for="(line, index) in failureLines(failure)" :key="index" class="m-0 mb-1">
          {{ line }}
        </p>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <n-button :disabled="submitting" @click="onCancel">取消</n-button>
        <n-button type="primary" :loading="submitting" @click="emit('submit')">
          {{ submitText ?? '保存' }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.c-modal-body {
  max-height: 62vh;
  overflow-y: auto;
  padding-right: 4px;
}
.c-form-note {
  color: var(--c-warn);
}
.c-form-failure {
  padding: 8px 10px;
  border-radius: 6px;
  background: var(--c-danger-soft);
  color: var(--c-danger-ink);
}
</style>
