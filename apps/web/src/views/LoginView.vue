<script setup lang="ts">
/**
 * 登录页 v3.2（移动优先 · 极简 + 线稿插画焦点，docs/31 + pages/login.md v3.2）
 *
 * 升级点（参考图语言：线稿插画 + 大字标题 + 单点彩色）：
 *  - 自绘线稿声波插画（ArtWave：2.5px 圆头线稿 + 单色填涂 + 星芒）替代单色图标 = 品牌记忆点/设计语言
 *  - 字标升 32px（-0.03em 拉丁收紧，仍在本方案 6 档内）
 *  - 表单组 16 内距 → 蓝按钮；底部单行「演示账号登录」；无卡片、少文字（<15 词）
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import ArtWave from '@/components/mobile/ArtWave.vue'
import IconMicrophone from '~icons/tabler/microphone'
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
    setTimeout(() => {
      router.push((router.currentRoute.value.query.redirect as string) ?? '/m/home')
    }, 200)
  } catch (e) {
    errorMsg.value = (e as Error).message
    loading.value = false
  }
}

function demoLogin() {
  if (loading.value) return
  username.value = 'demoadult'
  password.value = 'demo123456'
  void submit()
}
</script>

<template>
  <div class="s-login">
    <!-- 品牌焦点：自绘线稿声波插画（设计语言 = 记忆点） -->
    <div class="s-login__hero">
      <ArtWave :size="216" />
      <h1 class="s-login__name">VocalVerse</h1>
      <p class="s-login__tag">说得好，唱得准</p>
    </div>

    <form class="s-login__form" @submit.prevent="submit">
      <input
        v-model="username"
        class="s-input"
        name="username"
        placeholder="用户名"
        aria-label="用户名"
        autocomplete="username"
        autocapitalize="none"
        spellcheck="false"
      >
      <input
        v-model="password"
        class="s-input"
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
        <IconMicrophone v-else-if="success" style="width: 18px; height: 18px" aria-hidden="true" />
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
