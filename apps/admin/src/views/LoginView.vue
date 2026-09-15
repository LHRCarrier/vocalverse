<script setup lang="ts">
/**
 * 控制台登录（docs/50 §4.1）。
 *
 * 与 App 登录页**刻意不共用**：控制台身份独立、令牌独立、错误语义独立
 * （被锁定/已停用要说清楚，而不是笼统"账号或密码错误"——管理员需要知道
 * 是被风控锁了还是账号被停用了，否则会一直重试导致锁得更久）。
 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput, useMessage } from 'naive-ui'
import IconLock from '~icons/tabler/lock'
import IconUser from '~icons/tabler/user'

import { ApiError, ERR } from '@/api'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const message = useMessage()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref<string | null>(null)
const retryAfter = ref<number | null>(null)
const lockedUntil = ref<string | null>(null)
const submitting = ref(false)

const canSubmit = computed(() => username.value.trim().length > 0 && password.value.length > 0)

/** 按错误码给出可操作提示，而不是统一一句"登录失败" */
function describe(err: unknown): void {
  if (!(err instanceof ApiError)) {
    error.value = (err as Error).message ?? '登录失败'
    return
  }
  const data = (err.data ?? {}) as { retryAfter?: number; lockedUntil?: string; required?: string }
  retryAfter.value = data.retryAfter ?? null
  lockedUntil.value = data.lockedUntil ?? null

  if (err.code === ERR.LOGIN_THROTTLED) {
    error.value = `登录失败次数过多，请 ${data.retryAfter ?? 15} 分钟后再试，或联系超级管理员解锁。`
  } else if (err.code === ERR.ACCOUNT_DISABLED) {
    error.value = data.lockedUntil
      ? `该账号已被临时锁定至 ${data.lockedUntil}。`
      : '该账号已停用，请联系超级管理员。'
  } else if (err.code === -1) {
    error.value = '连不上后端服务。确认 Java 服务已在 8080 启动（或网关可用）。'
  } else {
    error.value = err.message || '登录失败'
  }
}

async function onSubmit(): Promise<void> {
  if (!canSubmit.value || submitting.value) return
  submitting.value = true
  error.value = null
  retryAfter.value = null
  lockedUntil.value = null
  try {
    await auth.login(username.value.trim(), password.value)
    message.success(`欢迎回来，${auth.profile?.displayName ?? ''}`)
    const redirect = route.query.redirect
    await router.replace(typeof redirect === 'string' && redirect ? redirect : '/')
  } catch (err) {
    describe(err)
    password.value = ''
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="lg">
    <form class="lg-card" @submit.prevent="onSubmit">
      <div class="lg-brand">
        <span class="lg-mark">VV</span>
        <div>
          <h1 class="lg-title">VocalVerse 控制台</h1>
          <p class="lg-sub">运维 · 运营 · 审核</p>
        </div>
      </div>

      <label class="lg-field">
        <span class="lg-label">账号</span>
        <n-input
          v-model:value="username"
          placeholder="管理员账号"
          autocomplete="username"
          :input-props="{ autocapitalize: 'off', autocorrect: 'off' }"
          size="large"
        >
          <template #prefix>
            <IconUser width="16" height="16" aria-hidden="true" />
          </template>
        </n-input>
      </label>

      <label class="lg-field">
        <span class="lg-label">口令</span>
        <n-input
          v-model:value="password"
          type="password"
          show-password-on="click"
          placeholder="口令"
          autocomplete="current-password"
          size="large"
          @keydown.enter.prevent="onSubmit"
        >
          <template #prefix>
            <IconLock width="16" height="16" aria-hidden="true" />
          </template>
        </n-input>
      </label>

      <p v-if="error" class="lg-error" role="alert">{{ error }}</p>

      <n-button
        type="primary"
        size="large"
        block
        :loading="submitting"
        :disabled="!canSubmit"
        attr-type="submit"
      >
        登录
      </n-button>

      <p class="lg-note">
        控制台账号与 App 账号互相独立。没有账号请联系超级管理员创建，控制台不提供自助注册。
      </p>
    </form>
  </div>
</template>

<style scoped>
.lg {
  display: grid;
  place-items: center;
  min-height: 100vh;
  background: var(--c-bg);
  padding: 24px;
}
.lg-card {
  width: 100%;
  max-width: 400px;
  background: var(--c-surface);
  border-radius: var(--c-card-radius);
  box-shadow: var(--c-shadow-2);
  padding: 32px 32px 24px;
}
.lg-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 26px;
}
.lg-mark {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: var(--c-primary);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 0.02em;
}
.lg-title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.lg-sub {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--c-text-3);
  letter-spacing: 0.04em;
}
.lg-field {
  display: block;
  margin-bottom: 16px;
}
.lg-label {
  display: block;
  margin-bottom: 6px;
  font-size: 12.5px;
  color: var(--c-text-2);
}
.lg-error {
  margin: 0 0 14px;
  padding: 9px 12px;
  border-radius: var(--c-ctl-radius);
  background: var(--c-danger-soft);
  color: var(--c-danger);
  font-size: 12.5px;
  line-height: 1.5;
}
.lg-note {
  margin: 18px 0 0;
  font-size: 11.5px;
  line-height: 1.6;
  color: var(--c-text-3);
}
</style>
