import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { bootstrapAuth } from './stores/auth'
import router from './router'

import 'virtual:uno.css'
import './styles/global.css'

/**
 * 启动即恢复会话：token 从 localStorage 恢复到 client.ts 全局（供 request/SSE 自动携带）。
 * 时序硬约束：必须在 app.use(pinia) 之后、mount 之前调用——useAuthStore() 依赖 active pinia，
 * 提前调用会抛错且被 .catch 静默吞掉 → 整页刷新/App 冷启后所有请求 401「missing bearer token」。
 * bootstrapAuth 的同步段（useAuthStore → setAuthToken）先于 mount 执行，页面 onMounted 的
 * 首个 API 请求就已经带上 token。
 */
const app = createApp(App).use(createPinia()).use(router)
void bootstrapAuth().catch(() => undefined)
app.mount('#app')
