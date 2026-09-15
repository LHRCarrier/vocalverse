<script setup lang="ts">
/**
 * 导航图标（编译期内联）。
 *
 * ⚠️ 为什么用显式映射而不是 `<component :is="'~icons/tabler/' + name" />`：
 * `unplugin-icons` 是**编译期**虚拟模块，只有字面量 `import IconX from '~icons/tabler/x'`
 * 才会被解析；运行时拼字符串拿不到组件，会渲染成空标签（静默失效）。
 * 显式映射还顺带带来 Tree-shaking：用不到的图标不进产物。
 *
 * 图标源：Tabler 单一功能图标源（docs/32 选型 + docs/35 硬规则）。
 */
import IconActivity from '~icons/tabler/activity'
import IconAlertTriangle from '~icons/tabler/alert-triangle'
import IconBook from '~icons/tabler/book'
import IconChartLine from '~icons/tabler/chart-line'
import IconClipboardList from '~icons/tabler/clipboard-list'
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

defineProps<{ name: string; size?: number }>()

const ICONS: Record<string, unknown> = {
  activity: IconActivity,
  'alert-triangle': IconAlertTriangle,
  book: IconBook,
  'chart-line': IconChartLine,
  'clipboard-list': IconClipboardList,
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
</script>

<template>
  <!-- 未知图标名渲染空位而非报错：新增菜单项忘记登记图标时不该白屏 -->
  <component :is="ICONS[name]" v-if="ICONS[name]" :width="size ?? 18" :height="size ?? 18" aria-hidden="true" />
</template>
