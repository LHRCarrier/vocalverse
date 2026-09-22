<script setup lang="ts">
/**
 * 酒馆 · 消息项（迁移自 ai4u MessageItem；2026-09-21 改造 · 2026-09-22 对设计稿完整参考）：
 * - 系统卡：open（开场重卡）、scene（过场细线）、dice（判定卡，成功绿/失败红）；
 * - **三种说话人三种呈现**（设计稿 dialog-stream）：
 *   ① DM 叙述 = 米白气泡（左，头像 = 设计稿 DM 头像）；
 *   ② 玩家 = 暗茶色气泡（右，头像 = 账号头像，无则设计稿 PC 头像占位）；
 *   ③ **NPC 台词 = 独立 whisper 卡**（虚线琥珀卡 + NPC 头像 + 名牌 + 斜体台词，**不塞进 DM 气泡**）；
 * - **引号整行**（「…」/“…”）按设计稿 dm-quote 样式高亮（整行才高亮，避免误伤行内引号）；
 * - 卡拉OK逐词高亮 + 长按操作菜单 + 译文（气泡脚注），均保持；
 * - 文本插值禁 v-html（docs/13 §5）。
 */
import { computed, ref } from 'vue'

import IconCrown from '~icons/tabler/crown'

import MobileAvatar from '@/components/mobile/MobileAvatar.vue'

import { TAVERN_ART, npcAvatar } from './art'
import { buildTrpgLines, groupTrpgParts, tokenizeTrpg } from './segments'
import TrpgEndingCard from './TrpgEndingCard.vue'

const props = withDefaults(
  defineProps<{
    role: 'user' | 'assistant'
    kind?: 'text' | 'system'
    content: string
    payload?: Record<string, unknown> | null
    /** 当前 AI 流式目标（尾部闪烁光标） */
    live?: boolean
    /** NPC 名单（实体表 kind=npc；决定「名字：」是否渲染成人名标签） */
    npcNames?: Set<string>
    avatarLetter?: string
    /** 玩家头像/昵称（账号；立绘抽屉与消息头像用） */
    avatarUrl?: string | null
    userName?: string
    /** 已标注（长按菜单切换；展示左侧标记） */
    marked?: boolean
    /** 该条为长按选中项（动作条打开期间高亮描边） */
    active?: boolean
    /** 译文状态（X 式「翻译」按钮）：null = 未翻译 */
    translation?: { status: 'loading' | 'done' | 'error'; text: string; showing: boolean } | null
    /** 朗读高亮（仅 role=assistant；未在播为 null） */
    highlight?: { offset: number | null; length: number | null; progress: number } | null
  }>(),
  {
    kind: 'text',
    payload: null,
    live: false,
    npcNames: () => new Set<string>(),
    avatarLetter: '我',
    avatarUrl: null,
    userName: '冒险者',
    marked: false,
    active: false,
    translation: null,
    highlight: null,
  },
)

const emit = defineEmits<{ actions: []; translate: []; standee: [role: 'user' | 'assistant'] }>()

const isSystem = computed(() => props.kind === 'system')
const sysType = computed(() => String(props.payload?.trpg_sys ?? ''))
const scenePayload = computed(() => props.payload ?? {})
/** DM 头像加载失败 → 回退 Tabler crown（离线/资源缺失时不出现破图） */
const dmAvatarFailed = ref(false)

const openTasks = computed<string[]>(() => {
  const raw = scenePayload.value.tasks
  return Array.isArray(raw) ? raw.map((x) => String(x)) : []
})
const diceLines = computed(() => String(scenePayload.value.text ?? '').split('\n').filter(Boolean))
const diceOutcome = computed<'success' | 'failure' | null>(() => {
  const text = String(scenePayload.value.text ?? '')
  if (text.includes('成功')) return 'success'
  if (text.includes('失败')) return 'failure'
  return null
})

/* ---------------- 长按 → 操作菜单 ---------------- */
const LONG_PRESS_MS = 420
/** 手指抖动阈值（px）：小位移不取消长按（此前任何 touchmove 都取消 → 手机上几乎按不出来） */
const MOVE_TOLERANCE = 14
const pressing = ref(false)
let pressTimer: ReturnType<typeof setTimeout> | null = null
let pressOrigin: { x: number; y: number } | null = null

function cancelPress() {
  if (pressTimer != null) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
  pressing.value = false
  pressOrigin = null
}

function startPress(event: TouchEvent) {
  if (isSystem.value) return
  cancelPress()
  const touch = event.touches?.[0]
  pressOrigin = touch ? { x: touch.clientX, y: touch.clientY } : null
  pressTimer = setTimeout(() => {
    pressTimer = null
    pressing.value = false
    pressOrigin = null
    navigator.vibrate?.(12) // 轻震反馈（不支持的设备静默）
    emit('actions')
  }, LONG_PRESS_MS)
  // 按压视觉反馈（180ms 后仍按住 → 轻微缩放，让用户知道长按被识别）
  setTimeout(() => {
    if (pressTimer != null) pressing.value = true
  }, 180)
}

