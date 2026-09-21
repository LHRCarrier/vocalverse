/**
 * 控制台导航图标映射（编译期内联）。
 *
 * ⚠️ 为什么用显式映射而不是 `<component :is="'~icons/tabler/' + name" />`：
 * `unplugin-icons` 是**编译期**虚拟模块，只有字面量 `import IconX from '~icons/tabler/x'`
 * 才会被解析；运行时拼字符串拿不到组件，会渲染成空标签（静默失效）。
 * 显式映射还顺带带来 Tree-shaking：用不到的图标不进产物。
 *
 * 图标源：Tabler 单一功能图标源（docs/32 选型 + docs/35 硬规则）。
 *
 * 独立成 .ts（2026-09-21）：`<script setup>` 不允许 ES module export，而回归测试需要
 * 拿到「已登记图标名」清单（漏登记 = 侧栏静默空白，见 navIcon.test.ts）。
 */
import IconActivity from '~icons/tabler/activity'
import IconAlertTriangle from '~icons/tabler/alert-triangle'
import IconBook from '~icons/tabler/book'
import IconChartLine from '~icons/tabler/chart-line'
import IconClipboardList from '~icons/tabler/clipboard-list'
import IconDice from '~icons/tabler/dice'
import IconFlag from '~icons/tabler/flag'
import IconGavel from '~icons/tabler/gavel'
import IconHeadphones from '~icons/tabler/headphones'
import IconHistory from '~icons/tabler/history'
import IconInbox from '~icons/tabler/inbox'
import IconKey from '~icons/tabler/key'
import IconLayoutDashboard from '~icons/tabler/layout-dashboard'
import IconListCheck from '~icons/tabler/list-check'
import IconMessages from '~icons/tabler/messages'
import IconMusic from '~icons/tabler/music'
import IconPhoto from '~icons/tabler/photo'
import IconRoute from '~icons/tabler/route'
import IconTicket from '~icons/tabler/ticket'
import IconUsers from '~icons/tabler/users'

export const NAV_ICONS: Record<string, unknown> = {
  activity: IconActivity,
  'alert-triangle': IconAlertTriangle,
  book: IconBook,
  'chart-line': IconChartLine,
  'clipboard-list': IconClipboardList,
  dice: IconDice,
  flag: IconFlag,
  gavel: IconGavel,
  headphones: IconHeadphones,
  history: IconHistory,
  inbox: IconInbox,
  key: IconKey,
  'layout-dashboard': IconLayoutDashboard,
  'list-check': IconListCheck,
  messages: IconMessages,
  music: IconMusic,
  photo: IconPhoto,
  route: IconRoute,
  ticket: IconTicket,
  users: IconUsers,
}

/** 已登记图标名清单（回归测试消费：导航项 icon 必须在此集合内） */
export const NAV_ICON_NAMES: readonly string[] = Object.keys(NAV_ICONS)
