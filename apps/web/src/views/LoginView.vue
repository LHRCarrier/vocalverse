<script setup lang="ts">
/**
 * 登录页 v3.1（移动优先 · 极简 + 设计语言焦点，docs/31 §5.1 + pages/login.md）
 *
 * 焦点 = 大尺寸声波图形（Phosphor duotone，唯一高饱和元素）——设计语言表达"声语"，不是靠文字；
 * 字标 24px（拉丁 -0.03em收紧）退为次级 + 一行 14px 弱化副标题；表单组（16px 内距）→ 蓝按钮（32px）；
 * 底部单行「演示账号登录」。无卡片、无装饰动画、少文字（全屏 ≤15 词）。
 * 无障碍：placeholder + aria-label + autocomplete（密码管理器/粘贴兼容）；回车提交；错误 aria-live。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import IconMicrophone from '~icons/tabler/microphone'
import IconWaveDuotone from '~icons/ph/wave-sine-duotone'
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
    <!-- 品牌焦点：声波大图形（设计语言 = 记忆点） -->
    <div class="s-login__hero">
      <span class="s-login__wave">
        <IconWaveDuotone aria-hidden="true" />
      </span>
      <h1 class="s-login__name">VocalVerse</h1>
      <p class="s-login__tag">说得好，唱得准</p>
    </div>

    <!-- 表单组：药丸输入 ×2（16 内距）→ 蓝按钮 -->
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
