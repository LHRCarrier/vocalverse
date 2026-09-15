/**
 * 管理员列表的展示助手（`AdminsView` 抽出：页面本体要留在 ESLint `max-lines` 之下）。
 *
 * 权威：Java `ConsoleRbacController.AdminView` —— 角色是**扁平三字段**
 * （`roleId` / `roleCode` / `roleName`），v1 读的 `role: {id,code,name}` 对象后端不存在，
 * 于是「角色」列一直渲染成空白徽标。
 */
import { h } from 'vue'
import type { VNodeChild } from 'vue'

import type { AdminUserRow } from '@/api'
import { ROLE_LABEL } from '@/router/nav'
import { fmtDateTime, fmtInt } from '@/utils/format'

/**
 * 角色徽标：内置角色（super/ops/operator/moderator）用 `nav.ts` 的统一定义，
 * 自定义角色直接用后端给的 `roleName`；两者都没有时回落到 `roleCode`。
 * `title` 始终给 `roleCode`，方便对着权限矩阵与审计里的 code 排查。
 */
export function roleBadge(row: AdminUserRow): VNodeChild {
  const code = row.roleCode ?? ''
  const meta = ROLE_LABEL[code] ?? { name: row.roleName ?? code, tone: 'muted' as const }
  return h('span', { class: `c-badge c-badge--${meta.tone}`, title: code }, meta.name || '—')
}

/**
 * 账号状态下的第二行：锁定信息（`lockedUntil` + 累计失败次数）。
 *
 * 为什么值得显示：`ConsoleAuthService` 的锁定阈值是「同账号 5 次 / 15 分钟」（§4.1），
 * 不显示的话运营只能靠"用户说登不上"来猜；失败次数是能直接指向爆破的线索。
 */
export function accountLockNote(row: AdminUserRow): VNodeChild {
  if (row.lockedUntil) {
    return h('span', { class: 'c-weak text-12px' }, `锁定至 ${fmtDateTime(row.lockedUntil)}`)
  }
  if (row.failedAttempts) {
    return h('span', { class: 'c-weak text-12px' }, `失败 ${fmtInt(row.failedAttempts)} 次`)
  }
  return null
}
