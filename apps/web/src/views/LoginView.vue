<script setup lang="ts">
/**
 * 登录页（移动优先 · Soft UI 极简版，docs/31 §5.1 + pages/login.md v2）
 *
 * 极简原则：无卡片、无演示文案堆砌、无装饰动画。
 * 构成：居中品牌（波形标 + 字标 + 一行短标语）→ 两个药丸输入框 → 主按钮 → 一行「演示账号登录」。
 * 无障碍：placeholder + aria-label + autocomplete（密码管理器/粘贴兼容）；错误内联 aria-live。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import '@/styles/mobile-soft.css'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)
const success = ref(false)

async function submit() {
  if (loading.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    loading.value = false
    success.value = true
    // 丝滑反馈：绿勾 200ms 后跳转
    setTimeout(() => {
      router.push((router.currentRoute.value.query.redirect as string) ?? '/m/home')
    }, 200)
  } catch (e) {
    errorMsg.value = (e as Error).message
    loading.value = false
  }
}

/* 演示账号：一键填充并登录（团队联调用，单行入口不占视觉） */
function demoLogin() {
  if (loading.value) return
  username.value = 'demoadult'
  password.value = 'demo123456'
  void submit()
}
</script>

<template>
  <div class="s-login">
    <!-- 品牌：波形标 + 字标 + 一行短标语 -->
    <div class="s-login__hero">
      <span class="s-login__logo" aria-hidden="true">
        <svg width="26" height="26" viewBox="0 0 22 22" fill="none">
          <path d="M4 9v4M8.5 5v12M13 8v6M17.5 3v16" stroke="#fff" stroke-width="2.4" stroke-linecap="round" />
        </svg>
      </span>
      <h1 class="s-login__name">VocalVerse</h1>
      <p class="s-login__tag">说得好，唱得准</p>
    </div>

    <!-- 表单：两个药丸输入框 + 主按钮 -->
    <form class="s-login__form" @submit.prevent="submit">
      <input
        v-model="username"
        class="s-input s-input--pill"
        name="username"
        placeholder="用户名"
        aria-label="用户名"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
      >
      <input
        v-model="password"
        class="s-input s-input--pill"
        type="password"
        name="password"
        placeholder="密码"
        aria-label="密码"
        autocomplete="current-password"
      >
      <button
        type="submit"
        class="s-btn s-btn--primary s-btn--block s-login__submit"
        :class="{ 's-btn--ok': success }"
        :disabled="loading"
      >
        <span v-if="loading" class="s-spinner" aria-hidden="true" />
        <svg v-else-if="success" width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <path d="M3 9.5l4 4 8-9" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <template v-else>登录</template>
      </button>
    </form>

    <button type="button" class="s-login__demo" @click="demoLogin">演示账号登录</button>

    <p v-if="errorMsg" class="s-error" role="alert" aria-live="polite">
      <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
        <circle cx="7" cy="7" r="6" stroke="#DC2626" stroke-width="1.6" />
        <path d="M7 4v3.4M7 9.8v.6" stroke="#DC2626" stroke-width="1.6" stroke-linecap="round" />
      </svg>
      {{ errorMsg }}
    </p>
  </div>
</template>
