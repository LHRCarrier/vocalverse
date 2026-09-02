<script setup lang="ts">
/**
 * Lieflat 表盘预览（docs/13 §8 预览工作流）。
 *
 * 两份单文件 HTML 由 lieflat-charts 技能（SKILL.md 选型规则）生成：
 * - 管理端评价看板：图表模式 · Glance 系 × PORCELAIN（KPI + G8/G3/G4/G13/G14）
 * - 用户端学习报表：报告模式 · R09 数据故事仪表盘骨架（雷达 + F2/F4/L15 + KPI 栏）
 * 演示数据口径 docs/06 §9.1；资产来源与选型审计见 src/assets/lieflat/README.md。
 */
import { computed, ref } from 'vue'
import { NAlert, NTag } from 'naive-ui'

import LieflatChart from '@/components/LieflatChart.vue'
import adminDashboardHtml from '@/assets/lieflat/vv-admin-dashboard.html?raw'
import learningReportHtml from '@/assets/lieflat/vv-learning-report.html?raw'

const tabs = [
  { key: 'admin', label: '管理端评价看板' },
  { key: 'report', label: '用户端学习报表' },
] as const

const active = ref<(typeof tabs)[number]['key']>('admin')

const currentHtml = computed(() =>
  active.value === 'admin' ? adminDashboardHtml : learningReportHtml,
)
</script>

<template>
  <div class="mx-auto max-w-[1280px]">
    <header class="mb-4">
      <h1 class="text-xl font-bold">Lieflat 表盘 · 高保真预览</h1>
      <p class="mt-1 text-sm text-[#667085]">
        按 lieflat-charts 技能选型规则为 VocalVerse 表盘数据的演示版本（口径 docs/06 §9.1）
      </p>
    </header>

    <NAlert class="mb-4" type="info" :show-icon="false">
      <div class="space-y-1 text-xs leading-relaxed">
        <div>
          <NTag class="mr-2" size="small" type="warning" :bordered="false">许可</NTag>
          上游为 <b>PolyForm Noncommercial License 1.0.0（仅限非商业用途）</b>；
          本仓库作为实训项目使用，商用前须向作者申请授权。
        </div>
        <div>
          <NTag class="mr-2" size="small" :bordered="false">依赖</NTag>
          在线字体（Google Fonts）+ ECharts/Chart.js CDN，离线打开时图表降级。
        </div>
        <div>
          <NTag class="mr-2" size="small" :bordered="false">落地</NTag>
          预览（静态高保真）→ 视觉验收 → 集成真实 view（替换演示数据）；选型审计记录见
          <code class="rounded bg-[#F0EFEB] px-1">src/assets/lieflat/README.md</code>。
        </div>
      </div>
    </NAlert>

    <div class="mb-3 flex items-center gap-2">
      <button
        v-for="t in tabs"
        :key="t.key"
        class="rounded-full px-4 py-1.5 text-sm font-semibold transition"
        :class="active === t.key ? 'bg-[#081F5C] text-[#F7F2EB]' : 'bg-[#F0EFEB] text-[#667085]'"
        type="button"
        @click="active = t.key"
      >
        {{ t.label }}
      </button>
    </div>

    <!-- 版心 1080px：窄容器横向滚动，不压缩重排（页面自带 fit-width 缩放） -->
    <div class="overflow-x-auto rounded-[24px] border border-[#E5E7EB] bg-white p-4">
      <div class="min-w-[1080px]">
        <LieflatChart :html="currentHtml" :fallback-height="active === 'admin' ? 1400 : 1800" />
      </div>
    </div>
  </div>
</template>
