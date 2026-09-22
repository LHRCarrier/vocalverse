<script setup lang="ts">
/**
 * 审核决定弹窗（docs/50 §6.2 状态机 + §11.4 危险操作二次确认）。
 *
 * 这是审核员最核心的一次交互，因此三件事必须**在点提交之前**就摆在他眼前：
 * 1. **内容快照**——决定的对象是什么（快照是送审时的截断留存，原文用文本插值，绝不 v-html）；
 * 2. **决定的真实效果**——每个决定都写明它对目标表做什么。特别是 `hide` / `delete`：
 *    服务端会写 `status='hidden'|'deleted'`，**用户可见范围内立即不可见（作者也一样）**，
 *    这不是"标记一下待复核"（§6.2 处置动作映射表）；
 * 3. **内部备注不是对外文案**——`decision_note` **不下发作者**（docs/51 B-4 拍板：避免审核员身份与
 *    内部理由外泄）；作者侧只会看到固定 `reason_code` 的中文标签（P6 后续 PR）。标签必须这么写，
 *    否则审核员会把它当"给用户的话"来写。
 *
 * 自动送审单（`source='auto'`）额外展示 `snapshot.ai` 判定证据（docs/58）：审核员要能看到
 * 「这单为什么在队列里」，而不是只能信任一次黑箱。
 *
 * 46010（`CASE_STATE_CONFLICT`）是**预期内**结果：另一个审核员抢先处置了同一单，
 * 服务端的条件 UPDATE 匹配 0 行（§6.2）。这里不弹红色报错，而是提示 + 关框 + 触发刷新。
 */
import { computed, ref, watch } from 'vue'
import { NAlert, NButton, NInput, NModal, NRadio, NRadioGroup, NSelect, useMessage } from 'naive-ui'

import { ERR, consoleApi } from '@/api'
import type { ModerationCaseRow, ModerationDecision } from '@/api'
import PermissionGate from '@/components/common/PermissionGate.vue'
import { fmtDateTime } from '@/utils/format'

import {
  DECISION_META,
  REASON_CODE_OPTIONS,
  SOURCE_LABEL,
  aiEvidenceText,
  decisionMeta,
  describeFailure,
  failureLines,
  isTerminalCase,
  reasonCodeText,
  reportCountText,
  targetText,
} from './moderationMeta'

const props = defineProps<{ show: boolean; item: ModerationCaseRow | null }>()
const emit = defineEmits<{ 'update:show': [boolean]; done: [] }>()

const message = useMessage()

const decision = ref<ModerationDecision | null>(null)
const reasonCode = ref<string | null>(null)
const note = ref('')
const submitting = ref(false)

const chosen = computed(() => decisionMeta(decision.value))
const aiEvidence = computed(() => aiEvidenceText(props.item?.snapshot))

const submitText = computed(() => {
  switch (decision.value) {
    case 'approve':
      return '通过并关闭工单'
    case 'hide':
      return '隐藏并关闭工单'
    case 'delete':
      return '删除并关闭工单'
    case 'reject':
      return '驳回举报'
    case 'escalate':
      return '升级该单'
    default:
      return '提交决定'
  }
})

/** 危险决定用警示色按钮（危险操作视觉上不能与普通操作一样，docs/50 §11.4） */
const submitType = computed(() => (chosen.value?.invisible ? 'error' : 'primary'))

/** 每次打开都重置：残留上一次的决定/说明会让第二个单被"顺手"用错文案处置 */
function reset(row: ModerationCaseRow | null): void {
  decision.value = null
  // 原因码默认带入本单的送审原因（服务端在 reasonCode 为空时也是这么兜的），审核员可改
  reasonCode.value = row?.reasonCode ?? null
  note.value = ''
  submitting.value = false
}

watch(
  () => [props.show, props.item?.id],
  () => {
    if (!props.show) return
    reset(props.item)
    // 终态单别给表单：提交必然吃 46010（服务端幂等保护，docs/50 §6.2）。
    // 从举报页按 caseId 跳进来时目标单可能已被别人处置，这里挡住比让他白填一遍更好。
    if (props.item && isTerminalCase(props.item)) {
      message.warning(`审核单 #${props.item.id} 已是终态，不能再处置；可在队列里看到处理人与时间`)
      emit('update:show', false)
    }
  },
  { immediate: true },
)

async function submit(): Promise<void> {
  const row = props.item
  if (!row || !decision.value || !reasonCode.value) {
    message.warning('请先选择决定与原因码')
    return
  }
  submitting.value = true
  try {
    await consoleApi.decideCase(row.id, {
      decision: decision.value,
      reasonCode: reasonCode.value,
      note: note.value.trim() || undefined,
    })
    message.success(`单 #${row.id} 已提交：${chosen.value?.label ?? decision.value}`)
    emit('update:show', false)
    emit('done')
  } catch (err) {
    handleFailure(err)
  } finally {
    submitting.value = false
  }
}

function handleFailure(err: unknown): void {
  const failure = describeFailure(err)
  if (failure.code === ERR.CASE_STATE_CONFLICT) {
    message.warning('该单已被其他人处理，请刷新')
    emit('update:show', false)
    emit('done')
    return
  }
  message.error(failureLines(failure).join('；'))
}
</script>

