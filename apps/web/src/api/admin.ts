/**
 * 管理端 API（docs/06 §9.3，Java /manage）：用户/场景/歌曲(LRC)/工单/评价看板。
 * NOTE: M3 后端契约未落地，当前返回 mock 并在会话内原地生效；接线后改 request()。
 */
import {
  mockAdminScenes,
  mockAdminSongLrc,
  mockAdminSongs,
  mockAdminTickets,
  mockAdminUsers,
  mockDashboardMetrics,
} from './mock/m3-data'
import type {
  AdminScene,
  AdminSong,
  AdminTicket,
  AdminUser,
  DashboardMetric,
  TicketStatus,
} from './m3-types'

const delay = (ms = 200) => new Promise<void>((r) => setTimeout(r, ms))

// 模块级内存态：mock 会话内 CRUD 立即生效（接线后由后端持久化）
let users = mockAdminUsers.map((u) => ({ ...u }))
let scenes = mockAdminScenes.map((s) => ({ ...s }))
let songs = mockAdminSongs.map((s) => ({ ...s }))
const songLrc = { ...mockAdminSongLrc }
let tickets = mockAdminTickets.map((t) => ({ ...t }))

// —— 用户 ——
// TODO(契约): GET /manage/users
export async function fetchUsers(): Promise<AdminUser[]> {
  await delay()
  return users.map((u) => ({ ...u }))
}

// TODO(契约): PATCH /manage/users/{id}
export async function toggleUser(id: number): Promise<AdminUser[]> {
  await delay(100)
  users = users.map((u) =>
    u.id === id ? { ...u, status: u.status === 'active' ? 'disabled' : 'active' } : u,
  )
  return users.map((u) => ({ ...u }))
}

// —— 场景 ——
// TODO(契约): GET /manage/scenes
export async function fetchScenes(): Promise<AdminScene[]> {
  await delay()
  return scenes.map((s) => ({ ...s }))
}

export async function toggleScene(id: number): Promise<AdminScene[]> {
  await delay(100)
  scenes = scenes.map((s) =>
    s.id === id ? { ...s, status: s.status === 'on' ? 'off' : 'on' } : s,
  )
  return scenes.map((s) => ({ ...s }))
}

export async function createScene(payload: Omit<AdminScene, 'id'>): Promise<AdminScene[]> {
  await delay(100)
  const id = scenes.reduce((max, s) => Math.max(max, s.id), 0) + 1
  scenes = [...scenes, { ...payload, id, status: 'off' }]
  return scenes.map((s) => ({ ...s }))
}

export async function updateScene(id: number, patch: Partial<AdminScene>): Promise<AdminScene[]> {
  await delay(100)
  scenes = scenes.map((s) => (s.id === id ? { ...s, ...patch } : s))
  return scenes.map((s) => ({ ...s }))
}

// —— 歌曲 ——
// TODO(契约): GET /manage/songs
export async function fetchSongs(): Promise<AdminSong[]> {
  await delay()
  return songs.map((s) => ({ ...s }))
}

export async function toggleSong(id: number): Promise<AdminSong[]> {
  await delay(100)
  songs = songs.map((s) =>
    s.id === id ? { ...s, status: s.status === 'on' ? 'off' : 'on' } : s,
  )
  return songs.map((s) => ({ ...s }))
}

// TODO(契约): GET /manage/songs/{id}/lrc
export async function fetchAdminSongLrc(id: number): Promise<string> {
  await delay()
  return songLrc[id] ?? ''
}

// TODO(契约): PUT /manage/songs/{id}/lrc
export async function updateAdminSongLrc(id: number, lrc: string): Promise<void> {
  await delay(100)
  songLrc[id] = lrc
}

// —— 工单 ——
// TODO(契约): GET /manage/tickets
export async function fetchTickets(): Promise<AdminTicket[]> {
  await delay()
  return tickets.map((t) => ({ ...t }))
}

// TODO(契约): PATCH /manage/tickets/{id}
export async function updateTicket(id: number, status: TicketStatus): Promise<AdminTicket[]> {
  await delay(100)
  tickets = tickets.map((t) => (t.id === id ? { ...t, status } : t))
  return tickets.map((t) => ({ ...t }))
}

// —— 评价看板 ——
// TODO(契约): GET /manage/dashboard
export async function fetchDashboardMetrics(): Promise<DashboardMetric[]> {
  await delay()
  return mockDashboardMetrics.map((m) => ({ ...m }))
}