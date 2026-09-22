/**
 * 酒馆消息分段纯函数（迁移自 ai4u message-utils.npcSegments）：
 * 按空行分段；`名字：内容` 且名字在实体（npc）名单内 → NPC 段（前端渲染人名标签）；
 * 其余 → 旁白段。**不渲染 markdown**（docs/13 §5 转义纪律：AI 文本禁 v-html），
 * 段落以 `white-space: pre-line` 保留换行。
 */

export interface TrpgSegment {
  /** npc 段带名字；旁白段为 null */
  npc: string | null
  text: string
}

const NPC_LINE = /^([^：:\n]{1,12})[：:]\s*(.+)$/

/** 简单的行内标记清洗：去掉 AI 偶发输出的 markdown 粗体/代码标记（保留纯文本） */
export function stripInlineMarks(text: string): string {
  return text
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/^\s{0,3}#{1,6}\s*/gm, '')
}

export function npcSegments(content: string, npcNames: Set<string>): TrpgSegment[] {
  const blocks = content
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean)
  const segments: TrpgSegment[] = []
  let buffer: string[] = []
  let currentNpc: string | null = null

  const flush = () => {
    if (!buffer.length) return
    const text = stripInlineMarks(buffer.join('\n')).trim()
    if (text) segments.push({ npc: currentNpc, text })
    buffer = []
  }

  for (const block of blocks) {
    const lines = block.split('\n')
    const first = lines[0] ?? ''
    const match = NPC_LINE.exec(first)
    const npcName = match && npcNames.has(match[1]!.trim()) ? match[1]!.trim() : null
    if (npcName !== currentNpc) {
      flush()
      currentNpc = npcName
    }
    if (npcName) {
      // NPC 段：名字标签 + 台词（首行去掉 `名字：` 前缀；后续同块行并入）
      const rest = [match![2]!, ...lines.slice(1)].join('\n')
      buffer.push(rest)
    } else {
      buffer.push(block)
    }
  }
  flush()
  return segments
}

/** 场景氛围（迁移自 ai4u scene-utils.toneKey）：四套色仅作用于色条与色点 */
export function sceneTone(scene: string | null | undefined): 'warm' | 'cold' | 'green' | 'city' {
  const s = scene ?? ''
  if (/酒馆|旅店|吧台|客栈|驿站|tavern|inn/i.test(s)) return 'warm'
  if (/地城|地下|遗迹|洞窟|矿坑|密室|dungeon|cave/i.test(s)) return 'cold'
  if (/森林|林地|树林|野外|湖畔|荒原|雪原|林|forest|woods/i.test(s)) return 'green'
  return 'city'
}

/** 城镇/聚落关键词（city 色档内再分「人来人往」与中性文案，避免森林场景显示市集话术） */
const SETTLEMENT = /城|镇|村|集|街|巷|广场|港|市|驿站|营地|town|city|village|market/i

/** 场景氛围文案（顶部状态带右侧提示） */
export function sceneAtmosphere(scene: string | null | undefined): string {
  const s = scene ?? ''
  switch (sceneTone(s)) {
    case 'warm':
      return '烛火与低语 · 适合打听消息'
    case 'cold':
      return '阴暗湿冷 · 小心脚下'
    case 'green':
      return '风声与虫鸣 · 视野开阔'
    default:
      return SETTLEMENT.test(s) ? '人来人往 · 众目睽睽' : '安静得能听见自己的呼吸'
  }
}

/* ============================================================
 * 消息渲染 token / 行 / 说话块（2026-09-22 从 TrpgMessageItem 抽出：
 * 纯函数便于单测，也让组件文件不超 fe-08 行数上限）
 * ============================================================ */

export interface TrpgToken {
  text: string
  /** 全局 token 序号（卡拉OK高亮比较用；跨行拆分的片段沿用父 token 序号） */
  idx: number
  start: number
  /** 渲染用文本（过滤 markdown 标记字符，偏移不变） */
  plain: string
  /** 行内引号内（“…”/「…」）→ 荧光笔式强调（人物说话「画重点」） */
  quote: boolean
}

