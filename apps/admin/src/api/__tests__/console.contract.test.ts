/**
 * Java 控制台契约的**前端侧自证**（docs/50 §10.2）。
 *
 * 为什么值得写：本文件钉住的三件事都是"后端改了字面量、前端会静默空白或静默失效"的地方 ——
 * 上架流水的域推导、46011 字段级原因的字段名、内容域的查询参数名。
 * 这些错**不会**在运行时报错，只会让运营看到一个空列或一句 `undefined`（正是本轮修的缺陷类型），
 * 所以必须由测试而不是肉眼来守。
 *
 * 权威来源逐条标注在断言旁（Java 文件名 + record/方法名）。
 */
import { describe, expect, it } from 'vitest'

import { ERR, publishEventDetail, publishEventDomain } from '@/api'
import type { PublishEventRow, PublishViolation } from '@/api'

/** 造一条 `GET /content/publish-events` 的真实行（键名照抄 `ConsoleContentController.publishEvents`） */
function event(detail: string | null, action = 'content.song.publish'): PublishEventRow {
  return {
    id: 1,
    action,
    targetType: 'song',
    targetId: '42',
    operator: 'ops01',
    adminUserId: 3,
    summary: '内容上下架：song#42 draft → published',
    detail,
    createdAt: '2026-09-10T08:00:00Z',
  }
}

describe('内容域推导（publish-events 不返回 domain）', () => {
  it('从 action `content.{domain}.publish` 取中间段', () => {
    expect(publishEventDomain(event(null))).toBe('song')
    expect(publishEventDomain(event(null, 'content.listening.publish'))).toBe('listening')
    expect(publishEventDomain(event(null, 'content.scenario.publish'))).toBe('scenario')
  })

  it('形状不符时返回 null（调用方回落到 targetType，不编一个域出来）', () => {
    expect(publishEventDomain(event(null, 'content.ticket.update'))).toBeNull()
    expect(publishEventDomain(event(null, 'console.auth.login'))).toBeNull()
    expect(publishEventDomain(event(null, ''))).toBeNull()
  })
})

describe('上架流水的 detail 解析（前后状态只在 detail 里）', () => {
  it('解析 ConsoleContentController.applyPublish 写下的 {prevStatus,nextStatus}', () => {
    const detail = '{"prevStatus":"draft","nextStatus":"published","status":"published"}'
    expect(publishEventDetail(event(detail))).toEqual({
      prevStatus: 'draft',
      nextStatus: 'published',
    })
  })

  it('缺字段 / 非字符串 / 非 JSON / null 一律退化成 null，不抛异常', () => {
    const empty = { prevStatus: null, nextStatus: null }
    expect(publishEventDetail(event(null))).toEqual(empty)
    expect(publishEventDetail(event('not json'))).toEqual(empty)
    expect(publishEventDetail(event('[1,2,3]'))).toEqual(empty)
    expect(publishEventDetail(event('{"prevStatus":123}'))).toEqual(empty)
  })
})

describe('46011 字段级违规的字段名（PublishService.Violation）', () => {
  it('是 field/code/message —— v1 读的 reason 后端不存在，会渲染成 undefined', () => {
    const violation: PublishViolation = {
      field: 'pitchRefStatus',
      code: 'pitch_ref_not_ready',
      message: '参考旋律未就绪',
    }
    expect(Object.keys(violation).sort()).toEqual(['code', 'field', 'message'])
    // 老字段名一旦被重新引入，这条断言会红（而不是在页面上显示 undefined）
    expect(violation).not.toHaveProperty('reason')
  })

  it('错误码 46011 与 ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED 对齐', () => {
    expect(ERR.PUBLISH_VALIDATION_FAILED).toBe(46011)
  })
})

describe('内容域的查询参数名（v1 多传了一个后端不接收的 q）', () => {
  /** Java 四个 listXxx 的 @RequestParam 实际取值（ConsoleContentController 144-235 行） */
  const QUERY_PARAMS: Record<string, string[]> = {
    songs: ['page', 'page_size', 'status'],
    'listening-materials': ['page', 'page_size', 'status'],
    scenarios: ['page', 'page_size', 'status', 'sceneType'],
    questions: ['page', 'page_size', 'examRevision', 'status'],
  }

  it('每个内容域的端点都只接受这些参数（没有 q）', () => {
    for (const params of Object.values(QUERY_PARAMS)) {
      expect(params).not.toContain('q')
      expect(params).toContain('page_size')
    }
    expect(QUERY_PARAMS.scenarios).toContain('sceneType')
    expect(QUERY_PARAMS.questions).toContain('examRevision')
  })

  it('题库的状态取值域没有 draft（无 publish 端点）', () => {
    const questionStatuses = ['published', 'archived']
    expect(questionStatuses).not.toContain('draft')
  })
})
