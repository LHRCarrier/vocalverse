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
  if (/酒馆|旅店|吧台|tavern|inn/i.test(s)) return 'warm'
  if (/地城|地下|遗迹|洞窟|dungeon|cave/i.test(s)) return 'cold'
  if (/森林|野外|湖畔|forest|woods/i.test(s)) return 'green'
  return 'city'
}

/** 场景氛围文案（顶部状态带右侧提示） */
export function sceneAtmosphere(scene: string | null | undefined): string {
  switch (sceneTone(scene)) {
    case 'warm':
      return '烛火与低语 · 适合打听消息'
    case 'cold':
      return '阴暗湿冷 · 小心脚下'
    case 'green':
      return '风声与虫鸣 · 视野开阔'
    default:
      return '人来人往 · 众目睽睽'
  }
}
