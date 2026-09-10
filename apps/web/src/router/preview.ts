import type { RouteRecordRaw } from 'vue-router'

/**
 * 前端预览画廊（docs/13 §8 预览工作流）。
 *
 * ⚠️ 仅开发环境：整棵子树被包在 `import.meta.env.DEV` 三元里，
 * 生产构建常量折叠后整个分支（含所有动态 import）被 Rollup 剔除——零体积、零路由。
 *
 * 流程纪律：新页面先在 preview/ 里做静态高保真 → 视觉验收（docs/13 §8 验收表）→
 * 再集成为真实 view；preview 页直接复用 tokens/主题/布局组件，token 零漂移。
 */
export const previewRoute: RouteRecordRaw | null = import.meta.env.DEV
  ? {
      path: '/preview',
      component: () => import('@/views/preview/PreviewLayout.vue'),
      meta: { title: '前端预览画廊' },
      children: [
        { path: '', redirect: '/preview/home' },
        { path: 'home', component: () => import('@/views/preview/HomePreview.vue') },
        {
          path: 'uic-home',
          component: () => import('@/views/preview/uic/UicHome.vue'),
        },
        {
          path: 'uic-speaking',
          component: () => import('@/views/preview/uic/UicSpeaking.vue'),
        },
        {
          path: 'uic-singing',
          component: () => import('@/views/preview/uic/UicSinging.vue'),
        },
        {
          path: 'agent-lab',
          component: () => import('@/views/preview/AgentLabPreview.vue'),
        },
        {
          path: 'fluency',
          component: () => import('@/views/preview/FluencyPreview.vue'),
        },
        {
          path: 'shadow',
          component: () => import('@/views/preview/ShadowPreview.vue'),
        },
        {
          path: 'community',
          component: () => import('@/views/preview/CommunityPreview.vue'),
        },
        {
          path: 'singing',
          component: () => import('@/views/preview/SingingPreview.vue'),
        },
        {
          path: 'community-s3',
          component: () => import('@/views/preview/CommunityS3Preview.vue'),
        },
        {
          path: 'reading',
          component: () => import('@/views/preview/ReadingPreview.vue'),
        },
        {
          path: 'lieflat',
          component: () => import('@/views/preview/LieflatPreview.vue'),
        },
        {
          // 管理端控制台联调桥接页（docs/50 §14.4 · AGENTS 工作流程 §3）。
          // 只探活 + 对照，不 import apps/admin 源码；删除清单见该文件尾注释。
          path: 'admin-console',
          component: () => import('@/views/preview/AdminConsolePreview.vue'),
        },
      ],
    }
  : null
