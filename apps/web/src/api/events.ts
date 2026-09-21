/**
 * 埋点上报（docs/06 §9.1 / docs/53 P1）：20 类事件 + 维度快照 + 幂等去重。
 * 失败静默（埋点非关键路径）；每次生成唯一事件 id 防重复上报。
 * beacon 模式（`beacon: true`）：用于页面卸载/刷新/路由切换边界的关键转化事件，
 * 用 `keepalive: true` 的 fetch 携带 Authorization（sendBeacon 无法带 Authorization
 * header，而本接口经 get_current_user_id 鉴权）。
 *
 * 2026-09-21（docs/53 P1 埋点补齐）：
 * - EventName 与后端 `EventTypes` 20 类**逐一对齐**（原缺读书域 5 类 + 推荐 2 类 → 类型层发不出去）；
 * - 新增 `TargetType`（与后端 `TargetTypes` / DB CHECK 同源），修复答辩 `defense` 被静默丢弃；
 * - 自动携带 `browse_session_id`（每次 App 会话一个，sessionStorage）与 `channel`
 *   （Capacitor 壳 android/ios → pwa 独立窗口 → web），CTR/跳出率的会话去重键；
 * - 退役事件（fun_action / corpus_hit / free_chat_switch / free_chat_rate）保留类型以兼容旧调用，
 *   不再新增生产者（详见 docs/06 §9.1 修订记录）。
 */

let seq = 0

/** 事件全集（与后端 `app/models/base.py:EventTypes` 20 类逐一对齐；运行时可用，供对账测试） */
export const EVENT_NAMES = [
  'page_view',
  'scene_start',
  'recording_start',
  'recording_complete',
  'score_event',
  'corpus_hit',
  'practice_complete',
  'fun_action',
  'free_chat_open',
  'free_chat_turn',
  'free_chat_switch',
  'free_chat_reset',
  'free_chat_rate',
  'recommend_impression',
  'recommend_click',
  'word_lookup',
  'vocab_add',
  'annotation_add',
  'tts_play',
  'tts_prepare',
] as const

export type EventName = (typeof EVENT_NAMES)[number]

/** 埋点目标类型（与后端 TargetTypes / events.target_type CHECK 同源；'scene' 已退役） */
export const TARGET_TYPES = [
  'scene',
  'song',
  'home',
  'defense',
  'trpg',
  'book',
  'card',
  'vocab',
  'post',
] as const

export type TargetType = (typeof TARGET_TYPES)[number]

export type Channel = 'web' | 'pwa' | 'ios' | 'android' | 'other'

export interface TrackOptions {
  page?: string
  targetType?: TargetType
  targetId?: number
  sceneId?: number
  songId?: number
  sessionId?: number
  /** 推荐流渲染组 id（impression 与 click 共享；docs/11 Q-B01） */
  recommendGroupId?: string
  payload?: Record<string, unknown>
  /** 页面卸载/切换边界事件：用 keepalive fetch（可携带 Authorization，不阻塞卸载） */
  beacon?: boolean
}

const BROWSE_SESSION_KEY = 'vv.browse.session'

function newId(): string {
  const c = globalThis.crypto
  if (c && typeof c.randomUUID === 'function') return c.randomUUID()
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

/** 浏览会话 id：前端每次 App 会话生成一次，贯穿 page_view/impression/click（CTR/跳出率去重键）。 */
export function browseSessionId(): string {
  try {
    let id = sessionStorage.getItem(BROWSE_SESSION_KEY)
    if (!id) {
      id = newId()
      sessionStorage.setItem(BROWSE_SESSION_KEY, id)
    }
    return id
  } catch {
    return newId()
  }
}

/** 运行渠道：Capacitor 壳（android/ios）→ PWA 独立窗口 → web（与后端 Channels 同源）。 */
export function clientChannel(): Channel {
  const cap = (globalThis as { Capacitor?: { getPlatform?: () => string } }).Capacitor
  const platform = cap?.getPlatform?.()
  if (platform === 'android') return 'android'
  if (platform === 'ios') return 'ios'
  try {
    if (typeof window !== 'undefined' && window.matchMedia('(display-mode: standalone)').matches) {
      return 'pwa'
    }
  } catch {
    /* 非浏览器环境（测试）→ web */
  }
  return 'web'
}

export async function track(name: EventName, options: TrackOptions = {}): Promise<void> {
  const clientEventId = `${Date.now()}-${(seq++).toString(36)}`
  try {
    const { request } = await import('@/api/client')
    await request('/api/v1/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      keepalive: options.beacon ? true : undefined,
      body: JSON.stringify({
        event_type: name,
        client_event_id: clientEventId,
        occurred_at: Math.floor(Date.now() / 1000),
        page: options.page,
        target_type: options.targetType,
        target_id: options.targetId,
        scene_id: options.sceneId,
        song_id: options.songId,
        session_id: options.sessionId,
        browse_session_id: browseSessionId(),
        recommend_group_id: options.recommendGroupId,
        channel: clientChannel(),
        payload: options.payload ?? {},
      }),
    })
  } catch {
    /* 静默 */
  }
}