<template>
  <n-modal
    :show="show"
    preset="card"
    :title="item ? `审核决定 · 单 #${item.id}` : '审核决定'"
    :style="{ width: '680px', maxWidth: '92vw' }"
    :mask-closable="false"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <div v-if="item" class="mdq">
      <!-- ① 快照：决定必须"看得见对象" -->
      <section class="mdq-snap">
        <div class="mdq-snap-head">
          <span class="c-badge c-badge--muted">{{ targetText(item) }}</span>
          <span class="c-weak">来源 {{ SOURCE_LABEL[item.source] ?? item.source }}</span>
          <span class="c-weak">原因码 {{ reasonCodeText(item.reasonCode) }}</span>
          <span class="c-weak">举报 {{ reportCountText(item) }} 条</span>
          <span class="c-weak">建单 {{ fmtDateTime(item.createdAt) }}</span>
        </div>
        <p class="mdq-snippet">{{ item.snippet || '（本单没有内容快照）' }}</p>
        <p v-if="aiEvidence" class="mdq-ai">
          <span class="mdq-ai-tag">AI 送审</span>{{ aiEvidence }}
          <span class="mdq-ai-note">
            （自动判定只负责把它送进队列，是否处置由你决定；证据仅供判断参考）
          </span>
        </p>
        <p class="mdq-snap-hint">
          快照是送审时的截断留存（≤500 字），不是全文；判断以「目标 + 原因码 + 举报数」为准。
        </p>
      </section>

      <!-- ② 决定：每条都写清它对目标表做什么（§6.2 处置动作映射表） -->
      <div class="mdq-field">
        <div class="mdq-label">决定（必选）</div>
        <n-radio-group v-model:value="decision" class="mdq-radios">
          <n-radio v-for="d in DECISION_META" :key="d.value" :value="d.value" class="mdq-radio">
            <span class="mdq-radio-label" :class="{ 'mdq-radio-label--danger': d.invisible }">
              {{ d.label }}
            </span>
            <span class="mdq-radio-effect">{{ d.effect }}</span>
          </n-radio>
        </n-radio-group>
      </div>

      <n-alert
        v-if="chosen?.invisible"
        class="mdq-alert"
        type="warning"
        title="该决定会让内容对用户不可见"
      >
        提交后 {{ targetText(item) }} 在用户可见范围内立即不可见（作者本人也看不到），
        只能由审核侧恢复。服务端为此写的是目标表的 status（hidden / deleted），不是标记待复核。
      </n-alert>

      <!-- ③ 原因码 + 给作者的说明 -->
      <div class="mdq-field">
        <div class="mdq-label">原因码（必选）</div>
        <n-select
          v-model:value="reasonCode"
          :options="REASON_CODE_OPTIONS"
          placeholder="请选择原因码"
          :consistent-menu-width="false"
        />
      </div>

      <div class="mdq-field">
        <div class="mdq-label">处置备注（内部留痕，不对外展示）</div>
        <n-input
          v-model:value="note"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-count
          placeholder="例如：与审核单 #123 合并处理；内容确认违规"
        />
        <p class="mdq-hint">
          只写进审核单与审计日志，不会下发给作者或举报人（docs/51 B-4 定稿）；作者侧看到的
          只是固定原因码的标签（P6 落地）。请写"内部可读"的话，不要写审核员身份信息。
        </p>
      </div>
    </div>

    <template #footer>
      <div class="mdq-footer">
        <PermissionGate code="moderation:decide" fallback="disable">
          <template #disabled>
            <span class="c-weak" style="font-size: 12px">需要 moderation:decide 才能提交决定</span>
          </template>
          <n-button @click="emit('update:show', false)">取消</n-button>
          <n-button
            :type="submitType"
            :loading="submitting"
            :disabled="!decision || !reasonCode"
            @click="submit"
          >
            {{ submitText }}
          </n-button>
        </PermissionGate>
      </div>
    </template>
  </n-modal>
</template>

<style scoped>
.mdq {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.mdq-snap {
  border: 1px solid var(--c-border);
  border-radius: var(--c-ctl-radius);
  background: var(--c-surface-sunken);
  padding: 10px 12px;
}
.mdq-snap-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}
.mdq-snippet {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--c-text);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 132px;
  overflow-y: auto;
}
.mdq-snap-hint {
  margin: 6px 0 0;
  font-size: 11.5px;
  color: var(--c-text-3);
}
.mdq-ai {
  margin: 8px 0 0;
  padding: 6px 8px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-primary-soft);
  font-size: 12px;
  color: var(--c-text);
  word-break: break-word;
}
.mdq-ai-tag {
  display: inline-block;
  margin-right: 6px;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--c-primary);
  color: #fff;
  font-size: 11px;
  line-height: 17px;
}
.mdq-ai-note {
  color: var(--c-text-3);
}
.mdq-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.mdq-label {
  font-size: 12.5px;
  color: var(--c-text-2);
}
.mdq-radios {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mdq-radio {
  align-items: flex-start;
}
.mdq-radio-label {
  font-size: 13px;
  font-weight: 600;
}
.mdq-radio-label--danger {
  color: var(--c-danger);
}
.mdq-radio-effect {
  margin-left: 8px;
  font-size: 12px;
  color: var(--c-text-2);
  font-weight: 400;
}
.mdq-alert {
  border-radius: var(--c-ctl-radius);
}
.mdq-hint {
  margin: 0;
  font-size: 11.5px;
  color: var(--c-text-3);
}
.mdq-footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
}
@media (max-width: 720px) {
  .mdq-radio-effect {
    display: block;
    margin-left: 0;
  }
}
</style>
