/**
 * M3 手写 DTO（前端先行，docs/13 §7）。
 *
 * 后端 M3 契约（docs/06 §9 / docs/21 §2 端点清单）落地后，这些类型逐条迁入
 * generated/*.d.ts（跑 `pnpm gen:api` 刷新），届时删除对应声明并改从 generated 导入。
 */

// —— 英文歌练唱（docs/06 §9.4）——
// TODO(契约): 迁入 generated/python-api.d.ts

export interface Song {
  id: number
  title: string
  artist: string
  /** 1-4 档 */
  difficulty: number
  genre: string
  bpm: number
  durationSec: number
}

export interface LrcLine {
  index: number
  startMs: number
  endMs: number
  text: string
}

export interface SongLrc {
  songId: number
  lines: LrcLine[]
}

/** 逐句三围评分：音准 / 节奏 / 发音（各 0-100） */
export interface SingLineScore {
  lineIndex: number
  pitch: number
  rhythm: number
  pronunciation: number
}

export interface SingReport {
  songId: number
  /** 综合分（0.5·音准 + 0.2·节奏 + 0.3·发音） */
  score: number
  lines: SingLineScore[]
  createdAt: string
}

// —— 个性化推荐（docs/06 §9.5）——

export type RecommendType = 'scene' | 'song' | 'listening'

export interface RecommendItem {
  id: number
  type: RecommendType
  title: string
  difficulty: number
  tags: string[]
  reason: string
}

export interface LevelForecast {
  dates: string[]
  predicted: number[]
  /** 当前水平（用于图中标注） */
  current: number
}

// —— 可视化报表（docs/06 §9.1）——

export interface StatSeries {
  name: string
  values: number[]
}

export interface StatTrend {
  dates: string[]
  series: StatSeries[]
}

export interface StatRadar {
  dimensions: string[]
  values: number[]
}

/** 四指标口径：CTR / 完成率 / 互动率 / 跳出率（docs/06 §9.1） */
export interface MetricBoard {
  ctr: number
  completion: number
  interaction: number
  bounce: number
}

export interface StatsOverview {
  oralTrend: StatTrend
  singTrend: StatTrend
  oralRadar: StatRadar
  singRadar: StatRadar
  metrics: MetricBoard
}

// —— 社区（docs/06 §9.6）——

export interface CommunityPost {
  id: number
  author: string
  content: string
  likes: number
  liked: boolean
  /** 分享的成绩（可选，携带则渲染成绩卡） */
  score: number
  createdAt: string
}

export interface CheckinStatus {
  checkedIn: boolean
  streakDays: number
}

// —— 管理端（docs/06 §9.3）——
// TODO(契约): 迁入 generated/java-api.d.ts

export interface AdminUser {
  id: number
  email: string
  nickname: string
  level: string
  scenes: number
  score: number
  status: 'active' | 'disabled'
  joined: string
}

export interface AdminScene {
  id: number
  title: string
  sceneType: string
  difficulty: number
  status: 'on' | 'off'
}

export interface AdminSong {
  id: number
  title: string
  artist: string
  difficulty: number
  hasLrc: boolean
  status: 'on' | 'off'
}

export type TicketStatus = 'new' | 'processing' | 'resolved' | 'closed'

export interface AdminTicket {
  id: number
  subject: string
  user: string
  status: TicketStatus
  createdAt: string
}

export interface DashboardMetric {
  label: string
  value: string
  delta: string
  up: boolean
}