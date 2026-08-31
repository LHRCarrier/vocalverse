import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      // 语音/LLM 热路径：直连 Python（docs/06 第 1 章）
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/healthz': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/readyz': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // 管理端与 JWT 签发：Java
      // ⚠️ 与 apps/web/nginx.conf 的 location /manage/ 保持语义一致（此处 rewrite 去前缀 =
      //    nginx 的 proxy_pass http://java-api:8080/ 尾斜杠剥离）。两处只能同步改，
      //    否则 dev（5173）与容器（8088）的 /manage 行为分叉（docs/06 §2.1 注记 3）。
      '/manage': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/manage/, ''),
      },
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts', 'tests/**/*.test.ts'],
  },
})
