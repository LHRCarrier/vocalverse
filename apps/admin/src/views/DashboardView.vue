<script setup lang="ts">
/**
 * 工作台（docs/50 §11.3「工作台按角色分流」）。
 *
 * 不分流成一个所有人都看的空壳仪表盘——那种页面所有角色都觉得没用。
 * 这里按**权限**（不是按角色名）决定渲染哪些面板：权限模型是可自定义的，
 * 而"哪个角色有哪些权限"是运营期的数据；用权限判断才不会在有人
 * 自建了一个角色之后出现"工作台空白"。
 */
import { computed } from 'vue'

import PageHeader from '@/components/common/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'

import ContentPanel from './dashboard/ContentPanel.vue'
import ModerationPanel from './dashboard/ModerationPanel.vue'
import OpsPanel from './dashboard/OpsPanel.vue'

const auth = useAuthStore()

const showOps = computed(() => auth.hasPermission('ops:overview:read'))
const showModeration = computed(() => auth.hasPermission('moderation:queue:read'))
const showContent = computed(() =>
  auth.hasAny(['content:song:read', 'content:listening:read', 'content:book:read', 'content:scenario:read']),
)

/** 一个面板都没有（例如只授了 console:admin:read 的账号）时给明确指引，不留白屏 */
const hasAnyPanel = computed(() => showOps.value || showModeration.value || showContent.value)
</script>

<template>
  <div class="c-page">
    <PageHeader
      title="工作台"
      :desc="`${auth.profile?.displayName ?? ''} · ${auth.profile?.roleName ?? ''} · 已授予 ${auth.permissions.length} 个权限码`"
    />

    <div class="db-stack">
      <OpsPanel v-if="showOps" />
      <ModerationPanel v-if="showModeration" />
      <ContentPanel v-if="showContent" />

      <section v-if="!hasAnyPanel" class="c-card">
        <h2 class="c-card-title">这台账号只有系统管理权限</h2>
        <p class="c-card-sub" style="margin-bottom: 10px">
          工作台按权限渲染面板；当前账号没有运维 / 运营 / 审核任一域的读权限，因此这里没有内容可显示。
        </p>
        <RouterLink to="/system/roles" class="c-page-desc">前往「系统 · 角色权限」查看权限码分配</RouterLink>
      </section>
    </div>
  </div>
</template>

<style scoped>
.db-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
</style>
