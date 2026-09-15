<script setup lang="ts">
/**
 * UIC 概念原型 ② 口语陪练（v2 · 对照参考帧返工）
 * 参考帧：ref-segmented-pill（高 56px 分段控件）+ ref-card-light-timeline（实色图标块场景卡）
 *        + ref-dark-colored-cards（深藏青推荐卡：光晕 + chip badge + 插画母题）
 * v2 改动：分段控件 56px / 图标块实色深底 / 深色卡加光晕与 chip / 场景卡内边距 32。
 * 本页为 dev-only 概念验证，生产构建整枝剔除；删除清单见文件尾注释。
 */
import { computed, ref } from 'vue'

import './uic.css'
import UicArt from './UicArt.vue'
import UicIcon from './UicIcon.vue'

type Scope = 'daily' | 'work' | 'study'

const scope = ref<Scope>('daily')

const scopes: { key: Scope; label: string; icon: string }[] = [
  { key: 'daily', label: '生活', icon: 'coffee' },
  { key: 'work', label: '工作', icon: 'briefcase' },
  { key: 'study', label: '学习', icon: 'book' },
]

interface Scene {
  id: number
  scope: Scope
  icon: string
  iconBg: string
  title: string
  sub: string
  level: string
  minutes: string
  rounds: string
  badge?: { text: string; variant: 'new' | 'success' | 'star' | 'error' | 'neutral' }
}

const scenes: Scene[] = [
  {
    id: 1,
    scope: 'daily',
    icon: 'coffee',
    iconBg: '#3A2440',
    title: '咖啡馆点单',
    sub: '点一杯拿铁，和小哥聊天气',
    level: 'L3',
    minutes: '3 分钟',
    rounds: '8 轮',
    badge: { text: '热门', variant: 'new' },
  },
  {
    id: 2,
    scope: 'daily',
    icon: 'plane',
    iconBg: '#16303A',
    title: '机场值机',
    sub: '行李托运、登机口变更应对',
    level: 'L4',
    minutes: '4 分钟',
    rounds: '10 轮',
    badge: { text: '新', variant: 'star' },
  },
  {
    id: 3,
    scope: 'work',
    icon: 'briefcase',
    iconBg: '#232044',
    title: '面试自我介绍',
    sub: '1 分钟从「我是谁」讲到「我能做什么」',
    level: 'L4',
    minutes: '4 分钟',
    rounds: '10 轮',
    badge: { text: '推荐', variant: 'success' },
  },
  {
    id: 4,
    scope: 'work',
    icon: 'chat',
    iconBg: '#1E2B26',
    title: '周会汇报',
    sub: '进度、风险、下一步——三步讲清楚',
    level: 'L3',
    minutes: '3 分钟',
    rounds: '8 轮',
  },
  {
    id: 5,
    scope: 'study',
    icon: 'book',
    iconBg: '#3A2440',
    title: '课堂提问',
    sub: '举手发言不再紧张，先想后说',
    level: 'L2',
    minutes: '2 分钟',
    rounds: '6 轮',
  },
  {
    id: 6,
    scope: 'study',
    icon: 'headphone',
    iconBg: '#16303A',
    title: '听力复述',
    sub: '听懂 80% 后用自己的话讲出来',
    level: 'L3',
    minutes: '3 分钟',
    rounds: '8 轮',
  },
]

const visibleScenes = computed(() => scenes.filter((s) => s.scope === scope.value))
</script>

