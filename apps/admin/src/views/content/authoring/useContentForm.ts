/**
 * 表单提交的**统一收口**（"本地预检 → 提交 → 服务端错误归位"这套动作只写一遍）。
 *
 * 四个弹窗（歌曲 / 场景 / 听力素材 / 题目）与 LRC 编辑器的差异只在"预检怎么算"与
 * "提交打哪个接口"，而这套顺序必须一致，否则会出现"某个弹窗把 42201 只 toast 掉、
 * 输入框不标红"的漏网之鱼（任务书点名的缺陷类型）。
 *
 * 为什么要 `shallowRef` 而不是 `ref`：`FormErrors` 是 `Partial<Record<…>>`，
 * 用 `ref` 会走 `UnwrapRef` 的深解包，模板里读 `errors.value.xxx` 的类型会退化成联合类型；
 * `shallowRef` 直接给 `FormErrors`，模板自动解包、字段名可补全。
 */
import { shallowRef } from 'vue'

import { describeActionError } from '@/views/content/actionReason'
import type { ActionFailure } from '@/views/content/actionReason'
import type { FormErrors } from './contentFormTypes'
import { formErrorsFromError } from './serverFieldErrors'

export interface SubmitOptions {
  /** 本地预检：返回空对象 = 通过（键见 `contentFormPayload` 的校验函数） */
  validate: () => FormErrors
  /** 真正打接口；抛出的异常由本函数归位到字段 */
  submit: () => Promise<unknown>
  /** 提交成功（弹窗一般在这里关闭并 emit saved） */
  onSuccess: () => void
  /** 服务端错误**已归位到字段**时的补充回调（如把焦点滚到第一个出错的输入框） */
  onFieldErrors?: (errors: FormErrors) => void
}

export function useContentForm() {
  const submitting = shallowRef(false)
  const errors = shallowRef<FormErrors>({})
  /** 未归位到字段的失败（权限不足 / 网络失败 / 目标已不存在）；归位成功的错误不重复弹 */
  const failure = shallowRef<ActionFailure | null>(null)

  /** 清掉某个字段的错误（用户一开始改就撤掉红字，不用等再次提交） */
  function clearField(field: string): void {
    if (!(field in errors.value)) return
    const next: FormErrors = { ...errors.value }
    delete next[field as keyof FormErrors]
    errors.value = next
  }

  function clearAll(): void {
    errors.value = {}
    failure.value = null
  }

  async function run(options: SubmitOptions): Promise<boolean> {
    clearAll()
    const local = options.validate()
    if (Object.keys(local).length > 0) {
      // 本地预检不过：一次把**所有**不合格字段标红（服务端只回第一条，见 serverFieldErrors 文件头）
      errors.value = local
      options.onFieldErrors?.(local)
      return false
    }
    submitting.value = true
    try {
      await options.submit()
      options.onSuccess()
      return true
    } catch (err) {
      const mapped = formErrorsFromError(err)
      errors.value = mapped.errors
      if (mapped.mapped) options.onFieldErrors?.(mapped.errors)
      // 即使已归位到字段，也留一份完整失败信息：错误码（46002/46007/50002）是排查线索，
      // 而字段红字里放不下它。两条都显示，不互相替代。
      failure.value = describeActionError(err)
      return false
    } finally {
      submitting.value = false
    }
  }

  return { submitting, errors, failure, clearField, clearAll, run }
}
