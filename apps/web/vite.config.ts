import { fileURLToPath, URL } from 'node:url'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

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
  build: {
    // fe-09 包门禁脚本按 manifest 源模块路径判定（字符串猜测会误报：见 check-bundle.mjs 注）
    manifest: true,
    rollupOptions: {
      output: {
        // fe-09（2026-09-09）manualChunks：大依赖出专块——
        // · 移动端 WebView 首屏不解析 desktop 侧 naive-ui（走懒加载块）；
        // · p5/echarts 保持独立块（本就是动态 import，rename 仅防合流）；
        // · vue 栈稳定快照块提高缓存命中（应用发布不重拉框架代码）。
        // CI 门禁 apps/web/scripts/check-bundle.mjs 断言：preview 树零体积、
        // p5 不进入口块、echarts 零残留——与 production 行为绑定，防回潮。
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/naive-ui/')) return 'naive-ui'
          if (id.includes('/p5/')) return 'p5'
          if (id.includes('/echarts/')) return 'echarts'
          if (id.includes('/vue/') || id.includes('/vue-router/') || id.includes('/pinia/')) {
            return 'vue-vendor'
          }
          return 'vendor'
        },
      },
    },
  },
  server: {
    port: 5173,
    /**
     * HTTPS（可选，2026-09-10 组长拍板「方案 A」：手机端录音 getUserMedia 要求安全上下文）。
     * 默认关闭（局域网 HTTP 仍可用）；要开就设 VITE_HTTPS_CERT/VITE_HTTPS_KEY 指向证书。
     * 证书用 mkcert 生成（含 192.168.0.104/localhost/127.0.0.1 的 SAN）→ 手机装一次 CA 即信任。
     */
    https:
      process.env.VITE_HTTPS_CERT && process.env.VITE_HTTPS_KEY
        ? {
            cert: readFileSync(resolve(process.env.VITE_HTTPS_CERT)),
            key: readFileSync(resolve(process.env.VITE_HTTPS_KEY)),
          }
        : undefined,
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
