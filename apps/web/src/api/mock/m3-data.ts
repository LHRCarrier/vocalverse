/**
 * M3 mock 数据层（前端先行，docs/13 §8 预览工作流）。
 *
 * 五个模块的假数据集中于此，类型对齐 api/m3-types.ts（未来对齐后端 DTO）。
 * 后端契约落地后，各 api/<domain>.ts 从本文件取数改为 request() 真实端点，
 * 本文件仅作为 seed/演示兜底保留或删除。
 *
 * 版权纪律（docs/06 §9.7）：曲目一律自创占位，不粘贴真实商用歌词。
 */
import type {
  AdminScene,
  AdminSong,
  AdminTicket,
  AdminUser,
  CommunityPost,
  DashboardMetric,
  LevelForecast,
  MetricBoard,
  RecommendItem,
  SingLineScore,
  Song,
  SongLrc,
  StatRadar,
  StatTrend,
  StatsOverview,
} from '@/api/m3-types'
import { deterministicScore } from '@/composables/useSingScore'

// —— 歌曲列表（自创占位曲目）——
export const mockSongs: Song[] = [
  { id: 1, title: 'Sunrise', artist: 'VocalVerse 原创', difficulty: 1, genre: 'Pop', bpm: 120, durationSec: 24 },
  { id: 2, title: 'River Flow', artist: 'VocalVerse 原创', difficulty: 2, genre: 'Folk', bpm: 92, durationSec: 16 },
  { id: 3, title: 'Starlight', artist: 'VocalVerse 原创', difficulty: 3, genre: 'Pop', bpm: 100, durationSec: 20 },
]

// —— LRC 逐句歌词（自创占位，规避版权）——
function lrc(songId: number, lines: Array<[string, number]>): SongLrc {
  return {
    songId,
    lines: lines.map(([text, i]) => ({
      index: i,
      startMs: i * 4000,
      endMs: (i + 1) * 4000,
      text,
    })),
  }
}

export const mockLrc: Record<number, SongLrc> = {
  1: lrc(1, [
    ['The morning light is calling me', 0],
    ['A brand new day begins to glow', 1],
    ['I step outside and breathe it in', 2],
    ['The world is waking soft and slow', 3],
    ['With every step I feel alive', 4],
    ['Chasing dreams before they go', 5],
  ]),
  2: lrc(2, [
    ['The river keeps on moving on', 0],
    ['It never stops to say goodbye', 1],
    ['It carries all our hopes along', 2],
    ['Beneath the wide and open sky', 3],
  ]),
  3: lrc(3, [
    ['When the night is dark and long', 0],
    ['I look up to the starlight', 1],
    ['A million little sparks of hope', 2],
    ['They guide me through the quiet', 3],
    ['Until the morning light', 4],
  ]),
}

// —— 唱歌逐句三围评分（确定性假评分，seed 与视图录制生成一致）——
function buildAttempts(songId: number, lineCount: number): SingLineScore[] {
  return Array.from({ length: lineCount }, (_, i) => {
    const seed = songId * 100 + i
    return {
      lineIndex: i,
      pitch: deterministicScore(seed),
      rhythm: deterministicScore(seed + 1),
      pronunciation: deterministicScore(seed + 2),
    }
  })
}

export const mockSingAttempts: Record<number, SingLineScore[]> = {
  1: buildAttempts(1, mockLrc[1].lines.length),
  2: buildAttempts(2, mockLrc[2].lines.length),
  3: buildAttempts(3, mockLrc[3].lines.length),
}

// —— 个性化推荐（3 画像互异）——
export const mockRecommendations: RecommendItem[] = [
  {
    id: 1,
    type: 'scene',
    title: '咖啡馆点单',
    difficulty: 2,
    tags: ['口语', '高频场景'],
    reason: '你本周缺场景对话练习，先补高频开口',
  },
  {
    id: 2,
    type: 'song',
    title: 'Sunrise',
    difficulty: 1,
    tags: ['唱歌', '入门'],
    reason: '音准得分上升，适合巩固连读',
  },
  {
    id: 3,
    type: 'listening',
    title: '慢速英语播客 · 新闻',
    difficulty: 2,
    tags: ['听力', '泛听'],
    reason: '流利度待提升，建议每日泛听 10 分钟',
  },
]

export const mockLevelForecast: LevelForecast = {
  dates: ['W1', 'W2', 'W3', 'W4', 'W5', 'W6'],
  predicted: [58, 61, 64, 67, 70, 73],
  current: 57,
}

