/**
 * 导航模型（docs/50 §11.3）。
 *
 * 两条硬规则：
 * 1. **一级分组必须与"域"一致**（总览/运维/运营/审核/系统），
 *    **不按角色重排导航**——否则同一个功能在不同角色下有不同位置，组员联调时对不上；
 *    角色差异只体现为"看得见/看不见"。
 * 2. 菜单项只声明**一个**权限码（或"任一"语义用数组），与实际端点所需权限码一致。
 */

export interface NavItem {
  label: string
  path: string
  /** 图标名（Tabler，编译期内联）：`~icons/tabler/xxx` 的后半段 */
  icon: string
  /** 无权限码 = 登录即可见 */
  permission?: string | string[]
  /** 需要"全部"还是"任一"（默认全部） */
  anyOf?: boolean
}

export interface NavGroup {
  key: string
  label: string
  items: NavItem[]
}

export const NAV_GROUPS: NavGroup[] = [
  {
    key: 'overview',
    label: '总览',
    items: [{ label: '工作台', path: '/', icon: 'layout-dashboard' }],
  },
  {
    key: 'ops',
    label: '运维',
    items: [
      { label: '服务总览', path: '/ops', icon: 'activity', permission: 'ops:overview:read' },
      { label: '性能指标', path: '/ops/metrics', icon: 'chart-line', permission: 'ops:metric:read' },
      { label: '预警中心', path: '/ops/alerts', icon: 'alert-triangle', permission: 'ops:alert:read' },
      { label: 'LLM Trace', path: '/ops/traces', icon: 'route', permission: 'ops:trace:read' },
    ],
  },
  {
    key: 'content',
    label: '运营',
    items: [
      { label: '歌曲库', path: '/content/songs', icon: 'music', permission: 'content:song:read' },
      {
        label: '听力素材',
        path: '/content/listening',
        icon: 'headphones',
        permission: 'content:listening:read',
      },
      { label: '书籍', path: '/content/books', icon: 'book', permission: 'content:book:read' },
      { label: '场景库', path: '/content/scenarios', icon: 'messages', permission: 'content:scenario:read' },
      { label: '媒体库', path: '/content/media', icon: 'photo', permission: 'content:media:read' },
      { label: '工单', path: '/content/tickets', icon: 'ticket', permission: 'content:ticket:read' },
      {
        label: '上架流水',
        path: '/content/publish-events',
        icon: 'history',
        permission: ['content:song:read', 'content:book:read'],
        anyOf: true,
      },
    ],
  },
  {
    key: 'moderation',
    label: '审核',
    items: [
      { label: '待审队列', path: '/moderation/queue', icon: 'inbox', permission: 'moderation:queue:read' },
      { label: '举报处理', path: '/moderation/reports', icon: 'flag', permission: 'moderation:report:read' },
      {
        label: '处置记录',
        path: '/moderation/actions',
        icon: 'gavel',
        permission: 'console:audit:read',
      },
    ],
  },
  {
    key: 'system',
    label: '系统',
    items: [
      { label: '管理员', path: '/system/admins', icon: 'users', permission: 'console:admin:read' },
      { label: '角色权限', path: '/system/roles', icon: 'key', permission: 'console:role:read' },
      { label: '审计日志', path: '/system/audit-logs', icon: 'clipboard-list', permission: 'console:audit:read' },
    ],
  },
]

/** 角色 code → 中文名 + 徽标色（docs/50 §4.2） */
export const ROLE_LABEL: Record<string, { name: string; tone: 'info' | 'ok' | 'warn' | 'muted' }> = {
  super: { name: '超级管理员', tone: 'info' },
  ops: { name: '运维', tone: 'ok' },
  operator: { name: '运营', tone: 'warn' },
  moderator: { name: '审核', tone: 'muted' },
}
