import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { bootstrapAuth } from './stores/auth'

import 'virtual:uno.css'
import './styles/global.css'

// 启动即恢复会话：token 从 localStorage 恢复到 client.ts 全局（供 request/SSE 自动携带）
void bootstrapAuth().catch(() => undefined)

createApp(App).use(createPinia()).use(router).mount('#app')
