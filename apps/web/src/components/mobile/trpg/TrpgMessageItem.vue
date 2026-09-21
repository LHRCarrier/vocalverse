<script setup lang="ts">
/**
 * 酒馆 · 消息项（迁移自 ai4u MessageItem；2026-09-21 改造）：
 * - 系统卡：open（开场重卡）、scene（过场细线）、dice（判定卡，成功绿/失败红）；
 * - 玩家气泡（右｜炭黑）；DM 气泡（左｜白卡）；
 * - **DM 台词按「名字：」分人名段**（纯文本插值，禁 v-html；docs/13 §5）；
 * - **卡拉OK逐词高亮**：服务端 audio_chunk 带句子文本 + 偏移，播放时按进度点亮到当前词
 *   （token 按原始字符偏移切分，渲染层只做标记字符过滤，不动偏移）；
 * - **长按消息卡 → 弹出操作菜单**（听这句/标注/复制；替代旧气泡尾重播按钮）。
 */
import { computed } from 'vue'

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
    /** 已标注（长按菜单切换；展示左侧标记） */
    marked?: boolean
    /** 朗读高亮（仅 role=assistant；未在播为 null） */
    highlight?: { offset: number | null; length: number | null; progress: number } | null
  }>(),
  {
    kind: 'text',
    payload: null,
    live: false,
    npcNames: () => new Set<string>(),
    avatarLetter: '我',
    marked: false,
    highlight: null,
  },
)

const emit = defineEmits<{ actions: [] }>()

const isSystem = computed(() => props.kind === 'system')
const sysType = computed(() => String(props.payload?.trpg_sys ?? ''))
const scenePayload = computed(() => props.payload ?? {})

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
const LONG_PRESS_MS = 450
let pressTimer: ReturnType<typeof setTimeout> | null = null

function cancelPress() {
  if (pressTimer != null) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
}
function startPress() {
  if (isSystem.value) return
  cancelPress()
  pressTimer = setTimeout(() => {
    pressTimer = null
    emit('actions')
  }, LONG_PRESS_MS)
}

/* ---------------- 逐词高亮（卡拉OK） ---------------- */
interface Token {
  text: string
  /** 全局 token 序号（高亮比较用；跨行拆分的片段沿用父 token 序号） */
  idx: number
  start: number
  /** 渲染用文本（过滤 markdown 标记字符，偏移不变） */
  plain: string
}

const tokens = computed<Token[]>(() => tokenize(props.content))
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

/** token 化：拉丁词/数字为一个 token；CJK 字符逐字；标点/空白并入前一 token */
function tokenize(text: string): Token[] {
  const out: Token[] = []
  const re = /[A-Za-z0-9''-]+|[\u4e00-\u9fff]|[\s\S]/g
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const piece = m[0]
    const start = m.index
    const isSpaceOrPunct = /^[\s\S]$/.test(piece) && !/[A-Za-z0-9\u4e00-\u9fff]/.test(piece)
    if (isSpaceOrPunct && out.length) {
      const last = out[out.length - 1]!
      last.text += piece
      last.plain += piece
      continue
    }
    out.push({ text: piece, idx: out.length, start, plain: stripMarks(piece) })
  }
  return out
}

function stripMarks(s: string): string {
  return s.replace(/\*\*|`|^#{1,6}\s*/g, '')
}

interface Line {
  npc: string | null
  tokens: Token[]
}

const lines = computed<Line[]>(() => {
  const result: Line[] = []
  let current: Line = { npc: null, tokens: [] }
  const flush = () => {
    const hasText = current.tokens.some((t) => t.plain.trim())
    if (hasText) result.push(current)
    current = { npc: null, tokens: [] }
  }
  for (const tok of tokens.value) {
    const parts = tok.text.split('\n')
    if (parts.length === 1) {
      current.tokens.push(tok)
      continue
    }
    // 跨行 token（换行并入前一 token）：切开，前缀入当前行，后续按新行续
    let cursor = tok.start
    parts.forEach((part, i) => {
      if (i > 0) {
        flush()
      }
      if (part) {
        current.tokens.push({ text: part, idx: tok.idx, start: cursor, plain: stripMarks(part) })
      }
      cursor += part.length + 1 // +1 = 换行符
    })
  }
  flush()
  // NPC 行识别：行首 token 以「名字：」开头且名字在名单内
  for (const line of result) {
    const joined = line.tokens.map((t) => t.text).join('')
    const m = /^([^：:\n]{1,12})[：:]\s*/.exec(joined)
    if (m && props.npcNames.has(m[1]!.trim())) {
      line.npc = m[1]!.trim()
    }
  }
  return result
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

  <!-- 未知系统卡：降级为文本（前向兼容） -->
  <div v-else-if="isSystem" class="t-scene-line">{{ content || `系统卡：${sysType}` }}</div>

  <!-- 气泡（长按 → 操作菜单；DM 支持卡拉OK高亮） -->
  <div
    v-else
    class="u-chat t-msg"
    :class="{ 'u-chat--user': role === 'user', 'is-marked': marked }"
    @touchstart.passive="startPress"
    @touchmove="cancelPress"
    @touchend="cancelPress"
    @touchcancel="cancelPress"
    @contextmenu.prevent="isSystem || emit('actions')"
  >
    <span v-if="role === 'assistant'" class="u-ava t-ava--dm" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <path
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          stroke-linecap="round"
          d="M4 8h13a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6a2 2 0 0 1 2-2Zm15 3h1a2 2 0 0 1 0 4h-1"
        />
      </svg>
    </span>
    <div class="u-bubble" :class="role === 'user' ? 'u-bubble--user' : 'u-bubble--ai'">
      <template v-if="role === 'assistant'">
        <p v-for="(line, i) in lines" :key="i" class="t-seg" :class="{ 't-seg--npc': line.npc }">
          <span v-if="line.npc" class="t-seg__npc">{{ line.npc }}</span>
          <span
            v-for="(tok, j) in line.tokens"
            :key="j"
            class="t-tok"
            :class="{ 'is-lit': litThrough >= 0 && tok.idx <= litThrough }"
          >{{ tok.plain }}</span>
        </p>
        <span v-if="live" class="t-caret" aria-hidden="true">▍</span>
        <span v-if="marked" class="t-mark" title="已标注">🔖 已标注</span>
      </template>
      <template v-else>{{ content || '…' }}</template>
    </div>
    <span v-if="role === 'user'" class="u-ava u-ava--me" aria-hidden="true">{{ avatarLetter }}</span>
  </div>
</template>
