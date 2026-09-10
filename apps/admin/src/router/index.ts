import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { setUnauthorizedHandler } from '@/api'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    /** 免登录（仅登录页） */
    public?: boolean
    /** 进入所需权限码；数组 = 全部满足 */
    permission?: string | string[]
    /**
     * 满足其一即可（与 nav.ts 的 `anyOf` 对应）。
     * 存在理由：上架流水由多个内容域共享，只授了书籍读权限的运营也该看到它——
     * 若这里写成「全部满足」，菜单（nav 用 anyOf）会显示而路由 403，用户点了才被拒。
     */
    permissionAny?: string[]
  }
}

/**
 * 路由表（docs/50 §11.3）。
 * `meta.permission` 与后端权限码一一对应；守卫失败跳 `/403`（不是 `/login`——
 * 已登录但无权限与未登录是两回事，混在一起会让用户反复"重新登录"却进不去）。
 */
const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: () => import('@/layouts/ConsoleLayout.vue'),
    children: [
      {
        path: '',
        name: 'dashboard',
        component: () => import('@/views/DashboardView.vue'),
        meta: { title: '工作台' },
      },

      // ── 运维 ────────────────────────────────────────────────────────────
      {
        path: 'ops',
        name: 'ops-overview',
        component: () => import('@/views/ops/OpsOverviewView.vue'),
        meta: { title: '服务总览', permission: 'ops:overview:read' },
      },
      {
        path: 'ops/metrics',
        name: 'ops-metrics',
        component: () => import('@/views/ops/OpsMetricsView.vue'),
        meta: { title: '性能指标', permission: 'ops:metric:read' },
      },
      {
        path: 'ops/alerts',
        name: 'ops-alerts',
        component: () => import('@/views/ops/OpsAlertsView.vue'),
        meta: { title: '预警中心', permission: 'ops:alert:read' },
      },
      {
        path: 'ops/traces',
        name: 'ops-traces',
        component: () => import('@/views/ops/TraceListView.vue'),
        meta: { title: 'LLM Trace', permission: 'ops:trace:read' },
      },
      {
        path: 'ops/traces/:traceId',
        name: 'ops-trace-detail',
        component: () => import('@/views/ops/TraceDetailView.vue'),
        meta: { title: 'Trace 详情', permission: 'ops:trace:read' },
      },

      // ── 运营 ────────────────────────────────────────────────────────────
      {
        path: 'content/songs',
        name: 'content-songs',
        component: () => import('@/views/content/SongsView.vue'),
        meta: { title: '歌曲库', permission: 'content:song:read' },
      },
      {
        path: 'content/listening',
        name: 'content-listening',
        component: () => import('@/views/content/ListeningView.vue'),
        meta: { title: '听力素材', permission: 'content:listening:read' },
      },
      {
        path: 'content/books',
        name: 'content-books',
        component: () => import('@/views/content/BooksView.vue'),
        meta: { title: '书籍', permission: 'content:book:read' },
      },
      {
        path: 'content/scenarios',
        name: 'content-scenarios',
        component: () => import('@/views/content/ScenariosView.vue'),
        meta: { title: '场景库', permission: 'content:scenario:read' },
      },
      {
        path: 'content/media',
        name: 'content-media',
        component: () => import('@/views/content/MediaView.vue'),
        meta: { title: '媒体库', permission: 'content:media:read' },
      },
      {
        // 工单：旧管理端工单面已随旧管理端退役 → 这里是工单的**唯一**处理入口（docs/50 §15.5 复核项 ①）
        path: 'content/tickets',
        name: 'content-tickets',
        component: () => import('@/views/content/TicketsView.vue'),
        meta: { title: '工单', permission: 'content:ticket:read' },
      },
      {
        path: 'content/publish-events',
        name: 'content-publish-events',
        component: () => import('@/views/content/PublishEventsView.vue'),
        // 任一内容域读权限即可（与 nav.ts 的 anyOf 对齐，别让菜单与路由判定打架）
        meta: {
          title: '上架流水',
          permissionAny: ['content:song:read', 'content:listening:read', 'content:book:read'],
        },
      },

      // ── 审核 ────────────────────────────────────────────────────────────
      {
        path: 'moderation/queue',
        name: 'moderation-queue',
        component: () => import('@/views/moderation/QueueView.vue'),
        meta: { title: '待审队列', permission: 'moderation:queue:read' },
      },
      {
        path: 'moderation/reports',
        name: 'moderation-reports',
        component: () => import('@/views/moderation/ReportsView.vue'),
        meta: { title: '举报处理', permission: 'moderation:report:read' },
      },
      {
        path: 'moderation/actions',
        name: 'moderation-actions',
        component: () => import('@/views/moderation/ActionsView.vue'),
        meta: { title: '处置记录', permission: 'console:audit:read' },
      },

      // ── 系统 ────────────────────────────────────────────────────────────
      {
        path: 'system/admins',
        name: 'system-admins',
        component: () => import('@/views/system/AdminsView.vue'),
        meta: { title: '管理员', permission: 'console:admin:read' },
      },
      {
        path: 'system/roles',
        name: 'system-roles',
        component: () => import('@/views/system/RolesView.vue'),
        meta: { title: '角色权限', permission: 'console:role:read' },
      },
      {
        path: 'system/audit-logs',
        name: 'system-audit-logs',
        component: () => import('@/views/system/AuditLogsView.vue'),
        meta: { title: '审计日志', permission: 'console:audit:read' },
      },
    ],
  },
  {
    path: '/403',
    name: 'forbidden',
    component: () => import('@/views/ForbiddenView.vue'),
    meta: { title: '无权限', public: true },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { title: '页面不存在', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

// client 层不做路由跳转（避免循环依赖）——由这里注入"令牌失效"的出口
setUnauthorizedHandler(() => {
  const current = router.currentRoute.value
  if (current.name !== 'login') {
    void router.replace({ path: '/login', query: { redirect: current.fullPath } })
  }
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (to.meta.public) {
    // 已登录再访问登录页 → 回工作台
    if (to.name === 'login' && auth.isLoggedIn) return { path: '/' }
    return true
  }

  if (!auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 令牌存在但档案未拉取（刷新页面 / 直接深链）——先补档案再判权限
  if (!auth.profile) {
    try {
      await auth.fetchMe()
    } catch {
      auth.clear()
      return { path: '/login', query: { redirect: to.fullPath } }
    }
  }

  if (to.meta.permissionAny?.length && !auth.hasAny(to.meta.permissionAny)) {
    return { path: '/403', query: { from: to.fullPath } }
  }

  if (!auth.hasPermission(to.meta.permission ?? null)) {
    return { path: '/403', query: { from: to.fullPath } }
  }

  return true
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · VocalVerse 控制台` : 'VocalVerse 控制台'
})

export default router
