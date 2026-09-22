<script setup lang="ts">
/**
 * 唱吧「本周精选」卡（2026-09-22 从 `MobileSingView.vue` 抽出；同日二次视觉重置）。
 *
 * 视觉重置（2026-09-22 用户要求「从幼稚风改到现代化」）：
 * - **表面**：青绿径向渐变 + 音符线稿插画 → **中性深灰平面**（`#15181c`）+ 发丝边框 + 适度投影。
 *   删掉的两层径向辉光与插画都属于「装饰性元素」，也是历史「插画压字」一类 bug 的根源
 *   （插画没了，压字不可能再发生；原护栏用例改为断言「不再有装饰插画」）。
 * - **强调**：原「青色实心 chip + 琥珀色描边按钮」= 两个彩色元素抢注意力 → 收敛为
 *   **单一强调动作**（白底实心 CTA）；chip 降级为发丝描边标签（无色块），色彩噪音归零。
 * - **层次**：靠字重/字号/色阶说话（20/600 标题 → 12/600 .78 属性 → 13/400 .62 说明 → 12/400 .55 署名），
 *   全部落在同一中性底上，对比度自检 ≥5.5:1（见安卓日志）。
 * - 版式（meta 排标题之后、署名可省略、「时长」永不省略、padding 18/24）沿用上一轮口径。
 * - **2026-09-22 第四轮（用户口径「卡片上应该是歌曲信息」）**：meta 改「歌手 · 专辑」
 *   （`songs.album`，可空）+ 右端**时长**；原来的「N 句 · 可跟唱」属练习元数据/默认态噪音，
 *   整体下架（就绪与否仍由 chip 与说明行表达）。
 */
import { computed } from 'vue'

import { formatClock } from '@/lib/sing-lyrics'
import MobileIcon from '@/components/mobile/MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

const props = defineProps<{ song: SongSummary }>()
const emit = defineEmits<{ (e: 'open', id: number): void }>()

/** 参考旋律就绪 = 可跟唱（与歌单行、跟唱面板同一口径） */
const ready = computed(() => props.song.pitch_ref_status === 'ready')
/** 署名：只取 `·` 前第一段（`Traditional · 合成旋律（公有领域童谣）` → `Traditional`） */
const artistShort = computed(() => (props.song.artist ?? '').split('·')[0].trim() || '歌单')
/** 专辑（可空）：缺失时整段不出现，不留空分隔符 */
const albumText = computed(() => (props.song.album ?? '').trim())
/** meta：歌曲信息「歌手 · 专辑」 */
const metaText = computed(() =>
  [artistShort.value, albumText.value].filter(Boolean).join(' · '),
)
/** 时长（`duration_s` 秒 → `mm:ss`；缺失时不渲染，不留 `--:--`） */
const durationText = computed(() =>
  props.song.duration_s ? formatClock(props.song.duration_s * 1000) : '',
)
</script>

<template>
  <section class="u-dark-card m-feat">
    <span class="u-chip m-feat__chip">{{ ready ? '本周精选' : '参考旋律提取中' }}</span>
    <h2 class="u-dark-card__title m-feat__title">{{ song.title }}</h2>
    <p class="u-dark-card__meta m-feat__meta">
      <span class="m-feat__artist">{{ metaText }}</span>
      <span v-if="durationText" class="m-feat__facts">{{ durationText }}</span>
    </p>
    <p class="u-dark-card__desc m-feat__desc">
      {{
        ready
          ? '一次最多 3 分钟，逐句评分。'
          : '参考旋律生成中，完成后即可跟唱。'
      }}
    </p>
    <button class="u-btn m-feat__cta" type="button" @click="emit('open', song.id)">
      <MobileIcon name="mic" :size="16" /> 去跟唱
    </button>
  </section>
</template>

<style scoped>
/* ============================================================
 * 现代化重置（2026-09-22）——低饱和中性面 + 单一强调动作 + 发丝分隔 + 适度投影
 *
 * 色板（全部实心，无渐变/无装饰）：
 *   面 #15181c ｜ 描边 white .08 ｜ 投影 rgba(16,20,24,.18)
 *   文字四档：标题 #fff / 属性 white .78 / 说明 white .62 / 署名 white .55（对比度依次 ≈18 / 11 / 7.5 / 6.1）
 * CTA：白底实心 + 深墨字（卡片里唯一的彩色/高对比元素 = 唯一强调动作）
 * ============================================================ */
.m-feat {
  padding: 18px 24px; /* 沿用上一轮收紧值（28 → 18/24，卡片高度实测 206px） */
  margin-bottom: 20px;
  background: #15181c; /* 覆盖 `.u-dark-card` 的浅色底与原来 `--teal` 的径向渐变 */
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 10px 30px rgba(16, 20, 24, 0.18);
}
/* 标签：发丝描边 + 字距（原为实心青底胶囊 —— 与 CTA 抢注意力，现降级为无声标签） */
.m-feat .u-chip {
  height: 24px;
  padding: 0 10px;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: rgba(255, 255, 255, 0.62);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
}
/* 标题：现代标题字重 600（原 700）+ 微负字距；仍是卡片里最大一档 */
.m-feat__title {
  margin: 10px 0 6px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
/* 元信息一行两段：歌曲信息（歌手 · 专辑，最弱）在前、时长（次强）在后 */
.m-feat__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}
.m-feat__artist {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: rgba(255, 255, 255, 0.55);
}
.m-feat__facts {
  flex: none;
  white-space: nowrap;
  color: rgba(255, 255, 255, 0.78);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
/* 说明：卡片内最弱的一档正文 */
.m-feat__desc {
  margin: 8px 0 0;
  font-size: 13px;
  line-height: 1.5;
  color: rgba(255, 255, 255, 0.62);
}
/* 唯一强调动作：白底实心（取代原来的白描边 ghost —— 描边在深灰面上偏弱，撑不起主操作） */
.m-feat__cta {
  margin-top: 14px;
  background: #fff;
  border: none;
  color: #0d1117;
  font-size: 14px;
  font-weight: 600;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.28);
}
.m-feat__cta:hover {
  background: #f2f3f5;
}
.m-feat__cta:active {
  transform: scale(0.98);
}
</style>
