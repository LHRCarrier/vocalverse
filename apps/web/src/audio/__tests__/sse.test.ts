import { afterEach, describe, expect, it, vi } from 'vitest'

import { openSseFetch, parseSseBuffer, SSE_IDLE_TIMEOUT_MS } from '../sse'

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

  it('audio_chunk 透传服务端时长估算（docs/44 P1-C：duration 可选字段）', () => {
    const [, events] = parseSseBuffer(
      'data: {"type":"audio_chunk","url":"/a/2.mp3","duration":1.5}\n\n',
    )
    expect(events[0]).toEqual({ type: 'audio_chunk', url: '/a/2.mp3', duration: 1.5 })
    // 旧端/旧服务端无 duration 时不影响解析
    const [, legacy] = parseSseBuffer('data: {"type":"audio_chunk","url":"/a/3.mp3"}\n\n')
    expect(legacy[0]).toEqual({ type: 'audio_chunk', url: '/a/3.mp3' })
  })
})

describe('openSseFetch idle 超时（R-18 / 审计 R-18：90s 无字节 → 报错取消）', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  /** 构造假流：read() 顺序返回受控 promise；pending(sentinel=false) 永远挂起。 */
  function makeFakeStream(reads: Array<() => Promise<{ done: boolean; value?: Uint8Array }>>) {
    const cancel = vi.fn().mockResolvedValue(undefined)
    const read = vi.fn()
    reads.forEach((factory) => read.mockImplementationOnce(factory))
    read.mockImplementation(() => new Promise(() => {})) // 默认挂起
    return { ok: true, body: { getReader: () => ({ read, cancel }) } } as unknown as Response
  }

  function mockFetchWith(resp: Response) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(resp))
  }

  it('90s 无任何数据 → onError(SSE 空闲超时) + onClose + cancel', async () => {
    vi.useFakeTimers()
    mockFetchWith(makeFakeStream([]))
    const onError = vi.fn()
    const onClose = vi.fn()
    openSseFetch(
      '/api/v1/sessions/1/turns',
      { method: 'POST', body: new FormData() },
      { onError, onClose },
    )
    await vi.advanceTimersByTimeAsync(SSE_IDLE_TIMEOUT_MS + 1)
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('SSE 空闲超时') }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('数据/心跳到达会重置 idle 计时（85s + 85s 不超时，再到 10s 才超时）', async () => {
    vi.useFakeTimers()
    const enc = new TextEncoder()
    const pingBytes = enc.encode(': ping\n\n')
    const dataBytes = enc.encode('data: {"type":"text_delta","text":"hi"}\n\n')
    // 按真实时序分布：read1(ping) 10s 后到达 → read2(data) 再 20s 后到达 → read3 挂起
    // 预期：每次到达即重置计时（30s+80s=110s 不超时；再 20s > 90s 阈值才超时）
    const calls: Array<() => Promise<{ done: boolean; value?: Uint8Array }>> = [
      () => new Promise((res) => setTimeout(() => res({ done: false, value: pingBytes }), 10_000)),
      () => new Promise((res) => setTimeout(() => res({ done: false, value: dataBytes }), 20_000)),
    ]
    mockFetchWith(makeFakeStream(calls))
    const onError = vi.fn()
    const onEvent = vi.fn()
    openSseFetch(
      '/api/v1/sessions/1/turns',
      { method: 'POST', body: new FormData() },
      { onError, onEvent },
    )
    await vi.advanceTimersByTimeAsync(110_000)
    expect(onEvent).toHaveBeenCalledWith({ type: 'text_delta', text: 'hi' }) // ping 被忽略、data 正常解析
    expect(onError).not.toHaveBeenCalled() // 10s/30s 两次数据各自重置，110s 尚未触发（30+80<90）
    await vi.advanceTimersByTimeAsync(20_000)
    expect(onError).toHaveBeenCalledWith(
      expect.objectContaining({ message: expect.stringContaining('SSE 空闲超时') }),
    )
  })

  it('服务端正常 EOF(done) → 仅 onClose，不报错', async () => {
    vi.useFakeTimers()
    const onError = vi.fn()
    const onClose = vi.fn()
    mockFetchWith(makeFakeStream([async () => ({ done: true })]))
    openSseFetch(
      '/api/v1/sessions/1/turns',
      { method: 'POST', body: new FormData() },
      { onError, onClose },
    )
    await vi.advanceTimersByTimeAsync(0)
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('读取中途拒绝（网络断开）→ onError + onClose（回归：修复前外层 Promise 永不结算，挂起）', async () => {
    vi.useFakeTimers()
    mockFetchWith(makeFakeStream([() => Promise.reject(new Error('network lost'))]))
    const onError = vi.fn()
    const onClose = vi.fn()
    openSseFetch(
      '/api/v1/sessions/1/turns',
      { method: 'POST', body: new FormData() },
      { onError, onClose },
    )
    await vi.advanceTimersByTimeAsync(0)
    expect(onError).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('network lost') }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('abort（AbortError）→ 静默返回，不触发 onError/onClose（主动取消不算错误）', async () => {
    vi.useFakeTimers()
    const abortErr = new Error('aborted')
    abortErr.name = 'AbortError'
    mockFetchWith(makeFakeStream([() => Promise.reject(abortErr)]))
    const onError = vi.fn()
    const onClose = vi.fn()
    openSseFetch(
      '/api/v1/sessions/1/turns',
      { method: 'POST', body: new FormData() },
      { onError, onClose },
    )
    await vi.advanceTimersByTimeAsync(0)
    expect(onError).not.toHaveBeenCalled()
    expect(onClose).not.toHaveBeenCalled()
  })
})
