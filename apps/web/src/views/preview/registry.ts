/**
 * 预览页注册表（docs/13 §8）：新增预览页 = ① router/preview.ts 加路由 ② 此处登记
 * （label/group 决定画廊菜单分组）。group 与预览页保持一致即可。
 */
export interface PreviewPage {
  path: string
  label: string
  group: '用户端' | '管理端'
}

export const previewPages: PreviewPage[] = [
  { path: '/preview/home', label: '学习主页', group: '用户端' },
  { path: '/preview/practice', label: '场景对话 ★核心', group: '用户端' },
  { path: '/preview/report', label: '评分报告', group: '用户端' },
  { path: '/preview/admin-dashboard', label: '评价看板（可视化）', group: '管理端' },
  { path: '/preview/admin-users', label: '用户管理', group: '管理端' },
]