function movePress(event: TouchEvent) {
  if (!pressOrigin) return
  const touch = event.touches?.[0]
  if (!touch) return
  const dx = Math.abs(touch.clientX - pressOrigin.x)
  const dy = Math.abs(touch.clientY - pressOrigin.y)
  if (dx > MOVE_TOLERANCE || dy > MOVE_TOLERANCE) cancelPress()
}

/* ---------------- 逐词高亮（卡拉OK）+ 行/说话块（纯函数见 segments.ts） ---------------- */
const tokens = computed(() => tokenizeTrpg(props.content))
const litThrough = computed(() => {
  const hl = props.highlight
  if (!hl || hl.offset == null) return -1
  // 已点亮到的字符：句内进度 → 该句字符区间 [offset, offset+len) 内（末字符封顶）
  const span = Math.max(hl.length ?? 1, 1)
  const activeChar = hl.offset + Math.min(span - 1, Math.floor(span * hl.progress))
  // 找到包含 activeChar 的 token（tokens 按 start 升序）
  let idx = -1
  for (let i = 0; i < tokens.value.length; i++) {
    if (tokens.value[i]!.start <= activeChar) idx = i
    else break
  }
  return idx
})

const lines = computed(() => buildTrpgLines(props.content, props.npcNames))
const parts = computed(() => groupTrpgParts(lines.value))

/** 最后一个旁白块的下标（脚注=译文/标注挂在它里面，对应设计稿 bubble-footer） */
const lastTextPart = computed(() => {
  for (let i = parts.value.length - 1; i >= 0; i--) if (!parts.value[i]!.npc) return i
  return -1
})
</script>

