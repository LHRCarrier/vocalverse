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
          path: 'agent-lab',
          component: () => import('@/views/preview/AgentLabPreview.vue'),
        },
        {
          path: 'admin-dashboard',
          component: () => import('@/views/preview/AdminDashboardPreview.vue'),
        },
        {
          path: 'admin-users',
          component: () => import('@/views/preview/AdminUsersPreview.vue'),
        },
        {
          path: 'lieflat',
          component: () => import('@/views/preview/LieflatPreview.vue'),
        },
      ],
    }
  : null
