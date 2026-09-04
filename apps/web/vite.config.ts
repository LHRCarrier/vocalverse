import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import Icons from 'unplugin-icons/vite'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    UnoCSS(),
    // 图标：unplugin-icons 编译期按需内联 SVG（docs/32 §1.2）——tabler 主 / ph 深色卡大图形
    Icons({ compiler: 'vue3', autoInstall: false }),
  ],
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
    // P1-#10：组件测试挂载需要 DOM 环境（happy-dom，docs/13）
    environment: 'happy-dom',
    include: ['src/**/*.test.ts', 'tests/**/*.test.ts'],
  },
})
