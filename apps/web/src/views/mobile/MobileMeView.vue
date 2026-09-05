<script setup lang="ts">
/**
 * 移动端 · 我的（学习档案 + 设置）——ui-concept-design skill 重制版
 * 功能点：学习档案（docs/02-功能规划 ①：注册/登录/学习档案+目标标签）、
 *        可视化报表入口、设置与退出登录。
 * 数据：真实账户（auth.me）；统计/目标为【占位·M3】演示帧（M3 埋点聚合后替换）。
 * 视觉：档案卡（四角星线稿锚点）+ 目标 chips + Stat 32px 统计行 + 设置列表卡 + 危险操作（白底红字）。
 */
import { computed } from 'vue'

import { shareDemoLink } from '@/composables/share'
import { useAuthStore } from '@/stores/auth'
import { useUiStore } from '@/stores/ui'

import MobileArt from '@/components/mobile/MobileArt.vue'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTabBar from '@/components/mobile/MobileTabBar.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import '@/styles/mobile-uic.css'

const auth = useAuthStore()
const ui = useUiStore()

const displayName = computed(() => auth.me?.nickname ?? auth.me?.username ?? '同学')
const avatarLetter = computed(() => displayName.value.slice(0, 1).toUpperCase())
const level = computed(() => auth.me?.level ?? 'L1')

/* ---------- 学习目标（【占位·M3】目标标签用于个性化推荐，P1） ---------- */
const goals = ['日常交流', '职场英语', '面试表达'] as const

function comingSoon(feature: string) {
  ui.showToast(`「${feature}」M3 上线后开放`)
}

/** 顶栏 · 分享学习档案（演示：系统面板 / 复制链接） */
async function shareProfile() {
  const result = await shareDemoLink({
    title: 'VocalVerse 学习档案',
    text: `${displayName.value} · 累计练习 38 轮 · 平均分 86.4`,
    url: 'https://vocalverse.demo/profile/demoadult',
  })
  if (result === 'shared') ui.showToast('已分享')
  else if (result === 'copied') ui.showToast('档案链接已复制（演示链接）')
  else if (result === 'failed') ui.showToast('复制失败，请手动复制')
}

/** 顶栏 · 齿轮：滚到设置区（页面内已有设置列表） */
function scrollToSettings() {
  document.querySelector('.u-settings')?.scrollIntoView({ behavior: 'smooth' })
}

function logout() {
  if (!window.confirm('确定退出登录吗？')) return
  auth.clear()
  window.location.href = '/login'
}
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="我的">
      <template #actions>
        <button class="u-topbar__act" type="button" title="分享档案（演示）" aria-label="分享档案" @click="shareProfile">
          <MobileIcon name="share" :size="18" />
        </button>
        <button class="u-topbar__act" type="button" title="设置" aria-label="设置" @click="scrollToSettings">
          <MobileIcon name="settings" :size="18" />
        </button>
      </template>
    </MobileTopBar>

    <div class="u-content">
      <!-- 档案卡（四角星线稿锚点） -->
      <section class="u-profile">
        <div class="u-profile__art" aria-hidden="true">
          <MobileArt name="sparkle" :size="76" />
        </div>
        <div class="u-avatar u-avatar--lg">{{ avatarLetter }}</div>
        <div style="flex: 1; min-width: 0">
          <div class="u-profile__name">
            {{ displayName }}
            <span class="u-chip u-chip--ink">水平 {{ level }}</span>
          </div>
          <div class="u-profile__sub">加入 128 天 · 累计练习 38 轮</div>
        </div>
      </section>

      <!-- 学习目标（个性化推荐依据 · P1） -->
      <div style="margin-bottom: 20px">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px">
          <div class="u-section-title" style="margin: 0">学习目标</div>
          <button class="u-btn u-btn--secondary" type="button" style="height: 36px; padding: 0 16px; font-size: 13px" @click="comingSoon('目标设置')">
            编辑
          </button>
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 8px">
          <span v-for="g in goals" :key="g" class="u-chip u-chip--accent">
            <MobileIcon name="check" :size="14" />{{ g }}
          </span>
        </div>
        <p class="u-note" style="margin-top: 8px">目标标签用于个性化内容推荐与学习计划（M3）。</p>
      </div>

      <!-- 统计行（Stat 32px） -->
      <section class="u-stats">
        <div>
          <div class="u-stat-label">累计轮数</div>
          <div class="u-stat-value">38</div>
        </div>
        <div>
          <div class="u-stat-label">平均分</div>
          <div class="u-stat-value u-stat-value--accent">86.4</div>
        </div>
        <div>
          <div class="u-stat-label">连续天数</div>
          <div class="u-stat-value u-stat-value--star">
            <MobileIcon name="star" :size="22" />12
          </div>
        </div>
      </section>

      <!-- 设置列表 -->
      <div class="u-settings">
        <RouterLink to="/m/report" class="u-setting">
          <span class="u-icon-block u-icon-block--sm" style="background: #232044">
            <MobileIcon name="chart" :size="18" />
          </span>
          <span class="u-setting__label">我的评分报告</span>
          <MobileIcon name="chevron" :size="18" class="chev" />
        </RouterLink>
        <button class="u-setting" type="button" @click="comingSoon('帮助与反馈')">
          <span class="u-icon-block u-icon-block--sm" style="background: #3a2440">
            <MobileIcon name="info" :size="18" />
          </span>
          <span class="u-setting__label">帮助与反馈</span>
          <MobileIcon name="chevron" :size="18" class="chev" />
        </button>
        <button class="u-setting" type="button" @click="comingSoon('数据与隐私')">
          <span class="u-icon-block u-icon-block--sm" style="background: #1e2b26">
            <MobileIcon name="heart" :size="18" />
          </span>
          <span class="u-setting__label">数据与隐私</span>
          <MobileIcon name="chevron" :size="18" class="chev" />
        </button>
        <button class="u-setting" type="button" @click="comingSoon('关于声语界')">
          <span class="u-icon-block u-icon-block--sm" style="background: #16303a">
            <MobileIcon name="wave" :size="18" />
          </span>
          <span class="u-setting__label">关于声语界</span>
          <span class="u-setting__hint">v1.0 · Demo</span>
          <MobileIcon name="chevron" :size="18" class="chev" />
        </button>
      </div>

      <!-- 退出登录（危险操作：白底红字胶囊） -->
      <button class="u-btn u-btn--danger u-btn--block" type="button" @click="logout">
        <MobileIcon name="logout" :size="18" />
        退出登录
      </button>

      <p class="u-note" style="margin-top: 24px; text-align: center">
        统计与目标为演示帧数据，M3 接入真实学习档案后自动替换。
      </p>
    </div>

    <MobileTabBar />
  </div>
</template>
