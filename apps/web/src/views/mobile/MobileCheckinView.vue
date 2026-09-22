<script setup lang="ts">
/**
 * 移动端 · 打卡页（2026-09-21 组长反馈：打卡改手动、要有入口）
 *
 * - 状态真源 = 我的打卡卡（stores/checkin）：今日是否已打卡 + 连续天数；
 * - 「打卡」= 调 Python `POST /api/v1/checkin` 聚合当日练习并物化当日卡（同一天幂等）；
 * - 规则文案把机制说清楚：练习不自动打卡，打卡卡会带上当日练习分。
 */
import { computed, onMounted } from 'vue'

import MobileIcon from '@/components/mobile/MobileIcon.vue'
import MobileTopBar from '@/components/mobile/MobileTopBar.vue'
import { timeAgo } from '@/api/community'
import { useMobileBack } from '@/composables/useMobileBack'
import { useCheckinStore } from '@/stores/checkin'
import '@/styles/mobile-uic.css'

const checkin = useCheckinStore()
const goBack = useMobileBack('/m/learn')

const dateLabel = computed(() => {
  const d = new Date(`${checkin.today}T00:00:00`)
  const week = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()]
  return `${d.getFullYear()} 年 ${d.getMonth() + 1} 月 ${d.getDate()} 日 · 星期${week}`
})

const recent = computed(() => checkin.cards.slice(0, 7))

function scoreText(overall: number | null): string {
  return overall == null ? '—' : overall.toFixed(0)
}

onMounted(() => {
  void checkin.refresh()
})
</script>

<template>
  <div class="u-phone">
    <MobileTopBar title="打卡" back @back="goBack" />

    <main class="u-checkin">
      <section class="u-checkin-hero" aria-label="今日打卡">
        <p class="u-checkin-hero__date">{{ dateLabel }}</p>
        <p class="u-checkin-hero__status">
          {{ checkin.checkedIn ? '今日已打卡' : '今天还没打卡' }}
        </p>
        <p class="u-checkin-hero__streak">
          <MobileIcon name="flame" :size="18" />
          连续 <strong>{{ checkin.streak }}</strong> 天
        </p>

        <button
          class="u-checkin-hero__btn"
          type="button"
          :disabled="checkin.checkedIn || checkin.submitting || checkin.loading"
          @click="checkin.checkIn()"
        >
          {{ checkin.checkedIn ? '今日已打卡' : checkin.submitting ? '打卡中…' : '打卡' }}
        </button>

        <p class="u-checkin-hero__rule">
          练习不会自动打卡：完成口语练习后再点「打卡」，打卡卡会带上当日综合分；每天一次。
        </p>
      </section>

      <section class="u-checkin-list" aria-label="最近打卡">
        <h2 class="u-checkin-list__title">最近打卡</h2>
        <p v-if="checkin.loading && !checkin.cards.length" class="u-note">打卡记录加载中…</p>
        <p v-else-if="!recent.length" class="u-note">还没有打卡记录，点上面的「打卡」开始吧。</p>
        <template v-else>
          <RouterLink
            v-for="c in recent"
            :key="c.id"
            :to="`/m/post/${c.id}`"
            class="u-checkin-row"
          >
            <span class="u-checkin-row__date">{{ c.checkinDate }}</span>
            <span class="u-checkin-row__meta">
              <template v-if="(c.checkinPracticeCount ?? 0) > 0">
                {{ c.checkinPracticeCount }} 次练习 · 综合分 {{ scoreText(c.checkinOverall) }}
              </template>
              <template v-else>已打卡</template>
            </span>
            <time class="u-checkin-row__time">{{ timeAgo(c.createdAt) }}</time>
            <MobileIcon name="chevron" :size="15" class="u-checkin-row__go" />
          </RouterLink>
        </template>
      </section>
    </main>
  </div>
</template>
