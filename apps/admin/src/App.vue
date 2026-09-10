<script setup lang="ts">
/**
 * 应用根（docs/50 §11.1）。
 *
 * naive-ui 主题的**唯一注入点**——与 `apps/web/src/App.vue:39` 同一模式：
 * 全局 provider 只挂一次，页面不各自 override（否则主题会分叉成多套）。
 */
import {
  NConfigProvider,
  NDialogProvider,
  NLoadingBarProvider,
  NMessageProvider,
  zhCN,
  dateZhCN,
} from 'naive-ui'

import { themeOverrides } from '@/theme/naive'
</script>

<template>
  <n-config-provider :theme-overrides="themeOverrides" :locale="zhCN" :date-locale="dateZhCN">
    <n-loading-bar-provider>
      <n-message-provider>
        <n-dialog-provider>
          <router-view />
        </n-dialog-provider>
      </n-message-provider>
    </n-loading-bar-provider>
  </n-config-provider>
</template>
