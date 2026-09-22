/**
 * 工单用户侧 API（docs/06 §9.6）：提交反馈/报错/内容纠误 + 查看自己工单。
 * 契约见 Java `TicketController`（`/manage/api/v1/tickets`，Envelope）；账户抽屉「帮助与反馈」消费。
 */
import { JAVA_BASE, request } from './client'

export type TicketKind = 'feedback' | 'bug' | 'content_correction'
export type TicketStatus = 'open' | 'processing' | 'resolved' | 'closed'

export interface TicketView {
  id: number
  userId: number
  kind: TicketKind
  targetType?: string | null
  targetId?: number | null
  title?: string | null
  content: string
  status: TicketStatus
  adminReply?: string | null
  resolvedAt?: string | null
  createdAt?: string | null
  updatedAt?: string | null
}

export async function createTicket(input: {
  kind: TicketKind
  content: string
  title?: string
}): Promise<TicketView> {
  const res = await request<TicketView>(
    '/api/v1/tickets',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targetType: 'none', ...input }),
    },
    JAVA_BASE,
  )
  return res.data
}

export async function fetchMyTickets(): Promise<TicketView[]> {
  const res = await request<TicketView[]>('/api/v1/tickets/mine', undefined, JAVA_BASE)
  return res.data
}
