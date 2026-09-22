/**
 * 酒馆美术资源（设计稿 `local/跑团设计/` 的 AI 生成图，已复制进 `public/tavern/`）。
 *
 * 口径（2026-09-22）：DM/PC 头像与全身立绘、示例 NPC 老陈头像是**设计稿占位素材**——
 * 真实「角色描述 → 文生图 → 挂实体档案」能力未实现（docs/54），先用设计稿图占位；
 * NPC 头像按名字命中（当前仅示例老陈），未命中的 NPC 仍回退「名字首字」方块。
 */
const BASE = import.meta.env.BASE_URL

export const TAVERN_ART = {
  dmAvatar: `${BASE}tavern/dm-avatar.webp`,
  pcAvatar: `${BASE}tavern/pc-avatar.webp`,
  dmStandee: `${BASE}tavern/dm-standee.webp`,
  pcStandee: `${BASE}tavern/pc-standee.webp`,
} as const

const NPC_AVATARS: Record<string, string> = {
  老陈: `${BASE}tavern/npc-laochen.webp`,
  'Lao Chen': `${BASE}tavern/npc-laochen.webp`,
}

/** NPC 名字 → 头像（去掉括号注记后精确匹配；无命中返回 null → 首字占位） */
export function npcAvatar(name: string): string | null {
  const key = name.replace(/[（(].*$/, '').trim()
  return NPC_AVATARS[key] ?? null
}
