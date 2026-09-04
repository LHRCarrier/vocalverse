<script setup lang="ts">
/**
 * 登录页（移动优先 · Soft UI 样板版，docs/31 §5.1 + pages/login.md）
 *
 * 要点：全屏浅天蓝渐变 + voice-first 波形装饰（p5，断网/无依赖降级）；
 * 52px 输入行 + focus ring；autocomplete 兼容（密码管理器/粘贴）；演示账号芯片（120ms 填充反馈）；
 * 登录按钮三态：default → loading(spinner) → success(绿勾 200ms) → 跳转；
 * 错误内联提示 aria-live，不打断输入。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import { useP5Wave } from '@/composables/useP5Wave'
import { useAuthStore } from '@/stores/auth'
import '@/styles/mobile-soft.css'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)
const success = ref(false)
const waveRef = ref<HTMLElement | null>(null)

useP5Wave(waveRef, { color: '#6B8FAF', height: 180 })

async function submit() {
  if (loading.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    loading.value = false
    success.value = true
    // 丝滑反馈：绿勾 200ms 后跳转（引导页路由后续版本接入）
    setTimeout(() => {
      router.push((router.currentRoute.value.query.redirect as string) ?? '/m/home')
    }, 200)
  } catch (e) {
    errorMsg.value = (e as Error).message
    loading.value = false
  }
}

function fillDemo(account: string) {
  username.value = account
  password.value = 'demo123456'
}
</script>

<template>
  <div class="s-login">
    <div ref="waveRef" class="s-login__wave" aria-hidden="true" />

    <section class="s-login__card" aria-label="登录">
      <!-- 品牌：三线波形 logo（Voice-First 视觉锚点） -->
      <div class="s-login__brand">
        <span class="s-login__logo" aria-hidden="true">
          <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
            <path d="M4 9v4M8.5 5v12M13 8v6M17.5 3v16" stroke="#fff" stroke-width="2.4" stroke-linecap="round" />
          </svg>
        </span>
        <h1 class="s-h1">VocalVerse 声语界</h1>
      </div>
      <p class="s-login__tag s-caption">
        <span style="color: var(--s-accent)" aria-hidden="true">●</span>
        说得好，唱得准 —— AI 发音教练
      </p>

      <form @submit.prevent="submit">
        <div class="s-field">
          <label class="s-field__label" for="vv-username">用户名</label>
          <input
            id="vv-username"
            v-model="username"
            class="s-input"
            name="username"
            autocomplete="username"
            placeholder="demoadult"
            autocapitalize="none"
            spellcheck="false"
          >
        </div>
        <div class="s-field">
          <label class="s-field__label" for="vv-password">密码</label>
          <input
            id="vv-password"
            v-model="password"
            class="s-input"
            type="password"
            name="password"
            autocomplete="current-password"
            placeholder="demo123456"
          >
        </div>

        <button
          type="submit"
          class="s-btn s-btn--primary s-btn--block"
          :class="{ 's-btn--ok': success }"
          :disabled="loading"
        >
          <span v-if="loading" class="s-spinner" aria-hidden="true" />
          <svg v-else-if="success" width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
            <path d="M3 9.5l4 4 8-9" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <template v-else>登录</template>
          <span v-if="loading" style="margin-left: 2px">正在登录…</span>
        </button>
      </form>

      <p v-if="errorMsg" class="s-error" role="alert" aria-live="polite">
        <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
          <circle cx="7" cy="7" r="6" stroke="#DC2626" stroke-width="1.6" />
          <path d="M7 4v3.4M7 9.8v.6" stroke="#DC2626" stroke-width="1.6" stroke-linecap="round" />
        </svg>
        {{ errorMsg }}
      </p>

      <div class="s-demo">
        <p class="s-demo__hint s-note">演示账号（密码 demo123456）：</p>
        <button type="button" class="s-chip" @click="fillDemo('demoadult')">成年中级</button>
        <button type="button" class="s-chip" @click="fillDemo('demoteen')">青少年初级</button>
        <button type="button" class="s-chip" @click="fillDemo('demosenior')">老年高级</button>
      </div>
    </section>
  </div>
</template>