// —— 可视化报表 ——
export const mockOralTrend: StatTrend = {
  dates: ['08-26', '08-27', '08-28', '08-29', '08-30', '08-31', '09-01'],
  series: [
    { name: '发音', values: [62, 65, 64, 68, 70, 72, 74] },
    { name: '语法', values: [58, 60, 62, 61, 66, 68, 69] },
    { name: '流利度', values: [55, 57, 60, 63, 64, 67, 71] },
  ],
}

export const mockSingTrend: StatTrend = {
  dates: ['08-26', '08-27', '08-28', '08-29', '08-30', '08-31', '09-01'],
  series: [
    { name: '音准', values: [60, 63, 66, 65, 70, 73, 76] },
    { name: '节奏', values: [66, 64, 68, 70, 69, 72, 74] },
    { name: '发音', values: [61, 63, 65, 67, 69, 71, 73] },
  ],
}

export const mockOralRadar: StatRadar = {
  dimensions: ['发音', '语法', '流利度', '词汇', '连贯'],
  values: [74, 69, 71, 66, 68],
}

export const mockSingRadar: StatRadar = {
  dimensions: ['音准', '节奏', '发音', '气息', '情感'],
  values: [76, 74, 73, 68, 70],
}

export const mockMetrics: MetricBoard = {
  ctr: 12.5,
  completion: 68.4,
  interaction: 42.1,
  bounce: 31.2,
}

export const mockStats: StatsOverview = {
  oralTrend: mockOralTrend,
  singTrend: mockSingTrend,
  oralRadar: mockOralRadar,
  singRadar: mockSingRadar,
  metrics: mockMetrics,
}

// —— 社区 ——
export const mockCheckin: { checkedIn: boolean; streakDays: number } = {
  checkedIn: true,
  streakDays: 6,
}

export const mockCommunity: CommunityPost[] = [
  { id: 1, author: 'lhr', content: '今天完成 3 轮咖啡馆场景，发音稳了！', likes: 12, liked: false, score: 82, createdAt: '09-01 09:24' },
  { id: 2, author: 'xiaoxiao', content: '首唱 Sunrise，音准 85，坚持练连读～', likes: 8, liked: true, score: 78, createdAt: '09-01 08:10' },
  { id: 3, author: 'faust', content: '答辩导师连问 5 道，语法覆盖度提升明显。', likes: 21, liked: false, score: 91, createdAt: '08-31 22:40' },
]

// —— 管理端 ——
export const mockAdminUsers: AdminUser[] = [
  { id: 1, email: 'lhr@example.com', nickname: 'lhr', level: 'L3', scenes: 42, score: 78.5, status: 'active', joined: '08-26' },
  { id: 2, email: 'xiaoxiao@example.com', nickname: 'xiaoxiao', level: 'L2', scenes: 17, score: 62.1, status: 'active', joined: '08-27' },
  { id: 3, email: 'faust@example.com', nickname: 'faust', level: 'L4', scenes: 88, score: 91.3, status: 'disabled', joined: '08-28' },
]

export const mockAdminScenes: AdminScene[] = [
  { id: 1, title: '咖啡馆点单', sceneType: 'cafe', difficulty: 2, status: 'on' },
  { id: 2, title: '机场值机', sceneType: 'airport', difficulty: 3, status: 'on' },
  { id: 3, title: '英文面试', sceneType: 'interview', difficulty: 4, status: 'off' },
]

export const mockAdminSongs: AdminSong[] = mockSongs.map((s) => ({
  id: s.id,
  title: s.title,
  artist: s.artist,
  difficulty: s.difficulty,
  hasLrc: true,
  status: 'on',
}))

/** 管理端歌曲库 LRC 词库编辑用（由 mockLrc 派生，mock 会话内原地修改） */
export const mockAdminSongLrc: Record<number, string> = Object.fromEntries(
  Object.values(mockLrc).map((l) => [l.songId, l.lines.map((line) => line.text).join('\n')]),
)

export const mockAdminTickets: AdminTicket[] = [
  { id: 1, subject: '口语评分偏低，希望看到逐句反馈', user: 'lhr', status: 'new', createdAt: '09-01 10:02' },
  { id: 2, subject: '唱歌录音在移动端无法开始', user: 'xiaoxiao', status: 'processing', createdAt: '08-31 21:18' },
  { id: 3, subject: '报表导出格式希望能加 PDF', user: 'faust', status: 'resolved', createdAt: '08-30 14:55' },
]

export const mockDashboardMetrics: DashboardMetric[] = [
  { label: '点击率 CTR', value: '12.5%', delta: '↑ 1.2pt', up: true },
  { label: '完成率', value: '68.4%', delta: '↑ 5.1pt', up: true },
  { label: '互动率', value: '42.1%', delta: '↓ 0.8pt', up: false },
  { label: '跳出率', value: '31.2%', delta: '↓ 3.4pt', up: true },
]