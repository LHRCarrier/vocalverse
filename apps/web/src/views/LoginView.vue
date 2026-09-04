<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { NButton, NForm, NFormItem, NInput, useMessage } from 'naive-ui'

import { useP5Wave } from '@/composables/useP5Wave'
import { useAuthStore } from '@/stores/auth'

const message = useMessage()
const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const errorMsg = ref('')
const loading = ref(false)
const waveRef = ref<HTMLElement | null>(null)

useP5Wave(waveRef, { height: 180 })

async function submit() {
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    message.success(`欢迎回来！`)
    router.push((router.currentRoute.value.query.redirect as string) ?? '/m/home')
  } catch (e) {
    errorMsg.value = (e as Error).message
  } finally {
    loading.value = false
  }
}

function fillDemo(account: string) {
  username.value = account
  password.value = 'demo123456'
}
</script>

<template>
  <div
    class="relative flex min-h-screen items-center justify-center overflow-hidden"
    :style="{ background: 'linear-gradient(155deg, #ECFDF5 0%, #F9FAFB 55%, #FFFFFF 100%)' }"
  >
    <div ref="waveRef" class="pointer-events-none absolute inset-x-0 bottom-0 h-[180px] opacity-70" />

    <section
      class="relative z-10 w-[380px] rounded-[12px] border border-[#E5E7EB] bg-white p-8 shadow-sm"
    >
      <div class="mb-6 flex items-center gap-2">
        <span class="inline-block h-4 w-4 rounded-full bg-brand" />
        <h1 class="text-xl font-bold">VocalVerse 声语界</h1>
      </div>
      <p class="mb-6 flex items-center gap-1 text-sm text-[#667085]">
        <span class="text-accent">●</span>
        说得好，唱得准 —— AI 发音教练
      </p>

      <n-form label-placement="top" @keyup.enter="submit">
        <n-form-item label="用户名">
          <n-input v-model:value="username" placeholder="demoadult" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input v-model:value="password" type="password" placeholder="demo123456" />
        </n-form-item>
      </n-form>

      <NButton block round size="large" type="primary" :loading="loading" @click="submit">
        登录
      </NButton>

      <div class="mt-4 flex items-center justify-center gap-2 text-xs text-[#667085]">
        <span>演示账号（密码 demo123456）：</span>
        <NButton size="tiny" quaternary round @click="fillDemo('demoadult')">成年中级</NButton>
        <NButton size="tiny" quaternary round @click="fillDemo('demoteen')">青少年初级</NButton>
        <NButton size="tiny" quaternary round @click="fillDemo('demosenior')">老年高级</NButton>
      </div>
      <p v-if="errorMsg" class="mt-3 text-center text-xs text-[#B91C1C]">{{ errorMsg }}</p>
      <p class="mt-4 text-center text-xs text-[#667085]">
        还没有账号？请先启动 Java 服务后注册（M2 认证已接入）
      </p>
    </section>
  </div>
</template>
