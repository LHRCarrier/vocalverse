/**
 * 用户资料 API（社区 S3 · docs/47 §4.2）
 *
 * 读取沿用既有 `GET /auth/me`（本次扩展 avatarUrl/handle），写入走
 * `PATCH /api/v1/users/me` —— 不新增重复的 GET 端点（docs/48 §3-A 裁定）。
 */
import { JAVA_BASE, request } from './client'

export interface MeProfile {
  userId: number
  username: string
  nickname: string
  level: string
  handle?: string | null
  tint?: string | null
  avatarUrl?: string | null
}

export interface PatchMeInput {
  nickname?: string
  handle?: string
  tint?: string
  avatarUrl?: string
}

export async function patchMe(input: PatchMeInput): Promise<MeProfile> {
  const res = await request<MeProfile>(
    '/api/v1/users/me',
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    JAVA_BASE,
  )
  return res.data
}