<template>
  <!-- 系统卡：开场 -->
  <section v-if="isSystem && sysType === 'open'" class="t-card t-card--open">
    <div class="t-card__kicker">冒险开始</div>
    <div class="t-card__title">{{ scenePayload.campaign_name ?? '无名剧本' }}</div>
    <div class="t-card__meta">
      <span v-if="scenePayload.scene">场景 · {{ scenePayload.scene }}</span>
      <span v-if="openTasks.length">任务 · {{ openTasks.join(' / ') }}</span>
    </div>
  </section>

  <!-- 系统卡：过场（细线） -->
  <div v-else-if="isSystem && sysType === 'scene'" class="t-scene-line">
    —— 场景 · {{ scenePayload.scene ?? '未知' }} ——
  </div>

  <!-- 系统卡：判定 -->
  <section
    v-else-if="isSystem && sysType === 'dice'"
    class="t-card t-card--dice"
    :class="diceOutcome === 'success' ? 'is-success' : diceOutcome === 'failure' ? 'is-fail' : ''"
  >
    <div class="t-card__dice-head">🎲 判定</div>
    <div v-for="(line, i) in diceLines" :key="i" class="t-card__dice-line">{{ line }}</div>
  </section>

  <!-- 系统卡：任务结算尾声（docs/56 §5：ending 额外落系统卡，刷新仍在） -->
  <TrpgEndingCard v-else-if="isSystem && sysType === 'ending'" :payload="scenePayload" />

  <!-- 未知系统卡：降级为文本（前向兼容） -->
  <div v-else-if="isSystem" class="t-scene-line">{{ content || `系统卡：${sysType}` }}</div>

  <!-- 气泡（长按 → 操作菜单；DM 支持卡拉OK高亮） -->
  <div
    v-else
    class="u-chat t-msg"
    :class="{
      'u-chat--user': role === 'user',
      'is-marked': marked,
      'is-active': active,
      'is-pressing': pressing,
    }"
    @touchstart.passive="startPress"
    @touchmove.passive="movePress"
    @touchend="cancelPress"
    @touchcancel="cancelPress"
    @contextmenu.prevent="isSystem || emit('actions')"
  >
    <!-- 头像框：点击打开角色立绘（设计稿 avatar-frame；DM = 设计稿头像，加载失败回退 Tabler） -->
    <button
      v-if="role === 'assistant'"
      class="t-ava-frame t-ava-frame--dm"
      type="button"
      title="查看守密人立绘"
      aria-label="查看守密人立绘"
      @click.stop="emit('standee', 'assistant')"
    >
      <img
        v-if="!dmAvatarFailed"
        :src="TAVERN_ART.dmAvatar"
        alt=""
        @error="dmAvatarFailed = true"
      >
      <IconCrown v-else />
    </button>

    <div class="t-msg__body">
      <div class="t-msg__meta">
        <template v-if="role === 'assistant'">
          <span class="t-msg__name">守密人 (DM)</span>
          <span class="t-msg__role">地下城主</span>
          <button
            class="t-msg__link"
            type="button"
            @click.stop="emit('standee', 'assistant')"
          >
            [查看全身立绘]
          </button>
        </template>
        <template v-else>
          <button class="t-msg__link" type="button" @click.stop="emit('standee', 'user')">
            [查看立绘]
          </button>
          <span class="t-msg__role t-msg__role--me">玩家</span>
          <span class="t-msg__name t-msg__name--me">{{ userName }}</span>
        </template>
      </div>

      <template v-if="role === 'assistant'">
        <!-- 展示译文：原文保留在服务端/本地，点击「原文」切回 -->
        <div v-if="translation?.showing" class="u-bubble t-bubble">
          <p class="t-seg t-seg--translated">{{ translation.text }}</p>
          <div class="t-msg__foot">
            <span v-if="marked" class="t-mark">🔖 已标注</span>
            <span v-else class="t-msg__foot-space" />
            <button class="t-tr is-on" type="button" @click.stop="emit('translate')">原文</button>
          </div>
        </div>
        <div v-else-if="translation?.status === 'error'" class="u-bubble t-bubble">
          <p class="t-seg t-seg--error">翻译失败，点击「译文」重试</p>
          <div class="t-msg__foot">
            <span class="t-msg__foot-space" />
            <button class="t-tr" type="button" @click.stop="emit('translate')">译文</button>
          </div>
        </div>
        <template v-else>
          <!-- 说话块流：DM 旁白 = 米白气泡；NPC 台词 = 独立 whisper 卡（不塞进 DM 气泡） -->
          <template v-for="(part, pi) in parts" :key="pi">
            <div v-if="part.npc" class="t-npc-card">
              <span class="t-npc-card__ava" aria-hidden="true">
                <img v-if="npcAvatar(part.npc)" :src="npcAvatar(part.npc)!" alt="">
                <template v-else>{{ part.npc.slice(0, 1) }}</template>
              </span>
              <div class="t-npc-card__body">
                <div class="t-npc-card__name">{{ part.npc }}</div>
                <div class="t-npc-card__line">
                  <span
                    v-for="(tok, j) in part.lines[0]!.tokens.slice(part.lines[0]!.skip)"
                    :key="j"
                    class="t-tok"
                    :class="{ 'is-lit': litThrough >= 0 && tok.idx <= litThrough }"
                  >{{ tok.plain }}</span>
                </div>
              </div>
            </div>
            <div v-else class="u-bubble t-bubble">
              <p
                v-for="(line, li) in part.lines"
                :key="li"
                class="t-seg"
                :class="{ 't-seg--quote': line.quote }"
              >
                <span
                  v-for="(tok, j) in line.tokens"
                  :key="j"
                  class="t-tok"
                  :class="{
                    'is-lit': litThrough >= 0 && tok.idx <= litThrough,
                    't-tok--quote': tok.quote,
                  }"
                >{{ tok.plain }}</span>
              </p>
              <!-- 脚注：标注状态 + 译文按钮（设计稿 bubble-footer），挂在最后一个旁白气泡内 -->
              <div v-if="pi === lastTextPart && content.trim()" class="t-msg__foot">
                <span v-if="marked" class="t-mark">🔖 已标注</span>
                <span v-else class="t-msg__foot-space" />
                <button
                  class="t-tr"
                  type="button"
                  :class="{ 'is-on': translation?.showing }"
                  :title="translation?.showing ? '查看原文' : '翻译这段'"
                  @click.stop="emit('translate')"
                >
                  {{ translation?.status === 'loading' ? '翻译中…' : translation?.showing ? '原文' : '译文' }}
                </button>
              </div>
            </div>
          </template>
          <!-- 纯 NPC 台词（无旁白气泡）时脚注兜底 -->
          <div v-if="lastTextPart < 0 && content.trim()" class="t-msg__foot t-msg__foot--bare">
            <span v-if="marked" class="t-mark">🔖 已标注</span>
            <span v-else class="t-msg__foot-space" />
            <button class="t-tr" type="button" @click.stop="emit('translate')">译文</button>
          </div>
        </template>
        <span v-if="live" class="t-caret" aria-hidden="true">▍</span>
      </template>
      <div v-else class="u-bubble t-bubble u-bubble--user">{{ content || '…' }}</div>
    </div>

    <button
      v-if="role === 'user'"
      class="t-ava-frame t-ava-frame--me"
      type="button"
      title="查看我的立绘"
      aria-label="查看我的立绘"
      @click.stop="emit('standee', 'user')"
    >
      <MobileAvatar :src="avatarUrl || TAVERN_ART.pcAvatar" :name="userName || avatarLetter" size="md" />
    </button>
  </div>
</template>
