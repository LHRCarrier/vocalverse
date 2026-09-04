<script setup lang="ts">
/**
 * UIC 概念原型 ③ 唱歌评分报告（v2 · 对照参考帧返工）
 * 参考帧：ref-dark-colored-cards（深紫卡 + 光晕 + chip + 插画母题 + 幽灵按钮）
 *        + ref-profile-card-stats（统计行 32px+）+ ref-card-light-timeline（逐句点线时间轴）
 * v2 改动：深紫卡加光晕与大幅音符插画 / 总分 64px / 统计 32px / 逐句卡实色图标块 + 点线。
 * 本页为 dev-only 概念验证，生产构建整枝剔除；删除清单见文件尾注释。
 */
import './uic.css'
import UicArt from './UicArt.vue'
import UicIcon from './UicIcon.vue'

interface LineScore {
  id: number
  lyric: string
  pitch: number
  rhythm: number
  status: 'excellent' | 'good' | 'review'
  comment: string
  iconBg: string
}

const lines: LineScore[] = [
  {
    id: 1,
    lyric: "You know I'm just a girl, a small town girl ...",
    pitch: 95,
    rhythm: 92,
    status: 'excellent',
    comment: '音准极佳，连读处理得很自然',
    iconBg: '#1E2B26',
  },
  {
    id: 2,
    lyric: 'And I will always love you, oh ...',
    pitch: 88,
    rhythm: 90,
    status: 'good',
    comment: '副歌换气点提前了一点点，注意 catch breath',
    iconBg: '#232044',
  },
  {
    id: 3,
    lyric: "I'm yours, I'm yours, I'm yours ...",
    pitch: 81,
    rhythm: 84,
    status: 'review',
    comment: '重复段节拍略有抢拍，建议跟踩点练习 2 遍',
    iconBg: '#16303A',
  },
]

const statusMap = {
  excellent: { text: '优秀', variant: 'success' },
  good: { text: '良好', variant: 'new' },
  review: { text: '再练', variant: 'neutral' },
} as const
</script>

<template>
  <div class="uic-scope">
    <div class="uic-page">
      <div class="wrap">
        <!-- 页头：返回（图标-only 带 Tooltip）+ Display -->
        <header class="page-head">
          <button class="icon-btn" type="button" title="返回唱歌页">
            <UicIcon name="back" />
          </button>
          <div>
            <h1 class="uic-display page-head__title">唱歌评分报告</h1>
            <p class="uic-body page-head__sub">Perfect Night · LE SSERAFIM · 2024-12-16 20:15</p>
          </div>
        </header>

        <!-- 深色展示卡（每屏 1 张）：深紫 #3A2440 + 光晕 + chip + 大幅音符插画 + 幽灵按钮 -->
        <article class="uic-dark-card score-hero">
          <div class="score-hero__art" aria-hidden="true">
            <UicArt name="note-big" />
          </div>
          <div class="score-hero__body">
            <div class="score-hero__top">
              <span class="uic-badge uic-badge--chip score-hero__badge">新纪录</span>
              <span class="score-hero__text">107 秒 · 整曲跟唱</span>
            </div>
            <h2 class="score-hero__title">Perfect Night</h2>
            <p class="score-hero__sub">打败了 82% 的学习者，继续保持。</p>
            <div class="score-hero__actions">
              <button class="uic-btn uic-btn--ghost" type="button">
                <UicIcon name="headphone" /> 再唱一遍
              </button>
              <button class="uic-btn uic-btn--ghost" type="button">查看逐句</button>
            </div>
          </div>
          <div class="score-hero__score">
            <span class="score-hero__score-label">总分</span>
            <span class="score-hero__score-value">92.4</span>
          </div>
        </article>

        <!-- 统计行：32px 大数字 -->
        <section class="metrics uic-card">
          <div class="uic-stat">
            <span class="uic-stat__label">音准</span>
            <span class="uic-stat__value uic-stat__value--accent">93</span>
          </div>
          <div class="uic-stat">
            <span class="uic-stat__label">节奏</span>
            <span class="uic-stat__value">91</span>
          </div>
          <div class="uic-stat">
            <span class="uic-stat__label">发音</span>
            <span class="uic-stat__value">88</span>
          </div>
          <div class="uic-stat">
            <span class="uic-stat__label">完整度</span>
            <span class="uic-stat__value">100%</span>
          </div>
        </section>

        <!-- 逐句评分：实色图标块 + 点线时间轴 -->
        <section class="line-section">
          <h2 class="line-section__title">逐句评分</h2>
          <div class="timeline">
            <template v-for="(line, i) in lines" :key="line.id">
              <article class="uic-card line-card" tabindex="0">
                <span
                  class="uic-icon-block line-card__icon"
                  :class="`line-card__icon--${line.status}`"
                  :style="{ backgroundColor: line.iconBg }"
                >
                  <UicIcon name="note" />
                </span>
                <div class="line-card__main">
                  <p class="line-card__lyric">{{ line.lyric }}</p>
                  <p class="line-card__comment">{{ line.comment }}</p>
                </div>
                <div class="line-card__right">
                  <span class="line-card__score">{{ line.pitch }}</span>
                  <span
                    class="uic-badge"
                    :class="`uic-badge--${statusMap[line.status].variant}`"
                  >
                    {{ statusMap[line.status].text }}
                  </span>
                </div>
              </article>
              <div v-if="i < lines.length - 1" class="uic-dotline" aria-hidden="true">
                <span class="uic-dotline__dot" />
                <span class="uic-dotline__line" />
              </div>
            </template>
          </div>
        </section>

        <footer class="page-footer">
          <span class="uic-caption">
            UI Concept Design 概念原型 ③ · 唱歌评分报告 v2 —— 依据 .trae/skills/ui-concept-design 参考帧制作
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
  gap: 24px;
  margin-bottom: 40px;
}

