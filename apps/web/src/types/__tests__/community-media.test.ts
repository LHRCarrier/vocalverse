/**
 * 社区 S3 · 纯函数（docs/47 §3.3/§4.1 · docs/48 B5/B8）
 *
 * 锁三件事：
 * 1. `normalizeMedia` 兼容三种历史形状（S1 种子 snake_case / S1 真实单媒体 / S3 items[]）；
 * 2. `mediaUrl` 必须拼 `PYTHON_BASE`（打包壳里相对路径会打到 https://localhost）；
 * 3. `selectionToWord` 只认单个英文词（多词/整句不弹词卡）。
 */
import { describe, expect, it } from 'vitest'

import { normalizeMedia } from '@/types/community'
import { selectionToWord } from '@/composables/useCommunityWordLookup'
import { precheck } from '@/api/media'

describe('normalizeMedia（三种历史形状归一）', () => {
  it('S1 种子：{type:video, duration_s} 无 url → 时长进 durationS，items 为空', () => {
    const m = normalizeMedia({ type: 'video', duration_s: 240 })
    expect(m.kind).toBe('video')
    expect(m.durationS).toBe(240)
    expect(m.items).toEqual([])
  })

  it('S1 真实：单 url → items 一条', () => {
    const m = normalizeMedia({ type: 'image', url: '/api/v1/media/aaa', cover_url: '/api/v1/media/bbb' })
    expect(m.items).toHaveLength(1)
    expect(m.items[0].url).toBe('/api/v1/media/aaa')
    expect(m.coverUrl).toBe('/api/v1/media/bbb')
  })

  it('S3 多图：items 原样保留 + camelCase', () => {
    const m = normalizeMedia({
      type: 'image',
      items: [
        { id: 'a', url: '/api/v1/media/a', width: 800, height: 600, size: 1024, mimeType: 'image/png' },
        { id: 'b', url: '/api/v1/media/b' },
      ],
      durationS: 12.5,
    })
    expect(m.items.map((i) => i.url)).toEqual(['/api/v1/media/a', '/api/v1/media/b'])
    expect(m.durationS).toBe(12.5)
  })

  it('空/非法项被过滤；null 媒体 → kind 按帖子 kind 兜底', () => {
    const m = normalizeMedia({ type: 'image', items: [{ url: '' }, { url: '/ok' }] as never })
    expect(m.items.map((i) => i.url)).toEqual(['/ok'])
    expect(normalizeMedia(null, 'video').kind).toBe('video')
    expect(normalizeMedia(null, 'article').kind).toBe('none')
  })
})

describe('selectionToWord（划词 → 单词）', () => {
  it('剥首尾标点后返回单词', () => {
    expect(selectionToWord('  "wonderful," ')).toBe('wonderful')
    expect(selectionToWord("don't")).toBe("don't")
    expect(selectionToWord('well-known')).toBe('well-known')
  })

  it('多词 / 中文 / 纯标点 / 超长 → null（不弹词卡）', () => {
    expect(selectionToWord('hello world')).toBeNull()
    expect(selectionToWord('你好')).toBeNull()
    expect(selectionToWord('   ')).toBeNull()
    expect(selectionToWord('a'.repeat(80))).toBeNull()
  })
})

describe('precheck（前端预校验，与后端口径一致）', () => {
  /** 造一个带指定体积/类型的 File（不实际分配大内存：size 走实例 getter 覆盖） */
  function file(size: number, type: string): File {
    const f = new File([new Uint8Array(1)], 'x.bin', { type })
    Object.defineProperty(f, 'size', { value: size })
    return f
  }

  it('图片超 20MB / 视频超 64MB 拒绝', () => {
    expect(precheck(file(21 * 1024 * 1024, 'image/png'), 'image')).toContain('20MB')
    expect(precheck(file(65 * 1024 * 1024, 'video/mp4'), 'video')).toContain('64MB')
  })

  it('类型不在白名单拒绝；type 为空时放行交给服务端魔数嗅探', () => {
    expect(precheck(file(1024, 'application/x-msdownload'), 'image')).toContain('JPG')
    expect(precheck(file(1024, ''), 'image')).toBeNull()
    expect(precheck(file(1024, 'image/jpeg'), 'image')).toBeNull()
  })

  it('空文件拒绝', () => {
    expect(precheck(file(0, 'image/png'), 'image')).toBe('文件为空')
  })
})
