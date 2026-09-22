<script setup lang="ts">
/**
 * 唱吧歌单行（MobileSingView 专用 · 2026-09-10；2026-09-22 歌单排版优化）。
 *
 * - 两颗独立 button（原来的整行 button 无法内嵌按钮——嵌套 button 是无效 HTML，
 *   且触摸端无法区分「点行去跟唱」与「点收藏」）；
 * - 收藏态/就绪状态由父组件透传（`song.favorited` 来自服务端），点击经 emit 回父级，
 *   本组件不持状态（单一数据源在 useSingPlay.songs）。
 *
 * 排版优化（2026-09-22 真机截图）：
 * 1. **状态只写一遍**：原来「可跟唱」(20px 蓝) 与「就绪」(11px 徽标) 同源于 `pitch_ref_status`，
 *    两段竖排吃掉 ~60px 横向空间 → 文本列只剩 ~128px，副文被截成「Traditional · 合成旋律（公…」。
 *    现只保留一颗徽标，并改成**用户语言**四态（可跟唱 / 提取中 / 提取失败 / 暂不可唱）。
 * 2. **副文按用处重排**：`L{难度} · {句数} 句 · {署名}` —— 原来把最长的 artist 排在最前，
 *    用户真正要看的句数与难度永远在省略号后面。
 * 3. **署名只取第一段**：`artist` 形如「Traditional · 合成旋律（公有领域童谣）」（`data/seed/songs.json`），
 *    后半段是制作说明、不是署名；完整值仍在歌曲详情与管理端。
 * 4. 徽标放**副文行右端**（`flex: none`，不参与文本宽度分配）→ 长副文只省略中间，状态永远可见。
 *
 * 5. **左侧图标块 → 专辑封面**（2026-09-22 用户要求）：`songs.cover_url` 有值就渲染封面图，
 *    与图标块同为 48×48/圆角 14（`.m-sing-row__cover` 只加裁切，不改几何）。
 *    封面路径必须是**站点相对路径**（如 `/api/v1/songs/covers/twinkle.svg`，后端公开路由服务），
 *    故一律过 `mediaUrl()` 拼 `PYTHON_BASE`——打包壳里页面源是 `https://localhost`，
 *    相对路径会打到壳自身资源服务器（404，docs/48 B5）。
 *    **无封面或图裂（资产缺失/离线）退回原音符图标**：不给用户留破图占位，
 *    也让「还没配封面的歌」保持老观感（种子数据 10 首已全部配图）。
 */
import { computed, ref } from 'vue'

import { mediaUrl } from '@/api/media'
import MobileIcon from './MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

const props = defineProps<{ song: SongSummary }>()
const emit = defineEmits<{ open: [number]; favorite: [SongSummary] }>()

/** 专辑封面地址（`cover_url` → 绝对/代理地址；空值返回 ''） */
const coverSrc = computed(() => mediaUrl(props.song.cover_url))
/** 图裂标志（同一行的 song 由 `:key=id` 固定，无需在切换歌时复位） */
const coverFailed = ref(false)

/** 状态徽标（**唯一**状态源；文案是用户语言，不是内部字段名） */
const STATE: Record<string, { text: string; variant: 'success' | 'neutral' }> = {
  ready: { text: '可跟唱', variant: 'success' },
  building: { text: '提取中', variant: 'neutral' },
  invalid: { text: '提取失败', variant: 'neutral' },
}
const state = computed(
  () => STATE[props.song.pitch_ref_status] ?? { text: '暂不可唱', variant: 'neutral' as const },
)
/** 状态完整语义（徽标只有 3 个字；读屏与长按要能看懂「为什么不能唱」） */
const stateLabel = computed(() =>
  props.song.pitch_ref_status === 'ready'
    ? '参考旋律已就绪，可以跟唱'
    : `参考旋律${state.value.text}，暂时不能开始跟唱`,
)

/** 署名：只取 `·` 前第一段（`Traditional · 合成旋律（公有领域童谣）` → `Traditional`） */
const artistShort = computed(() => (props.song.artist ?? '').split('·')[0].trim() || '歌单')
/** 副文：难度与句数在前（选歌依据），署名在后 */
const metaText = computed(
  () => `L${props.song.level} · ${props.song.expected_lines} 句 · ${artistShort.value}`,
)
</script>

<template>
  <div class="u-item m-sing-row">
    <button class="m-sing-row__hit" type="button" @click="emit('open', song.id)">
      <span class="u-icon-block m-sing-row__cover" :style="{ background: song.level <= 2 ? '#1E2B26' : '#16303A' }">
        <!-- 封面为装饰图（歌名就在右侧），alt 留空避免读屏重复播报 -->
        <img
          v-if="coverSrc && !coverFailed"
          :src="coverSrc"
          alt=""
          loading="lazy"
          decoding="async"
          @error="coverFailed = true"
        />
        <MobileIcon v-else :name="song.level <= 2 ? 'headphone' : 'note'" :size="22" />
      </span>
      <span class="u-item__main">
        <span class="u-item__title">{{ song.title }}</span>
        <span class="u-item__sub m-sing-row__sub">
          <span class="m-sing-row__meta">{{ metaText }}</span>
          <span
            class="u-badge m-sing-row__state"
            :class="`u-badge--${state.variant}`"
            :title="stateLabel"
            :aria-label="stateLabel"
          >{{ state.text }}</span>
        </span>
      </span>
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
