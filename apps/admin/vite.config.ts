import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import Icons from 'unplugin-icons/vite'
import { defineConfig } from 'vite'

/**
 * 管理端控制台（独立 SPA · docs/50）。
 *
 * ⚠️ 两上游代理（与 `apps/web/vite.config.ts` 的 `/manage` 块**同语义**，改一处必须改两处 + nginx）：
 *   - `/manage`  → Java :8080（**rewrite 剥前缀**）—— 控制台域：身份/RBAC/审计/审核/内容
 *   - `/api/v1`  → Python :8000（不剥）        —— 控制台域：运维/指标/预警/LLM trace/书籍
 * 生产由 nginx 承担同一分流（见 apps/admin/nginx.conf）。
 *
 * 端口 5174：避开 `apps/web` 的 5173，两者可同时起（联调时控制台与 App 各占一端）。
 */
export default defineConfig({
  // Icons：编译期内联（与 apps/web 同口径，docs/32 选型 = Tabler 单一功能图标源）。
  // autoInstall:false —— 图标集必须已在 devDependencies 声明（@iconify-json/tabler），
  // 否则构建期静默安装会让 CI 与本地不一致。
  plugins: [vue(), UnoCSS(), Icons({ compiler: 'vue3', autoInstall: false })],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5174,
    host: true,
    proxy: {
      '/manage': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/manage/, ''),
      },
      '/api/v1': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        // naive-ui 与 echarts 体积巨大（各 ~3.9MB 原始）——独立成 chunk，
        // 登录页首屏不加载它们（控制台是独立产物，不受 apps/web 的 bundle 断言约束）
        manualChunks: {
          'vendor-naive': ['naive-ui'],
          'vendor-echarts': ['echarts/core', 'echarts/charts', 'echarts/components', 'echarts/renderers'],
        },
      },
    },
  },
})