.page-head__title {
  margin: 0;
}

.page-head__sub {
  margin: 12px 0 0;
}

/* 图标-only 按钮：pill + track 底，hover 变色（带 title Tooltip） */
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border: none;
  border-radius: var(--uic-r-pill);
  background: var(--uic-track);
  color: var(--uic-ink);
  cursor: pointer;
  transition: background-color 150ms ease-out;
  margin-bottom: 10px;
}

.icon-btn:hover {
  background: var(--uic-track-hover);
}

/* 深色卡：深紫 + 光晕 + chip + 大幅插画 + 总分 64px */
.score-hero {
  display: flex;
  align-items: center;
  gap: 48px;
  padding: 48px 56px;
  overflow: hidden;
  background:
    radial-gradient(90% 140% at 10% 8%, rgba(185, 168, 255, 0.25) 0%, transparent 55%),
    radial-gradient(130% 170% at 85% 10%, #4c3060 0%, transparent 60%),
    var(--uic-dark-purple);
}

.score-hero__art {
  width: 220px;
  flex: none;
  opacity: 0.9;
}

.score-hero__art :deep(svg) {
  stroke: rgba(255, 255, 255, 0.85);
}

.score-hero__body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.score-hero__top {
  display: flex;
  align-items: center;
  gap: 14px;
}

.score-hero__badge {
  background: var(--uic-dark-badge-bg);
  color: var(--uic-dark-badge-text);
}

.score-hero__text {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
}

.score-hero__title {
  margin: 20px 0 10px;
  font-size: 24px;
  font-weight: 700;
  color: #fff;
}

.score-hero__sub {
  margin: 0 0 28px;
  font-size: 16px;
  color: rgba(255, 255, 255, 0.72);
}

.score-hero__actions {
  margin-top: auto;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.score-hero__score {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.score-hero__score-label {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
}

.score-hero__score-value {
  font-size: 64px;
  font-weight: 700;
  line-height: 1;
  color: #fff;
  letter-spacing: -2px;
  font-variant-numeric: tabular-nums;
}

/* 统计行 */
.metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 24px;
  padding: 32px 40px;
  margin-top: 24px;
}

/* 逐句 · 点线时间轴 */
.line-section {
  margin-top: 48px;
}

.line-section__title {
  font-size: 18px;
  font-weight: 700;
  color: var(--uic-ink);
  margin: 0 0 20px;
}

.line-card {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 24px 32px;
  transition:
    box-shadow 150ms ease-out,
    transform 150ms ease-out;
}

.line-card:hover {
  box-shadow: 0 10px 28px rgba(28, 28, 26, 0.1);
  transform: translateY(-1px);
}

.line-card:focus-visible {
  outline: 2px solid var(--uic-accent);
  outline-offset: 2px;
}

.line-card__main {
  flex: 1;
  min-width: 0;
}

.line-card__lyric {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
  color: var(--uic-ink);
}

.line-card__comment {
  margin: 0;
  font-size: 13px;
  color: var(--uic-weak);
}

.line-card__right {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: none;
}

.line-card__score {
  font-size: 24px;
  font-weight: 700;
  color: var(--uic-ink);
  font-variant-numeric: tabular-nums;
}

.uic-dotline {
  margin: 8px 0 8px 95px;
}

.page-footer {
  margin-top: 56px;
  text-align: center;
}

@media (max-width: 720px) {
  .score-hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .score-hero__art {
    display: none;
  }

  .score-hero__score {
    align-items: flex-start;
  }

  .metrics {
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
