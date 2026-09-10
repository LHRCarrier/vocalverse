/**
 * 预览页注册表（docs/13 §8）：新增预览页 = ① router/preview.ts 加路由 ② 此处登记。
 * layout 字段决定画廊的默认渲染模式：以真实布局（UserLayout）包裹，
 * 保证"所见即生产"——视觉验收时 TopNav/侧边栏关系与集成后完全一致（docs/13 §8 盲点修正）。
 *
 * ⚠️ 已移除 `'admin'` 布局模式与两个旧管理端预览页（`admin-dashboard` / `admin-users`）：
 * 旧管理端已废弃，`/admin` 路由与 `AdminLayout.vue` 一并删除；管理端唯一形态是
 * **独立 SPA `apps/admin`**（入口 `/console/`），它不共享用户端布局，故画廊里不模拟它。
 * 依据：docs/50 §2（ADR 修订申请 1）、docs/51 §1.3 C-1/C-9。
 */
export interface PreviewPage {
  path: string
  label: string
  group: '用户端' | '管理端'
  layout: 'user' | 'gallery'
}

export const previewPages: PreviewPage[] = [
  { path: '/preview/home', label: '学习主页', group: '用户端', layout: 'user' },
  { path: '/preview/uic-home', label: 'UIC 概念 · 学习主页', group: '用户端', layout: 'gallery' },
  { path: '/preview/uic-speaking', label: 'UIC 概念 · 口语陪练', group: '用户端', layout: 'gallery' },
  { path: '/preview/uic-singing', label: 'UIC 概念 · 唱歌评分报告', group: '用户端', layout: 'gallery' },
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
    path: '/preview/community',
    label: '社区内容 S1 · 真实流联调台',
    group: '用户端',
    layout: 'gallery',
  },
  {
    path: '/preview/community-s3',
    label: '社区内容 S3 · 媒体闭环联调台（docs/47）',
    group: '用户端',
    layout: 'gallery',
  },
  {
    path: '/preview/reading',
    label: '读书域 · 查词/书架联调台（docs/45）',
    group: '用户端',
    layout: 'gallery',
  },
  { path: '/preview/lieflat', label: 'Lieflat 表盘（高保真）', group: '管理端', layout: 'gallery' },
  {
    path: '/preview/admin-console',
    label: '管理端控制台 · 联调桥接（docs/50）',
    group: '管理端',
    layout: 'gallery',
  },
]
