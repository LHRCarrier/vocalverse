import { describe, expect, it } from 'vitest'

import { parseSseBuffer } from '../sse'

describe('parseSseBuffer（docs/16 A1：跨 chunk/多 data/心跳/坏块）', () => {
  it('解析单事件', () => {
    const [rest, events] = parseSseBuffer('data: {"type":"turn_start","turn_index":1}\n\n')
    expect(rest).toBe('')
    expect(events).toEqual([{ type: 'turn_start', turn_index: 1 }])
  })

  it('跨 chunk 拼接（不完整事件留在缓冲）', () => {
    const [rest, events] = parseSseBuffer('data: {"type":"text_delta","text":"he')
    expect(events).toEqual([])
    expect(rest).toBe('data: {"type":"text_delta","text":"he')
    const [, events2] = parseSseBuffer(rest + 'llo"}\n\n')
    expect(events2).toEqual([{ type: 'text_delta', text: 'hello' }])
  })

  it('多 data: 行拼接为一条事件（SSE 语义：换行拼接后整体作 payload）', () => {
    const [rest, events] = parseSseBuffer('data: {"type":"meta_block"}\ndata: \n\n')
    expect(rest).toBe('')
    expect(events).toHaveLength(1)
    expect(events[0]?.type).toBe('meta_block')
  })

  it('忽略心跳注释行与未知事件', () => {
    const [rest, events] = parseSseBuffer(': ping\n\ndata: {"type":"turn_end","turn_index":2,"score_status":"ok"}\n\n')
    expect(rest).toBe('')
    expect(events).toEqual([{ type: 'turn_end', turn_index: 2, score_status: 'ok' }])
  })

  it('坏 JSON 块被容忍（不影响后续事件）', () => {
    const [rest, events] = parseSseBuffer('data: {broken\n\ndata: {"type":"error","code":"x","recoverable":true}\n\n')
    expect(rest).toBe('')
    expect(events).toHaveLength(1)
    expect(events[0]?.type).toBe('error')
  })

  it('一次解析多个事件', () => {
    const [rest, events] = parseSseBuffer(
      'data: {"type":"audio_chunk","url":"/a/1.mp3"}\n\ndata: {"type":"turn_end","turn_index":1,"score_status":"ok"}\n\n',
    )
    expect(rest).toBe('')
    expect(events.map((e) => e.type)).toEqual(['audio_chunk', 'turn_end'])
  })
})
