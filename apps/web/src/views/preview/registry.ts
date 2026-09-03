/**
 * 预览页注册表（docs/13 §8）：新增预览页 = ① router/preview.ts 加路由 ② 此处登记。
 * layout 字段决定画廊的默认渲染模式：以真实布局（UserLayout/AdminLayout）包裹，
 * 保证"所见即生产"——视觉验收时 TopNav/侧边栏关系与集成后完全一致（docs/13 §8 盲点修正）。
 */
export interface PreviewPage {
  path: string
  label: string
  group: '用户端' | '管理端'
  layout: 'user' | 'admin' | 'gallery'
}

export const previewPages: PreviewPage[] = [
  { path: '/preview/home', label: '学习主页', group: '用户端', layout: 'user' },
  { path: '/preview/agent-lab', label: 'Agent Lab · LLM 框架测试台', group: '用户端', layout: 'gallery' },
  {
    path: '/preview/fluency',
    label: '流利度特征 · 联调测试台（docs/06 §9.3）',
    group: '用户端',
    layout: 'gallery',
  },
  {
    path: '/preview/shadow',
    label: '影子跟读 · 联调测试台（DoD ④）',
    group: '用户端',
    layout: 'gallery',
  },
  {
    path: '/preview/placement',
    label: 'Placement Lab · 入学测试联调测试台（C1/C5/C8）',
    group: '用户端',
    layout: 'gallery',
  },
  { path: '/preview/admin-dashboard', label: '评价看板（可视化）', group: '管理端', layout: 'admin' },
  { path: '/preview/admin-users', label: '用户管理', group: '管理端', layout: 'admin' },
  { path: '/preview/lieflat', label: 'Lieflat 表盘（高保真）', group: '管理端', layout: 'gallery' },
]
