<script setup lang="ts">
/**
 * 唱吧歌单行（MobileSingView 专用 · 2026-09-10；2026-09-23 QQ 音乐式改版）。
 *
 * - 行内三颗独立 button（原整行 button 无法内嵌按钮——嵌套 button 是无效 HTML，
 *   触摸端也无法区分「点行」与「点收藏」）：**行点击 = 试听参考旋律**（2026-09-23 用户原型口径，
 *   与悬浮播放条联动）、**「去跟唱」= 打开跟唱面板**、**心形 = 收藏**；
 * - 收藏态/在播态由父组件透传（`song.favorited` 来自服务端、`active` 来自播放条），
 *   本组件不持状态（单一数据源在 useSingPlay.songs / 页面预览播放）。
 *
 * 2026-09-23 第六轮（用户提供 QQ 音乐式原型，视觉照搬、内容接真）：
 * 1. 封面 56 → **52px**（原型口径），**在播行**叠加绿色音波（`m-sing-row__wave`，三根跳动条）；
 * 2. 右侧新增**「去跟唱」药丸键**（浅绿底 + 深绿字，原型同款语义：行=试听、药丸=进录音）；
 * 3. 不再上任何状态/元数据徽标（就绪/难度/句数此前已下架；原型里的 SQ无损/伴奏修音是假标签，不搬）。
 *
 * 2026-09-22 第四轮（用户口径「卡片上应该是歌曲信息」）：副文只留**歌曲信息**——歌手 · 专辑
 * （`songs.album`，可空，缺省时整段不出现）+ 时长；署名只取 `artist` 里 `·` 前第一段。
 * 封面：`songs.cover_url` 有值就渲染，无封面或图裂退回音符图标——不留破图。
 * 封面路径必须是**站点相对路径**（`/api/v1/songs/covers/*`），一律过 `mediaUrl()` 拼 `PYTHON_BASE`
 * （打包壳里页面源是 `https://localhost`，相对路径会打到壳自身资源服务器，docs/48 B5）。
 */
import { computed, ref } from 'vue'

import { mediaUrl } from '@/api/media'
import { formatClock } from '@/lib/sing-lyrics'
import MobileIcon from './MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

const props = withDefaults(
  defineProps<{
    song: SongSummary
    /** 在播（悬浮播放条当前曲目）→ 封面叠加音波、标题高亮 */
    active?: boolean
  }>(),
  { active: false },
)
const emit = defineEmits<{
  /** 试听参考旋律（行点击；页面侧驱动悬浮播放条） */
  preview: [song: SongSummary]
  /** 去跟唱（打开跟唱面板） */
  open: [id: number]
  favorite: [song: SongSummary]
}>()

/** 专辑封面地址（`cover_url` → 绝对/代理地址；空值返回 ''） */
const coverSrc = computed(() => mediaUrl(props.song.cover_url))
/** 图裂标志（同一行的 song 由 `:key=id` 固定，无需在切换歌时复位） */
const coverFailed = ref(false)

/** 署名：只取 `·` 前第一段（`Traditional · 合成旋律（公有领域童谣）` → `Traditional`） */
const artistShort = computed(() => (props.song.artist ?? '').split('·')[0].trim() || '歌单')
/** 专辑（可空）：缺失时整段不出现，不留空分隔符 */
const albumText = computed(() => (props.song.album ?? '').trim())
/** 副文：**歌曲信息**「歌手 · 专辑」 */
const metaText = computed(() =>
  [artistShort.value, albumText.value].filter(Boolean).join(' · '),
)
/** 时长（`duration_s` 秒 → `mm:ss`；缺失时不渲染这一格，不留 `--:--` 占位） */
const durationText = computed(() =>
  props.song.duration_s ? formatClock(props.song.duration_s * 1000) : '',
)
</script>

<template>
  <div class="u-item m-sing-row" :class="{ 'is-active': active }">
    <button class="m-sing-row__hit" type="button" @click="emit('preview', song)">
      <span class="m-sing-row__cover">
        <!-- 封面为装饰图（歌名就在右侧），alt 留空避免读屏重复播报 -->
        <img
          v-if="coverSrc && !coverFailed"
          :src="coverSrc"
          alt=""
          loading="lazy"
          decoding="async"
          @error="coverFailed = true"
        >
        <MobileIcon v-else :name="song.level <= 2 ? 'headphone' : 'note'" :size="20" />
        <!-- 在播音波（原型同款：三根跳动条；动效分级 off 档只留静态竖条） -->
        <span v-if="active" class="m-sing-row__wave" aria-hidden="true">
          <i /><i /><i />
        </span>
      </span>
      <span class="u-item__main">
        <span class="u-item__title m-sing-row__name">{{ song.title }}</span>
        <span class="u-item__sub m-sing-row__sub">
          <span class="m-sing-row__meta">{{ metaText }}</span>
          <span v-if="durationText" class="m-sing-row__dur">{{ durationText }}</span>
        </span>
      </span>
    </button>
    <button
      class="m-sing-row__sing"
      type="button"
      :aria-label="`去跟唱 ${song.title}`"
      @click="emit('open', song.id)"
    >
      <MobileIcon name="mic" :size="13" /><span class="m-sing-row__sing-text">去跟唱</span>
    </button>
    <button
      class="m-sing-fav"
      :class="{ 'is-on': song.favorited }"
      type="button"
      :aria-pressed="song.favorited"
      :aria-label="song.favorited ? `取消收藏 ${song.title}` : `收藏 ${song.title}`"
      :title="song.favorited ? '取消收藏' : '收藏'"
      @click="emit('favorite', song)"
    >
      <MobileIcon name="heart" :size="20" />
    </button>
  </div>
</template>
