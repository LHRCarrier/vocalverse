/**
 * 手动打卡（Python `POST /api/v1/checkin` · 2026-09-21 改版）
 *
 * 打卡不再由练习收尾自动触发：用户在打卡页显式调用本接口；同一天重复调用幂等
 * （服务端聚合当日练习后刷新同一张卡）。
 */
import { request } from './client'

export interface CheckinResult {
  /** 打卡日（YYYY-MM-DD） */
  date: string
  /** 当日已完成口语练习次数（可为 0——先打卡后练习同样成立） */
  practiceCount: number
  /** 当日最佳综合分（无练习为 null） */
  overall: number | null
}

export async function manualCheckin(date: string): Promise<CheckinResult> {
  const res = await request<CheckinResult>('/api/v1/checkin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date }),
  })
  return res.data
}
