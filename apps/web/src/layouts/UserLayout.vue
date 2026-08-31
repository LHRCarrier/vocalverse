<script setup lang="ts">
import { NButton } from 'naive-ui'
import { useRouter } from 'vue-router'

const router = useRouter()

const nav = [
  { label: '骨架演示', to: '/demo' },
  { label: '场景练习', to: '/practice/cafe' },
  { label: '唱吧 (M3)', to: '/sing' },
  { label: '报表 (M3)', to: '/stats' },
]

function login() {
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-[#F9FAFB]">
    <header class="sticky top-0 z-10 border-b border-[#E5E7EB] bg-white">
      <nav class="mx-auto flex max-w-[1080px] items-center gap-2 px-4 py-3">
        <RouterLink to="/demo" class="flex items-center gap-2 pr-4">
          <span class="inline-block h-3.5 w-3.5 rounded-full bg-brand" />
          <span class="text-lg font-bold">VocalVerse 声语界</span>
        </RouterLink>
        <RouterLink
          v-for="link in nav"
          :key="link.to"
          :to="link.to"
          class="rounded-full px-4 py-1.5 text-sm text-[#667085] transition-colors hover:bg-[#ECFDF5] hover:text-brand-deep"
          active-class="bg-[#ECFDF5] text-brand-deep font-semibold"
        >
          {{ link.label }}
        </RouterLink>
        <NButton class="ml-auto" round size="small" type="primary" @click="login">
          登录
        </NButton>
      </nav>
    </header>
    <main class="mx-auto max-w-[1080px] px-4 py-6">
      <router-view />
    </main>
  </div>
</template>
