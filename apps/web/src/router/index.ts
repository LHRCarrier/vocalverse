import { createRouter, createWebHistory } from 'vue-router'

/**
 * 路由表（docs/13 §3）：M2/M3 页面排期见 docs/04。
 * 懒加载：图表/动效等重依赖在各自的页面 chunk 里（按页动态 import），不进首屏。
 */
const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      component: () => import('@/layouts/UserLayout.vue'),
      children: [
        { path: '', redirect: '/demo' },
        {
          path: 'demo',
          component: () => import('@/views/DemoView.vue'),
          meta: { title: '骨架演示' },
        },
        {
          path: 'placement',
          component: () => import('@/views/PlaceholderView.vue'),
          props: {
            title: '入学测试',
            desc: '5 句固定朗读 + 1 轮 QA（docs/06 §9.2，题库 admin 预置）——M2 第 2 周',
          },
          meta: { title: '入学测试' },
        },
        {
          path: 'practice/:sceneId',
          component: () => import('@/views/PlaceholderView.vue'),
          props: {
            title: '场景对话',
            desc: 'DeepSeek 多轮 + SSE 流式 + TTS 排队播放（docs/06 §8）——M2 主线',
          },
          meta: { title: '场景对话' },
        },
        {
          path: 'report/:attemptId',
          component: () => import('@/views/PlaceholderView.vue'),
          props: {
            title: '评分报告',
            desc: '音素级错误定位 + 正确示范 + 改进建议（docs/06 §9.3）——M2',
          },
          meta: { title: '评分报告' },
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
        { path: 'users', component: () => import('@/views/PlaceholderView.vue'), props: { title: '用户管理' }, meta: { title: '用户管理' } },
        { path: 'scenes', component: () => import('@/views/PlaceholderView.vue'), props: { title: '场景库' }, meta: { title: '场景库' } },
        { path: 'songs', component: () => import('@/views/PlaceholderView.vue'), props: { title: '歌曲库' }, meta: { title: '歌曲库' } },
        { path: 'tickets', component: () => import('@/views/PlaceholderView.vue'), props: { title: '工单' }, meta: { title: '工单' } },
        { path: 'dashboard', component: () => import('@/views/PlaceholderView.vue'), props: { title: '评价看板' }, meta: { title: '评价看板' } },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/demo' },
  ],
})

router.afterEach((to) => {
  document.title = to.meta.title
    ? `${String(to.meta.title)} · VocalVerse 声语界`
    : 'VocalVerse 声语界'
})

export default router
