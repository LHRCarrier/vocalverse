<script setup lang="ts">
import { ref } from 'vue'
import { NButton, NForm, NFormItem, NInput, useMessage } from 'naive-ui'

import { useP5Wave } from '@/composables/useP5Wave'

const message = useMessage()
const email = ref('')
const password = ref('')
const waveRef = ref<HTMLElement | null>(null)

useP5Wave(waveRef, { height: 180 })

function submit() {
  // M2：接入 Java JWT 链路后替换（docs/06 §7：access 15min + refresh 7d httpOnly cookie）
  message.info('登录接口 M2 接入（Java 签发 JWT，见 docs/api 契约）')
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
        <n-form-item label="邮箱">
          <n-input v-model:value="email" placeholder="you@example.com" />
        </n-form-item>
        <n-form-item label="密码">
          <n-input v-model:value="password" type="password" placeholder="••••••••" />
        </n-form-item>
      </n-form>

      <NButton block round size="large" type="primary" @click="submit">登录</NButton>
      <p class="mt-4 text-center text-xs text-[#667085]">
        还没有账号？M2 注册/入学测试开放（docs/06 §9.2）
      </p>
    </section>
  </div>
</template>
