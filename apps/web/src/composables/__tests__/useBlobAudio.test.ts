import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useBlobAudio } from '../useBlobAudio'

/**
 * fe-01 回归：TTS Blob→objectURL 生命周期
 * - revokeUrl 与 createUrl 配对（幂等，重复 revoke 只生效一次）；
 * - releaseAll（组件卸载兜底）清空全部未回收 URL；
 * - 修复前实现（仅 onended revoke/无卸载清理）在以下场景全部泄漏 → 本组用例即回归锁。
 */
describe('useBlobAudio', () => {
  const revoked: string[] = []
  let counter = 0

  beforeEach(() => {
    counter = 0
    revoked.length = 0
    vi.spyOn(URL, 'createObjectURL').mockImplementation(() => `blob:mock-${counter++}`)
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation((u: string) => {
      revoked.push(u)
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('revokeUrl 配对回收（重复调用幂等）', () => {
    const { createUrl, revokeUrl } = useBlobAudio()
    const url = createUrl(new Blob(['x']))
    expect(url).toBe('blob:mock-0')
    revokeUrl(url)
    revokeUrl(url) // 第二次：已回收，不再 revoke
    expect(revoked).toEqual(['blob:mock-0'])
  })

  it('releaseAll 卸载兜底清空全部未回收 URL（含未播完/暂停的）', () => {
    const { createUrl, releaseAll } = useBlobAudio()
    const a = createUrl(new Blob(['a']))
    const b = createUrl(new Blob(['b']))
    const c = createUrl(new Blob(['c']))
    expect([a, b, c]).toEqual(['blob:mock-0', 'blob:mock-1', 'blob:mock-2'])
    releaseAll()
    expect(revoked.sort()).toEqual(['blob:mock-0', 'blob:mock-1', 'blob:mock-2'])
    // 幂等：二次 release 无重复 revoke
    const before = revoked.length
    releaseAll()
    expect(revoked.length).toBe(before)
  })

  it('部分回收后 releaseAll 只清剩余（不重复 revoke 已回收的）', () => {
    const { createUrl, revokeUrl, releaseAll } = useBlobAudio()
    const a = createUrl(new Blob(['a']))
    const b = createUrl(new Blob(['b']))
    expect(a).toBe('blob:mock-0')
    expect(b).toBe('blob:mock-1')
    revokeUrl(a)
    releaseAll()
    expect(revoked.sort()).toEqual(['blob:mock-0', 'blob:mock-1'])
  })
})
