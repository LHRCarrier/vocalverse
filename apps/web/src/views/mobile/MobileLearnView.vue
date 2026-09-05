<script setup lang="ts">
/**
 * 移动端 · 学习（2026-09-05 组长拍板：参考 Duolingo——等级制度 + 经验条为画像主要焦点）
 * 画像主卡 = LV 徽章 + 等级名 + XP 经验条 + 连续天数/本周时长；
 * 速览卡 = 薄弱音素 / 高频错误词（演示帧，讯飞词级数据 M3 替换）；
 * 趋势卡 = 流利度周趋势迷你柱（演示帧）。
 * 联动：完成练习 +XP（progress store）→ 全 app 展示同一份 LV（我的/抽屉/社区帖子/私信）。
 */
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { useProgressStore } from '@/stores/progress'
import '@/styles/mobile-uic.css'

const progress = useProgressStore()

/* ---------- 画像速览（演示帧 · M3 讯飞/评分数据替换） ---------- */
const weakPhonemes = ['/θ/', '/ð/', '/r/']
const weakWords = ['interesting', 'comfortable', 'world']
/** 流利度周趋势（演示：最近 5 次对话平均分） */
const weekTrend = [72, 75, 80, 82, 86]

const streak = 12 // 连续天数（演示；M3 打卡聚合）
const weekMinutes = 86 // 本周时长（演示）
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="学习" />

    <div class="u-learn">
      <!-- 画像主卡：LV 徽章 + 等级名 + 经验条 + 双数字（扫一眼 = 等级 & 进度 & 坚持） -->
      <section class="u-learn-hero">
        <div class="u-learn-hero__badge">
          <span class="u-learn-hero__lv">{{ progress.lvLabel }}</span>
          <span class="u-learn-hero__rank">{{ progress.info.title }}</span>
        </div>
        <div class="u-learn-hero__body">
          <div class="u-learn-hero__bar" role="progressbar" :aria-valuenow="progress.progressPct" aria-valuemin="0" aria-valuemax="100">
            <span class="u-learn-hero__fill" :style="{ width: `${progress.progressPct}%` }" />
          </div>
          <div class="u-learn-hero__xp">
            {{ progress.xpInLevel }} / {{ progress.nextXp ?? '—' }} XP
          </div>
          <div class="u-learn-hero__stats">
            <span class="u-learn-hero__stat">
              <MobileIcon name="flame" :size="16" />{{ streak }} 天
            </span>
            <span class="u-learn-hero__stat">
              <MobileIcon name="clock" :size="16" />本周 {{ weekMinutes }} 分钟
            </span>
          </div>
        </div>
      </section>

      <!-- 画像速览：薄弱音素 / 高频错误词（演示帧） -->
      <section class="u-learn-card">
        <div class="u-section-title" style="margin-bottom: 10px">画像速览</div>
        <div class="u-learn-card__row">
          <span class="u-learn-card__label">薄弱音素</span>
          <span v-for="p in weakPhonemes" :key="p" class="u-chip u-chip--warm">{{ p }}</span>
        </div>
        <div class="u-learn-card__row">
          <span class="u-learn-card__label">高频错误词</span>
          <span v-for="w in weakWords" :key="w" class="u-chip u-chip--ink">{{ w }}</span>
        </div>
      </section>

      <!-- 流利度趋势（演示 · 最近 5 次对话平均分） -->
      <section class="u-learn-card">
        <div class="u-section-title" style="margin-bottom: 12px">流利度趋势</div>
        <div class="u-learn-trend" aria-label="最近 5 次对话平均分趋势">
          <div
            v-for="(v, i) in weekTrend"
            :key="i"
            class="u-learn-trend__bar"
            :style="{ height: `${v}%` }"
            :title="`第 ${i + 1} 次 · ${v} 分`"
          />
        </div>
        <div class="u-learn-trend__scale">72 · 75 · 80 · 82 · 86</div>
      </section>

      <p class="u-note" style="text-align: center; margin-top: 20px">
        等级经验真实结算（练习加权规则）与画像数据 M3 接入。
      </p>
    </div>
  </div>
</template>
