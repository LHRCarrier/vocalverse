<script setup lang="ts">
/**
 * 表单字段壳：标签 + 提示 + **行内错误**（任务书要求"服务端校验逐字段浮回输入框"）。
 *
 * 为什么不用 `n-form` + `n-form-item` 的 rules：那几个弹窗的错误来源是**服务端**
 * （42201 的 message 里带 Java 属性名 / 46011 的 violations[]），不是本地 rules。
 * 而 `n-form-item` 的 `feedback` 需要一个能持续求值的规则函数，把"服务端回来的一次性错误"
 * 硬塞进 rules 会变成"错误在第二次输入时凭空消失"或"永远消不掉"。
 * 这里把错误当成一个受控字符串显示：`useContentForm` 负责设置与清除，职责单一。
 *
 * `role="alert"`：字段级错误要能被读屏播报（控制台是有人靠键盘+读屏用的）。
 */
defineProps<{
  label: string
  /** 该字段是否服务端必填（显示红色星号）；不代表本地一定拦，见各表单说明 */
  required?: boolean
  /** 常驻说明：取值域、格式、为什么有这个规则（含 Java / docs 依据） */
  hint?: string
  error?: string | null
}>()
</script>

<template>
  <div class="c-field mb-3">
    <div class="c-field-label">
      <span>{{ label }}</span>
      <span v-if="required" class="c-field-required" aria-hidden="true">*</span>
    </div>
    <slot />
    <div v-if="hint" class="c-weak text-12px mt-1">{{ hint }}</div>
    <div v-if="error" class="c-field-error text-12px mt-1" role="alert">{{ error }}</div>
  </div>
</template>

<style scoped>
.c-field-label {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
  font-size: 12px;
  color: var(--c-text-2);
}
.c-field-required {
  color: var(--c-danger);
  line-height: 1;
}
.c-field-error {
  color: var(--c-danger);
}
</style>