export interface TrpgLine {
  npc: string | null
  /** NPC 行需跳过的前缀 token 数（「名字：」由卡片标题呈现，避免重复） */
  skip: number
  /** 整行引号包裹（设计稿 dm-quote 高亮） */
  quote: boolean
  tokens: TrpgToken[]
}

export interface TrpgPart {
  npc: string | null
  lines: TrpgLine[]
}

/** token 化：拉丁词/数字为一个 token；CJK 字符逐字；标点/空白并入前一 token */
export function tokenizeTrpg(text: string): TrpgToken[] {
  const out: TrpgToken[] = []
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
    out.push({ text: piece, idx: out.length, start, plain: stripMarks(piece), quote: false })
  }
  return out
}

function stripMarks(s: string): string {
  return s.replace(/\*\*|`|^#{1,6}\s*/g, '')
}

const QUOTE_LINE = /^[“"「『][\s\S]*[”"」』]$/
const NPC_LINE_PREFIX = /^([^：:\n]{1,12})[：:]\s*/

/** 内容 → 行（按换行切分；识别 NPC「名字：」行与整行引号；保留 token 原始字符偏移供高亮） */
export function buildTrpgLines(content: string, npcNames: Set<string>): TrpgLine[] {
  const result: TrpgLine[] = []
  let current: TrpgLine = { npc: null, skip: 0, quote: false, tokens: [] }
  const flush = () => {
    if (current.tokens.some((t) => t.plain.trim())) result.push(current)
    current = { npc: null, skip: 0, quote: false, tokens: [] }
  }
  for (const tok of tokenizeTrpg(content)) {
    const pieces = tok.text.split('\n')
    if (pieces.length === 1) {
      current.tokens.push(tok)
      continue
    }
    // 跨行 token（换行并入前一 token）：切开，前缀入当前行，后续按新行续
    let cursor = tok.start
    pieces.forEach((part, i) => {
      if (i > 0) flush()
      if (part) {
        current.tokens.push({
          text: part,
          idx: tok.idx,
          start: cursor,
          plain: stripMarks(part),
          quote: false,
        })
      }
      cursor += part.length + 1 // +1 = 换行符
    })
  }
  flush()
  for (const line of result) {
    const joined = line.tokens.map((t) => t.text).join('')
    line.quote = QUOTE_LINE.test(joined.trim())
    const m = NPC_LINE_PREFIX.exec(joined)
    if (m && npcNames.has(m[1]!.trim())) {
      line.npc = m[1]!.trim()
      // 前缀（名字 + 冒号）的 token 不再渲染（卡片标题已显示名字），剩余 token 仍带原始偏移
      let consumed = 0
      for (const t of line.tokens) {
        consumed += t.text.length
        line.skip++
        if (consumed >= m[0].length) break
      }
    } else if (!line.quote) {
      // 旁白行内的引语（人物说话）→ 逐 token 标记，渲染成荧光笔式「画重点」
      // （NPC 卡整行已是斜体台词，不再叠加；整行引号走块状 dm-quote 样式）
      markInlineQuotes(line.tokens)
    }
  }
  return result
}

const INLINE_QUOTE = /[“"「『][^”"」』]*[”"」』]/g

function markInlineQuotes(tokens: TrpgToken[]) {
  const joined = tokens.map((t) => t.text).join('')
  const spans: Array<[number, number]> = []
  INLINE_QUOTE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = INLINE_QUOTE.exec(joined)) !== null) spans.push([m.index, m.index + m[0].length])
  if (!spans.length) return
  let pos = 0
  for (const tok of tokens) {
    tok.quote = spans.some(([s, e]) => pos >= s && pos < e)
    pos += tok.text.length
  }
}

/** 说话块：连续旁白行合成一个 DM 气泡，NPC 行各自独立成 whisper 卡（原顺序保留） */
export function groupTrpgParts(lines: TrpgLine[]): TrpgPart[] {
  const out: TrpgPart[] = []
  for (const line of lines) {
    const last = out[out.length - 1]
    if (!line.npc && last && !last.npc) last.lines.push(line)
    else out.push({ npc: line.npc, lines: [line] })
  }
  return out
}
