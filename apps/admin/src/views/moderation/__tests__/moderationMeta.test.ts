/**
 * 审核工作台展示口径的回归测试（docs/58）。
 *
 * 钉住三件事，它们都属于「后端数据没错、前端画错/读错」的静默缺陷：
 * 1. 队列默认视图必须包含 `open`（升级件不能从待办里消失）；
 * 2. 趋势图的「新建」必须接 `created` 而不是 `pending`（v1 图例与数据不符）；
 * 3. AI 送审证据只在有 `snapshot.ai` 时展示，没有就不编。
 */
import { describe, expect, it } from 'vitest'

import type { ModerationSnapshot } from '@/api'

import { CASE_STATUS_FILTER_OPTIONS, aiEvidenceText, trendSeries } from '../moderationMeta'

describe('队列状态筛选（docs/58 §5.1）', () => {
  it('选项值与 ModerationController.listCases 的 @Pattern 逐字一致（含聚合项 open）', () => {
    // 权威来源：ModerationController.listCases
    //   @Pattern(regexp = "open|pending|approved|rejected|escalated|withdrawn")
    expect(CASE_STATUS_FILTER_OPTIONS.map((o) => o.value)).toEqual([
      'open',
      'pending',
      'escalated',
      'approved',
      'rejected',
      'withdrawn',
    ])
  })

  it('open 只是查询别名，不在 CaseView.status 的取值域里；且排在筛选首位（队列默认值）', () => {
    // CaseView.status ∈ pending/approved/rejected/escalated/withdrawn（ModerationCaseEntity.STATUS_*）
    const caseStatuses = ['pending', 'approved', 'rejected', 'escalated', 'withdrawn']
    expect(caseStatuses).not.toContain('open')
    expect(CASE_STATUS_FILTER_OPTIONS[0].value).toBe('open')
  })
})

describe('趋势序列口径（v1 把 pending 当「新建」画）', () => {
  it('新建 = created；created 缺失退 0；与 pending 严格区分', () => {
    const series = trendSeries([
      { date: '2026-09-01', created: 3, pending: 2, approved: 1, rejected: 0 },
      { date: '2026-09-02', pending: 5, approved: 4, rejected: 1 },
    ])
    expect(series.labels).toEqual(['09-01', '09-02'])
    expect(series.created).toEqual([3, 0])
    expect(series.decided).toEqual([1, 4])
    expect(series.rejected).toEqual([0, 1])
    // 修复前「新建」接的是 pending（[2,5]）；这条断言防回潮
    expect(series.created).not.toEqual([2, 5])
  })

  it('trend 缺省 → 空序列，不抛错、不编造', () => {
    expect(trendSeries(undefined)).toEqual({ labels: [], created: [], decided: [], rejected: [] })
  })
})

describe('自动送审证据展示（snapshot.ai）', () => {
  it('完整证据 → 一行可读文本（概率/条款号/类型/严重度/模型）', () => {
    const snap: ModerationSnapshot = {
      ai: {
        model: 'jev-1.13.0',
        violation: 0.962,
        clause: 'R2',
        category: 'abuse',
        clauseConfidence: 0.81,
        severity: 1.96,
      },
    }
    const text = aiEvidenceText(snap)
    expect(text).toContain('违规概率 96%')
    expect(text).toContain('类型 辱骂骚扰（R2）')
    expect(text).toContain('严重度 1.96/3')
    expect(text).toContain('jev-1.13.0')
  })

  it('clause=none 不显示条款号（兼容上游异常/旧数据）', () => {
    const text = aiEvidenceText({
      ai: { violation: 0.8, clause: 'none', category: 'other', severity: 1 },
    })
    expect(text).toContain('类型 其他')
    expect(text).not.toContain('none')
  })

  it('举报/人工单（无 ai）→ null；不伪造证据', () => {
    expect(aiEvidenceText({ reportCount: 2 })).toBeNull()
    expect(aiEvidenceText({ ai: null })).toBeNull()
    expect(aiEvidenceText(null)).toBeNull()
    expect(aiEvidenceText(undefined)).toBeNull()
  })
})
