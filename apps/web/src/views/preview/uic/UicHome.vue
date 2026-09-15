<script setup lang="ts">
/**
 * UIC 概念原型 ① 学习主页（v2 · 对照参考帧返工）
 * 参考帧：ref-landing-hero-light（双侧线稿插画 hero + 信任条 + 纸面描边次级按钮）
 *        + ref-profile-card-stats（统计行 32px+）+ ref-segmented-pill（高 56px）
 *        + ref-card-light-timeline（实色图标块 + 点线时间轴）
 * v2 改动：插画锚点（气球/日历/星星）/ Display 56px / 统计 32px / 分段 56px /
 *         图标块实色深底白图标 / 点线时间轴 / 纸面次级按钮改白底描边。
 * 本页为 dev-only 概念验证，生产构建整枝剔除；删除清单见文件尾注释。
 */
import { computed, ref } from 'vue'

import './uic.css'
import UicArt from './UicArt.vue'
import UicIcon from './UicIcon.vue'

type Tab = 'all' | 'speaking' | 'singing'

const tab = ref<Tab>('all')

const tabs: { key: Tab; label: string; icon: string }[] = [
  { key: 'all', label: '全部', icon: 'chart' },
  { key: 'speaking', label: '口语', icon: 'mic' },
  { key: 'singing', label: '唱歌', icon: 'note' },
]

interface Session {
  id: number
  kind: 'speaking' | 'singing'
  icon: string
  iconBg: string
  title: string
  sub: string
  value: string
  valueAccent?: boolean
  badge?: { text: string; variant: 'new' | 'success' | 'star' | 'error' | 'neutral' }
}

const sessions: Session[] = [
  {
    id: 1,
    kind: 'speaking',
    icon: 'coffee',
    iconBg: '#3A2440',
    title: '场景对话 · 咖啡馆点单',
    sub: '今天 9:30 · 8 轮 · 用时 3 分 12 秒',
    value: '86.4',
    valueAccent: true,
    badge: { text: '完成', variant: 'success' },
  },
  {
    id: 2,
    kind: 'singing',
    icon: 'note',
    iconBg: '#232044',
    title: '英文歌 · Perfect Night',
    sub: '昨天 20:15 · 跟唱 2 遍 · 音准 88',
    value: '88.1',
    valueAccent: true,
    badge: { text: '新纪录', variant: 'star' },
  },
  {
    id: 3,
    kind: 'speaking',
    icon: 'briefcase',
    iconBg: '#16303A',
    title: '场景对话 · 面试自我介绍',
    sub: '9 月 12 日 · 6 轮 · 中级难度',
    value: '79.8',
    badge: { text: '待提升', variant: 'neutral' },
  },
  {
    id: 4,
    kind: 'singing',
    icon: 'headphone',
    iconBg: '#1E2B26',
    title: '英文歌 · Yesterday Once More',
    sub: '9 月 10 日 · 跟唱 1 遍 · 节奏 91',
    value: '91.5',
    valueAccent: true,
    badge: { text: '优秀', variant: 'success' },
  },
]

const visibleSessions = computed(() =>
  tab.value === 'all' ? sessions : sessions.filter((s) => s.kind === tab.value),
)

/* 信任条品牌字（弱化 60%，视觉压舱） */
const trust = ['DeepSeek', 'Whisper', '讯飞', 'edge-tts', 'PyTorch', 'PostgreSQL']
</script>

