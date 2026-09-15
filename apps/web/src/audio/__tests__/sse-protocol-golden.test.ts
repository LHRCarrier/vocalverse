import { readFileSync } from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { parseSseBuffer } from '../sse'

/**
 * SSE 事件协议 golden 校验（va-arch-04：单语料、双端断言）。
 * 与后端 tests/test_sse_protocol_golden.py 同读
 * `services/python/tests/fixtures/sse_event_cases.json`（由后端 pydantic 模型生成的 v1 快照）：
 * 本侧断言 parseSseBuffer 解析结果 == 语料 event；任何一端契约漂移 → 单边 CI 红。
 */

interface GoldenCase {
  name: string
  payload: string
  event: Record<string, unknown>
}

const golden = JSON.parse(
  readFileSync(
    // vitest cwd = apps/web：仓库根 = 两级上级（monorepo 布局，勿用 import.meta.url 拼相对路径）
    path.resolve(process.cwd(), '../../services/python/tests/fixtures/sse_event_cases.json'),
    'utf-8',
  ),
) as { cases: GoldenCase[] }

describe('SSE 协议 golden（后端 pydantic 模型 ↔ 前端 sse.ts 解析器）', () => {
  it('全部语料样例解析一致（含 duration / expected_turn / exclude_none 语义）', () => {
    expect(golden.cases.length).toBeGreaterThanOrEqual(12)
    for (const c of golden.cases) {
      const [rest, events] = parseSseBuffer(c.payload)
      expect(rest).toBe('')
      expect(events).toHaveLength(1)
      expect(events[0]).toEqual(c.event)
    }
  })

  it('exclude_none 语义固化为前端契约（缺省可选字段不在事件对象上）', () => {
    const plain = golden.cases.find((c) => c.name === 'audio_chunk_plain')!
    const legacy = golden.cases.find((c) => c.name === 'turn_end_legacy_no_expected')!
    expect(plain.event).not.toHaveProperty('duration')
    expect(legacy.event).not.toHaveProperty('expected_turn')
  })
})
