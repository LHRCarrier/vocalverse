import { createRouter, createWebHistory } from 'vue-router'

import type { RouteRecordRaw } from 'vue-router'

import { track } from '@/api/events'
import { previewRoute } from './preview'

/**
 * 路由表（docs/13 §3）：M2/M3 页面排期见 docs/04。
 * 懒加载：图表/动效等重依赖在各自的页面 chunk 里（按页动态 import），不进首屏。
 */
const routes: RouteRecordRaw[] = [
  /* ---- 移动端真形态（App 主界面 · 原型 ui-concept-design/app）---- */
  {
    path: '/m/home',
    component: () => import('@/views/mobile/MobileHomeView.vue'),
    meta: { title: '今日学习', requiresAuth: true },
  },
  {
    path: '/m/free-chat',
    component: () => import('@/views/mobile/MobileFreeChatView.vue'),
    meta: { title: '自由对话', requiresAuth: true },
  },
  {
    path: '/m/chat/:sceneId?',
    component: () => import('@/views/mobile/MobileSpeakingView.vue'),
    meta: { title: '场景对话', requiresAuth: true },
  },
  {
    path: '/m/report',
    component: () => import('@/views/mobile/MobileReportView.vue'),
    meta: { title: '评分报告', requiresAuth: true },
  },
  {
    path: '/m/sing',
    component: () => import('@/views/mobile/MobileSingView.vue'),
    meta: { title: '唱吧', requiresAuth: true },
  },
  {
    path: '/m/learn',
    component: () => import('@/views/mobile/MobileLearnView.vue'),
    meta: { title: '学习', requiresAuth: true },
  },
  {
    path: '/m/learn/:module',
    component: () => import('@/views/mobile/MobileLearnModuleView.vue'),
    meta: { title: '学习模块', requiresAuth: true },
  },
  {
    path: '/m/notifications',
    component: () => import('@/views/mobile/MobileNotificationsView.vue'),
    meta: { title: '通知', requiresAuth: true },
  },
  {
    path: '/m/messages',
    component: () => import('@/views/mobile/MobileMessagesView.vue'),
    meta: { title: '私信', requiresAuth: true },
  },
  {
    path: '/m/messages/:id',
    component: () => import('@/views/mobile/MobileChatView.vue'),
    meta: { title: '私信', requiresAuth: true },
  },
  {
    path: '/m/search',
    component: () => import('@/views/mobile/MobileSearchView.vue'),
    meta: { title: '搜索', requiresAuth: true },
  },
  {
    path: '/m/compose',
    component: () => import('@/views/mobile/MobileComposeView.vue'),
    meta: { title: '发帖', requiresAuth: true },
  },
  /* ---- 社区 S3（docs/47 §5.1）：帖子详情 / 我的资料；均沉浸页（无底栏） ---- */
  {
    path: '/m/post/:postId',
    component: () => import('@/views/mobile/MobilePostDetailView.vue'),
    meta: { title: '内容', requiresAuth: true },
  },
  {
    path: '/m/me/profile',
    component: () => import('@/views/mobile/MobileProfileView.vue'),
    meta: { title: '我的资料', requiresAuth: true },
  },
  {
    path: '/m/me/posts',
    component: () => import('@/views/mobile/MobileMyPostsView.vue'),
    meta: { title: '我的发帖', requiresAuth: true },
  },
  {
    path: '/m/notes',
    component: () => import('@/views/mobile/MobileNotesView.vue'),
    meta: { title: '笔记', requiresAuth: true },
  },
  /* ---- 读书域（docs/45 · 书架/书详情/阅读器/生词本；阅读器沉浸无底栏） ---- */
  {
    path: '/m/bookshelf',
    component: () => import('@/views/mobile/MobileBookshelfView.vue'),
    meta: { title: '书房', requiresAuth: true },
  },
  {
    path: '/m/books/:bookId',
    component: () => import('@/views/mobile/MobileBookDetailView.vue'),
    meta: { title: '书籍详情', requiresAuth: true },
  },
  {
    path: '/m/reader/:chapterId',
    component: () => import('@/views/mobile/MobileReaderView.vue'),
    meta: { title: '阅读', requiresAuth: true },
  },
  {
    path: '/m/vocab',
    component: () => import('@/views/mobile/MobileVocabView.vue'),
    meta: { title: '生词本', requiresAuth: true },
  },

  {
    path: '/',
    component: () => import('@/layouts/UserLayout.vue'),
    children: [
      { path: '', redirect: '/m/home' },
      {
        path: 'demo',
        component: () => import('@/views/DemoView.vue'),
        meta: { title: '骨架演示' },
      },
      {
        path: 'placement',
        component: () => import('@/views/PlacementView.vue'),
        meta: { title: '入学测试', requiresAuth: true },
      },
      {
        path: 'practice',
        component: () => import('@/views/PracticeHubView.vue'),
        meta: { title: '练习', requiresAuth: true },
      },
      {
        path: 'practice/:sceneId',
        component: () => import('@/views/PracticeView.vue'),
        meta: { title: '场景对话', requiresAuth: true },
      },
      {
        path: 'defense',
        component: () => import('@/views/DefenseView.vue'),
        meta: { title: '答辩导师', requiresAuth: true },
      },
      {
        path: 'report/:reportId',
        component: () => import('@/views/ReportView.vue'),
        meta: { title: '评分报告', requiresAuth: true },
      },
      {
        path: 'recommend',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '推荐', desc: '内容推荐 + 水平预测模型（docs/06 §9.5）——M3' },
        meta: { title: '推荐' },
      },
      {
        path: 'sing',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '唱吧', desc: '英文歌跟唱：音准/节奏/发音逐句评分（docs/06 §9.4）——M3' },
        meta: { title: '唱吧' },
      },
      {
        path: 'stats',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '报表', desc: '趋势/雷达图/四指标看板（docs/06 §9.1）——M3' },
        meta: { title: '报表' },
      },
      {
        path: 'community',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '社区', desc: '打卡 + 成绩卡片分享 + 动态流（docs/06 §9.6）——M3' },
        meta: { title: '社区' },
      },
    ],
  },
  {
    path: '/login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/admin',
    component: () => import('@/layouts/AdminLayout.vue'),
    redirect: '/admin/users',
    children: [
      {
        path: 'users',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '用户管理' },
        meta: { title: '用户管理' },
      },
      {
        path: 'scenes',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '场景库' },
        meta: { title: '场景库' },
      },
      {
        path: 'songs',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '歌曲库' },
        meta: { title: '歌曲库' },
      },
      {
        path: 'tickets',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '工单' },
        meta: { title: '工单' },
      },
      {
        path: 'dashboard',
        component: () => import('@/views/PlaceholderView.vue'),
        props: { title: '评价看板' },
        meta: { title: '评价看板' },
      },
    ],
  },
]

// 前端预览画廊：仅 DEV 注入（router/preview.ts 内 import.meta.env.DEV 三元，生产构建整支剔除）；
// 必须插在 catch-all 之前，否则被通配吞掉。
if (previewRoute) routes.push(previewRoute)
routes.push({ path: '/:pathMatch(.*)*', redirect: '/demo' })

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 登录守卫：requiresAuth 路由无 token → 登录页（docs/18 §3-F3；token 恢复见 stores/auth）
router.beforeEach((to) => {
  if (to.meta.requiresAuth && !localStorage.getItem('vv_token')) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  return true
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${String(to.meta.title)} · VocalVerse 声语界`
    : 'VocalVerse 声语界'
  // 登录页专属 body 背景：mobile-uic.css 全局把 body 钉为移动端灰底（#edece8 !important），
  // 退出登录（SPA 导航）后 body 残留该背景会让登录卡配色错位——用 .is-login 类切回纸白底（2026-09-06）。
  document.body.classList.toggle('is-login', to.path === '/login')
  // 页面曝光埋点（docs/06 §9.1 fe-06）：fire-and-forget，非关键路径不阻塞导航；
  // 重复上报由后端 client_event_id 幂等去重兜底。
  void track('page_view', { page: to.path })
})

export default router