<template>
  <div class="uic-scope">
    <div class="uic-page">
      <div class="wrap">
        <!-- 顶栏：线性 logo + 文字链接 + 主操作 -->
        <header class="topbar">
          <div class="topbar__brand">
            <span class="brand-mark"><UicIcon name="wave" /></span>
            <span class="brand-name">声语界</span>
          </div>
          <nav class="topbar__nav">
            <a href="#">口语陪练</a>
            <a href="#">唱歌评分</a>
            <a href="#">学习报告</a>
          </nav>
          <div class="topbar__actions">
            <a class="topbar__login" href="#">登录</a>
            <button class="uic-btn uic-btn--primary topbar__cta" type="button">
              <UicIcon name="mic" /> 开始今日训练
            </button>
          </div>
        </header>

        <!-- Hero：双侧对称大幅线稿插画 = 视觉锚点；居中 Display 56px -->
        <section class="hero">
          <div class="hero__art hero__art--left">
            <UicArt name="balloon" />
          </div>
          <div class="hero__art hero__art--right">
            <UicArt name="calendar" />
          </div>

          <h1 class="uic-display hero__title">
            说得好，唱得准。<br>
            <span class="hero__title-soft">每天进步一点点。</span>
          </h1>
          <p class="uic-body hero__sub">
            AI 数字人陪你口语对练，英文歌逐句跟唱评分——<br>
            生活中的每一个场景，都是你的练习场。
          </p>
          <div class="hero__actions">
            <button class="uic-btn uic-btn--primary" type="button">
              <UicIcon name="mic" /> 开始口语训练
            </button>
            <button class="uic-btn uic-btn--outline" type="button">
              <UicIcon name="chart" /> 查看学习报告
            </button>
          </div>

          <!-- 信任条：灰色品牌字，弱化 60% -->
          <div class="hero__trust">
            <span class="uic-caption">已接入业界主流模型与语音引擎</span>
            <div class="hero__trust-row">
              <span v-for="b in trust" :key="b" class="hero__brand">{{ b }}</span>
            </div>
          </div>
        </section>

        <!-- 统计行：Caption weak 在上，Stat 32px 在下 -->
        <section class="stats uic-card">
          <div class="uic-stat">
            <span class="uic-stat__label">连续训练（天）</span>
            <span class="uic-stat__value"><UicIcon name="flame" class="stat-star" /> 12</span>
          </div>
          <div class="uic-stat">
            <span class="uic-stat__label">累计训练（轮）</span>
            <span class="uic-stat__value">38</span>
          </div>
          <div class="uic-stat">
            <span class="uic-stat__label">综合评分</span>
            <span class="uic-stat__value uic-stat__value--accent">86.4</span>
          </div>
          <div class="uic-stat">
            <span class="uic-stat__label">本周目标</span>
            <span class="uic-stat__value">5 / 7</span>
          </div>
        </section>

        <!-- 分段控件：高 56px，白胶囊浮起 -->
        <div class="toolbar">
          <div class="uic-segment" role="tablist">
            <button
              v-for="t in tabs"
              :key="t.key"
              class="uic-segment__item"
              :class="{ 'uic-segment__item--active': tab === t.key }"
              type="button"
              role="tab"
              :aria-selected="tab === t.key"
              @click="tab = t.key"
            >
              <UicIcon :name="t.icon" /> {{ t.label }}
            </button>
          </div>
          <span class="uic-caption">共 {{ visibleSessions.length }} 条记录 · 最近一次:3 分钟前</span>
        </div>

        <!-- 点线时间轴列表：图标块搁在点线上，实色深底 + 白图标 -->
        <section class="timeline">
          <template v-for="(s, i) in visibleSessions" :key="s.id">
            <article class="uic-card session-card" tabindex="0">
              <span class="uic-icon-block session-card__icon" :style="{ backgroundColor: s.iconBg }">
                <UicIcon :name="s.icon" />
              </span>
              <div class="session-card__main">
                <h3 class="session-card__title">{{ s.title }}</h3>
                <p class="session-card__sub">{{ s.sub }}</p>
              </div>
              <div class="session-card__right">
                <span
                  class="session-card__value"
                  :class="{ 'session-card__value--accent': s.valueAccent }"
                >
                  {{ s.value }}
                </span>
                <span v-if="s.badge" class="uic-badge" :class="`uic-badge--${s.badge.variant}`">
                  {{ s.badge.text }}
                </span>
              </div>
            </article>
            <!-- 点线：点=当前位置，线=轨迹（最后一条不收口） -->
            <div v-if="i < visibleSessions.length - 1" class="uic-dotline" aria-hidden="true">
              <span class="uic-dotline__dot" />
              <span class="uic-dotline__line" />
            </div>
          </template>
        </section>

        <footer class="page-footer">
          <span class="uic-caption">
            UI Concept Design 概念原型 ① · 学习主页 v2 —— 依据 .trae/skills/ui-concept-design 参考帧制作
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