<template>
  <div class="uic-scope">
    <div class="uic-page">
      <div class="wrap">
        <!-- 页头：Display + 主操作 -->
        <header class="page-head">
          <div>
            <h1 class="uic-display page-head__title">口语陪练</h1>
            <p class="uic-body page-head__sub">挑一个场景，和 AI 教练开口说。</p>
          </div>
          <button class="uic-btn uic-btn--primary" type="button">
            <UicIcon name="mic" /> 开始对话
          </button>
        </header>

        <!-- 分段控件（高 56px） -->
        <div class="uic-segment" role="tablist">
          <button
            v-for="s in scopes"
            :key="s.key"
            class="uic-segment__item"
            :class="{ 'uic-segment__item--active': scope === s.key }"
            type="button"
            role="tab"
            :aria-selected="scope === s.key"
            @click="scope = s.key"
          >
            <UicIcon :name="s.icon" /> {{ s.label }}
          </button>
        </div>

        <!-- 深色展示卡（每屏 1 张）：深藏青 + 光晕 + 同色系 chip + 幽灵按钮 + 插画母题 -->
        <article class="uic-dark-card feature">
          <div class="feature__body">
            <span class="uic-badge uic-badge--chip feature__badge">今日推荐</span>
            <h2 class="feature__title">数字人陪练 · 本周主题</h2>
            <p class="feature__sub">
              「旅行英语」系列：值机、点餐、问路三连练，<br>
              学完就能用。
            </p>
            <button class="uic-btn uic-btn--ghost feature__cta" type="button">
              立即体验 <UicIcon name="arrow" />
            </button>
          </div>
          <div class="feature__art" aria-hidden="true">
            <UicArt name="note-big" />
          </div>
        </article>

        <!-- 场景网格：白卡 r-24 内边距 32，实色图标块 -->
        <section class="scene-grid">
          <article
            v-for="s in visibleScenes"
            :key="s.id"
            class="uic-card scene-card"
            tabindex="0"
          >
            <div class="scene-card__head">
              <span class="uic-icon-block scene-card__icon" :style="{ backgroundColor: s.iconBg }">
                <UicIcon :name="s.icon" />
              </span>
              <span v-if="s.badge" class="uic-badge" :class="`uic-badge--${s.badge.variant}`">
                {{ s.badge.text }}
              </span>
            </div>
            <h3 class="scene-card__title">{{ s.title }}</h3>
            <p class="scene-card__sub">{{ s.sub }}</p>
            <div class="scene-card__meta">
              <span class="uic-caption">{{ s.level }} · {{ s.minutes }} · {{ s.rounds }}</span>
            </div>
            <button class="uic-btn uic-btn--secondary scene-card__btn" type="button">
              开始练习
            </button>
          </article>
        </section>

        <footer class="page-footer">
          <span class="uic-caption">
            UI Concept Design 概念原型 ② · 口语陪练 v2 —— 依据 .trae/skills/ui-concept-design 参考帧制作
          </span>
        </footer>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  max-width: 1080px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  margin-bottom: 40px;
}

.page-head__title {
  margin: 0;
}

.page-head__sub {
  margin: 12px 0 0;
}

/* 深色卡：深藏青 + 左上光晕 + chip badge（同色系提亮） */
.feature {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  margin: 40px 0;
  padding: 48px 56px;
  overflow: hidden;
  background:
    radial-gradient(90% 140% at 12% 0%, rgba(185, 168, 255, 0.22) 0%, transparent 55%),
    radial-gradient(120% 160% at 85% 20%, #2f2b5e 0%, transparent 55%),
    var(--uic-dark-navy);
}

.feature__badge {
  background: var(--uic-dark-badge-bg);
  color: var(--uic-dark-badge-text);
}

.feature__title {
  margin: 20px 0 10px;
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}

.feature__sub {
  margin: 0 0 28px;
  font-size: 16px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.72);
}

.feature__cta {
  height: 44px;
  padding: 0 24px;
}

.feature__art {
  width: 240px;
  flex: none;
  opacity: 0.9;
}

.feature__art :deep(svg) {
  stroke: rgba(255, 255, 255, 0.85);
}

.feature__art :deep(.uic-art__fill) {
  filter: none;
}

/* 场景网格 */
.scene-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.scene-card {
  display: flex;
  flex-direction: column;
  padding: 32px;
  transition:
    box-shadow 150ms ease-out,
    transform 150ms ease-out;
}

.scene-card:hover {
  box-shadow: 0 10px 28px rgba(28, 28, 26, 0.1);
  transform: translateY(-1px);
}

.scene-card:focus-visible {
  outline: 2px solid var(--uic-accent);
  outline-offset: 2px;
}

.scene-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.scene-card__title {
  margin: 0 0 6px;
  font-size: 18px;
  font-weight: 700;
  color: var(--uic-ink);
}

.scene-card__sub {
  margin: 0;
  font-size: 14px;
  color: var(--uic-sub);
  flex: 1;
}

.scene-card__meta {
  margin: 20px 0;
}

.scene-card__btn {
  height: 44px;
  padding: 0 24px;
  align-self: flex-start;
}

.page-footer {
  margin-top: 56px;
  text-align: center;
}

@media (max-width: 860px) {
  .scene-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .feature__art {
    display: none;
  }
}
</style>

<!--
  删除清单（可删无影响，dev-only 概念原型）：
  1. 删除 apps/web/src/views/preview/uic/ 整目录（UicHome.vue / UicSpeaking.vue / UicSinging.vue /
     uic.css / UicIcon.vue / UicArt.vue）
  2. 删除 registry.ts 中「UIC 概念」3 行登记
  3. 删除 router/preview.ts 中 3 条路由
  删除后：pnpm lint && pnpm typecheck && pnpm build 全绿；生产构建不含任何残留。
-->
