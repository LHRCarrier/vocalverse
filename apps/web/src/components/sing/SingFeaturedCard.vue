<script setup lang="ts">
/**
 * 唱吧「本周精选」卡（2026-09-22 从 `MobileSingView.vue` 抽出；同日多轮视觉重置）。
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
 *
 * **2026-09-22 第六轮（用户口径「卡片太丑；去掉『一次最多 3 分钟』；把歌曲封面放上去；
 * 做成专辑卡带那种转动的效果」）**：
 * - 删掉说明段（`m-feat__desc` 整体移除）——「一次最多 3 分钟，逐句评分。」不再上卡；
 * - 新增**磁带卡带**视觉（`m-feat__tape`）：封面贴纸（`cover_url`）+ 双卷轴**持续转动**
 *   （`@keyframes m-feat-spin`，4.5s/圈，linear infinite）；带窗口、走带、螺丝细节；
 * - 版式改**左右两栏**：左列 = chip / 标题（2 行截断）/ 歌曲信息，右列 = 卡带（`flex:none`，
 *   104×70，垂直居中）。**不做绝对定位**——避免重蹈「插画压字」覆辙（本文件既有护栏用例继续守）；
 * - 动效分级：`html[data-motion='off']` → 停转；`low` → 放缓到 9s（docs/31 §2 规则 4）。
 * - 封面走 `mediaUrl()`（打包壳相对路径会 404，docs/48 B5），图裂/缺失退回音符图标。
 */
import { computed, ref } from 'vue'

import { mediaUrl } from '@/api/media'
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
/** 封面（卡带贴纸）：`cover_url` → 代理地址；空值/图裂退回音符图标 */
const coverSrc = computed(() => mediaUrl(props.song.cover_url))
const coverFailed = ref(false)
</script>

<template>
  <section class="u-dark-card m-feat">
    <div class="m-feat__body">
      <div class="m-feat__info">
        <span class="u-chip m-feat__chip">{{ ready ? '本周精选' : '参考旋律提取中' }}</span>
        <h2 class="u-dark-card__title m-feat__title">{{ song.title }}</h2>
        <p class="u-dark-card__meta m-feat__meta">
          <span class="m-feat__artist">{{ metaText }}</span>
          <span v-if="durationText" class="m-feat__facts">{{ durationText }}</span>
        </p>
      </div>

      <!-- 卡带（装饰视觉：封面贴纸 + 双卷轴转动；读屏只播报标题，故整体 aria-hidden） -->
      <div class="m-feat__tape" aria-hidden="true">
        <span class="m-feat__tape-label">
          <img
            v-if="coverSrc && !coverFailed"
            :src="coverSrc"
            alt=""
            loading="lazy"
            decoding="async"
            @error="coverFailed = true"
          >
          <MobileIcon v-else name="note" :size="14" />
        </span>
        <span class="m-feat__tape-window">
          <span class="m-feat__reel m-feat__reel--l" />
          <span class="m-feat__reel m-feat__reel--r" />
        </span>
      </div>
    </div>

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
 *   文字四档：标题 #fff / 属性 white .78 / 署名 white .55（对比度依次 ≈18 / 11 / 6.1）
 * CTA：白底实心 + 深墨字（卡片里唯一的彩色/高对比元素 = 唯一强调动作）
 *
 * 第六轮新增：右列卡带（贴纸 = 封面；双卷轴 4.5s/圈 持续转动）+ 说明段下架。
 * ============================================================ */
.m-feat {
  padding: 18px 20px 18px 24px; /* 右内边距 24 → 20：给卡带多留 4px，左/上下沿用上一轮口径 */
  margin-bottom: 20px;
  background: #15181c; /* 覆盖 `.u-dark-card` 的浅色底与原来 `--teal` 的径向渐变 */
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 10px 30px rgba(16, 20, 24, 0.18);
}
/* 左右两栏：左 = 信息（可伸缩），右 = 卡带（固定宽，垂直居中）。刻意不用绝对定位——防插画压字回归 */
.m-feat__body {
  display: flex;
  align-items: center;
  gap: 14px;
}
.m-feat__info {
  flex: 1;
  min-width: 0;
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
/* 标题：现代标题字重 600（原 700）+ 微负字距；仍是卡片里最大一档；最多两行（窄列下防卡片过高） */
.m-feat__title {
  margin: 10px 0 6px;
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
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

/* ---------- 卡带（第六轮）---------- */
.m-feat__tape {
  position: relative;
  flex: none;
  width: 112px;
  height: 76px;
  border-radius: 8px;
  /* 深色塑料壳：顶亮底暗的窄渐变 + 发丝边 + 内阴影（立体感） */
  background: linear-gradient(168deg, #3a4048 0%, #262b31 58%, #1e2227 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.08),
    0 4px 12px rgba(0, 0, 0, 0.35);
}
/* 贴纸 = 封面（宽条裁切）；无封面/图裂 → 音符图标 */
.m-feat__tape-label {
  position: absolute;
  top: 7px;
  left: 8px;
  right: 8px;
  height: 32px;
  border-radius: 3px;
  overflow: hidden;
  background: #0d1117;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.45);
}
.m-feat__tape-label img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
/* 走带窗口：两个卷轴 + 中间的磁带（伪元素画带，卷轴转、带不动） */
.m-feat__tape-window {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 6px;
  height: 30px;
  border-radius: 4px;
  background: rgba(0, 0, 0, 0.42);
  border: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 11px;
}
.m-feat__tape-window::before {
  content: '';
  position: absolute;
  left: 26px;
  right: 26px;
  top: 50%;
  height: 3px;
  transform: translateY(-50%);
  border-radius: 2px;
  background: #4a5058;
}
/* 卷轴：辐条用重复锥形渐变画（转动可见），中心轴孔用 ::after */
.m-feat__reel {
  position: relative;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: repeating-conic-gradient(#d7dde3 0deg 20deg, #8b949e 20deg 60deg);
  box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.35);
  animation: m-feat-spin 4.5s linear infinite;
}
.m-feat__reel::after {
  content: '';
  position: absolute;
  inset: 6.5px;
  border-radius: 50%;
  background: #1e2227;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
}
@keyframes m-feat-spin {
  to {
    transform: rotate(360deg);
  }
}
/* 动效分级（docs/31 §2 规则 4）：low = 放缓，off = 停转（系统「减少动效」/省电档） */
html[data-motion='low'] .m-feat__reel {
  animation-duration: 9s;
}
html[data-motion='off'] .m-feat__reel {
  animation: none;
}

/* 唯一强调动作：白底实心（取代原来的白描边 ghost —— 描边在深灰面上偏弱，撑不起主操作） */
.m-feat__cta {
  margin-top: 14px;
  width: 100%;
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