/* ---- 顶栏 ---- */
.topbar {
  display: flex;
  align-items: center;
  gap: 24px;
}

.topbar__brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: var(--uic-ink);
  color: #fff;
}

.brand-name {
  font-size: 17px;
  font-weight: 700;
}

.topbar__nav {
  display: flex;
  gap: 24px;
  margin-left: 24px;
  flex: 1;
}

.topbar__nav a,
.topbar__login {
  color: var(--uic-sub);
  text-decoration: none;
  font-size: 15px;
  transition: color 150ms ease-out;
}

.topbar__nav a:hover,
.topbar__login:hover {
  color: var(--uic-ink);
}

.topbar__actions {
  display: flex;
  align-items: center;
  gap: 16px;
}

.topbar__cta {
  height: 44px;
  padding: 0 24px;
}

/* ---- Hero：双侧对称插画 ---- */
.hero {
  position: relative;
  text-align: center;
  padding: 128px 40px 96px;
}

.hero__art {
  position: absolute;
  top: 50%;
  width: 280px;
  transform: translateY(-52%);
  color: var(--uic-ink);
}

.hero__art--left {
  left: -40px;
  transform: translateY(-52%) rotate(-4deg);
}

.hero__art--right {
  right: -40px;
  transform: translateY(-52%) rotate(3deg);
}

.hero__title-soft {
  color: var(--uic-sub);
}

.hero__sub {
  margin-top: 24px;
}

.hero__actions {
  margin-top: 40px;
  display: flex;
  justify-content: center;
  gap: 16px;
}

/* 信任条 */
.hero__trust {
  margin-top: 64px;
}

.hero__trust-row {
  margin-top: 16px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 40px;
  flex-wrap: wrap;
}

.hero__brand {
  font-size: 16px;
  font-weight: 700;
  color: var(--uic-weak);
  opacity: 0.6; /* 弱化 60% */
  letter-spacing: 0.5px;
}

/* ---- 统计行 ---- */
.stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  padding: 32px 40px;
}

.stat-star {
  width: 26px;
  height: 26px;
  vertical-align: -3px;
  color: var(--uic-star);
}

/* ---- 工具栏 ---- */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 48px 0 24px;
}

/* ---- 点线时间轴 ---- */
.timeline {
  display: flex;
  flex-direction: column;
}

.session-card {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 24px 32px;
  cursor: pointer;
  transition:
    box-shadow 150ms ease-out,
    transform 150ms ease-out;
}

.session-card:hover {
  box-shadow: 0 10px 28px rgba(28, 28, 26, 0.1);
  transform: translateY(-1px);
}

.session-card:focus-visible {
  outline: 2px solid var(--uic-accent);
  outline-offset: 2px;
}

.session-card__main {
  flex: 1;
  min-width: 0;
}

.session-card__title {
  margin: 0 0 4px;
  font-size: 17px;
  font-weight: 700;
  color: var(--uic-ink);
}

.session-card__sub {
  margin: 0;
  font-size: 13px;
  color: var(--uic-weak);
}

.session-card__right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: none;
}

.session-card__value {
  font-size: 24px;
  font-weight: 700;
  color: var(--uic-ink);
  font-variant-numeric: tabular-nums;
}

.session-card__value--accent {
  color: var(--uic-accent);
}

/* 点线行：左缩进对齐图标块中心 */
.uic-dotline {
  margin: 8px 0 8px 95px; /* 56/2 图标 + 24 卡内边距 + 8 对齐 */
}

.page-footer {
  margin-top: 56px;
  text-align: center;
}

@media (max-width: 960px) {
  .hero__art {
    display: none;
  }

  .topbar__nav,
  .topbar__login {
    display: none;
  }

  .stats {
    grid-template-columns: repeat(2, 1fr);
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
