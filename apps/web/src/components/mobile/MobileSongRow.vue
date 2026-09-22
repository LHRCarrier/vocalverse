<script setup lang="ts">
/**
 * 唱吧歌单行（MobileSingView 专用 · 2026-09-10；2026-09-22 歌单排版优化（含第三轮 QQ 音乐式改版））。
 *
 * - 两颗独立 button（原来的整行 button 无法内嵌按钮——嵌套 button 是无效 HTML，
 *   且触摸端无法区分「点行去跟唱」与「点收藏」）；
 * - 收藏态/就绪状态由父组件透传（`song.favorited` 来自服务端），点击经 emit 回父级，
 *   本组件不持状态（单一数据源在 useSingPlay.songs）。
 *
 * 2026-09-22 第三轮（用户截图：状态徽标叠了两遍 + 排版空、信息量低）：
 * 1. **就绪态不再占位**：`ready` 是曲库的默认态，每行都挂一颗「可跟唱」纯属噪音；
 *    徽标只在**异常态**（提取中 / 提取失败 / 暂不可唱）出现，且带 `title`+`aria-label`
 *    讲清「为什么不能唱」。异常态是少数派，徽标进副文行、`flex:none`，不挤文本。
 * 2. **QQ 音乐式信息密度**：封面 48 → **56px**（几何在本页作用域内定义，不再从
 *    `.u-icon-block` 借 48）；副文行 = 左「歌手 · 专辑」+ 右**时长**
 *    （`duration_s` → `mm:ss`，tabular-nums）。
 * 3. **行高 80 → 72px**（上下内边距 16 → 8）：列表更紧凑，同样一屏能多露一行。
 *
 * 2026-09-22 第五轮（用户口径「暂不可唱必须去掉，因为我们上架歌曲必须是可唱的，这是逻辑问题」）：
 * **状态徽标整体下架**（ready / 提取中 / 提取失败 / 暂不可唱 都不再上卡片）——曲库只上架
 * 可唱的曲子（导入即生成歌词时间轴 + 参考旋律，见 `local/_make_songs_singable.py`），
 * 卡片只讲歌曲信息；服务端 40905 门禁仍在（异常态点击会 toast，不在卡片上展示）。
 *
 * 2026-09-22 第四轮（用户口径「把这个 L2 L3 这类删掉，还有『几句』这种，
 * 卡片上应该是歌曲信息」）：副文只留**歌曲信息**——歌手 · 专辑（`songs.album`，可空，
 * 缺省时整段不出现）+ 时长；难度 Lx 与句数属练习元数据，不再上卡片（数据仍在详情/管理端）。
 * 署名只取 `artist` 里 `·` 前第一段（`Traditional · 合成旋律（公有领域童谣）` → `Traditional`；
 * 后半段是制作说明，完整值仍在歌曲详情与管理端）。
 *
 * 封面（2026-09-22 首轮）：`songs.cover_url` 有值就渲染封面图，无封面或图裂
 * （资产缺失/离线）退回音符图标——不给用户留破图占位。封面路径必须是**站点相对路径**
 * （如 `/api/v1/songs/covers/twinkle.svg`，后端公开路由服务），故一律过 `mediaUrl()`
 * 拼 `PYTHON_BASE`——打包壳里页面源是 `https://localhost`，相对路径会打到壳自身
 * 资源服务器（404，docs/48 B5）。
 */
import { computed, ref } from 'vue'

import { mediaUrl } from '@/api/media'
import { formatClock } from '@/lib/sing-lyrics'
import MobileIcon from './MobileIcon.vue'
import type { SongSummary } from '@/api/sing'

const props = defineProps<{ song: SongSummary }>()
const emit = defineEmits<{ open: [number]; favorite: [SongSummary] }>()

/** 专辑封面地址（`cover_url` → 绝对/代理地址；空值返回 ''） */
const coverSrc = computed(() => mediaUrl(props.song.cover_url))
/** 图裂标志（同一行的 song 由 `:key=id` 固定，无需在切换歌时复位） */
const coverFailed = ref(false)

/** 署名：只取 `·` 前第一段（`Traditional · 合成旋律（公有领域童谣）` → `Traditional`） */
const artistShort = computed(() => (props.song.artist ?? '').split('·')[0].trim() || '歌单')
/** 专辑（可空）：缺失时整段不出现，不留空分隔符 */
const albumText = computed(() => (props.song.album ?? '').trim())
/** 副文：**歌曲信息**「歌手 · 专辑」（难度 Lx / 句数属练习元数据，不再上卡片） */
const metaText = computed(() =>
  [artistShort.value, albumText.value].filter(Boolean).join(' · '),
)
/** 时长（`duration_s` 秒 → `mm:ss`；缺失时不渲染这一格，不留 `--:--` 占位） */
const durationText = computed(() =>
  props.song.duration_s ? formatClock(props.song.duration_s * 1000) : '',
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
        >
        <MobileIcon v-else :name="song.level <= 2 ? 'headphone' : 'note'" :size="22" />
      </span>
      <span class="u-item__main">
        <span class="u-item__title">{{ song.title }}</span>
        <span class="u-item__sub m-sing-row__sub">
          <span class="m-sing-row__meta">{{ metaText }}</span>
          <span v-if="durationText" class="m-sing-row__dur">{{ durationText }}</span>
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
