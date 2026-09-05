import { afterEach, describe, expect, it, vi } from 'vitest'

import { shareDemoLink } from '@/composables/share'

describe('shareDemoLink', () => {
  afterEach(() => {
    delete (navigator as unknown as { share?: unknown }).share
    delete (navigator as unknown as { clipboard?: unknown }).clipboard
  })

  it('系统分享可用：调用 share 并返回 shared', async () => {
    const share = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'share', { value: share, configurable: true })
    await expect(shareDemoLink({ title: 't', text: 'x', url: 'u' })).resolves.toBe('shared')
    expect(share).toHaveBeenCalledWith({ title: 't', text: 'x', url: 'u' })
  })

  it('用户取消分享面板（AbortError）→ cancelled', async () => {
    Object.defineProperty(navigator, 'share', {
      value: vi.fn().mockRejectedValue(new DOMException('cancel', 'AbortError')),
      configurable: true,
    })
    await expect(shareDemoLink({ title: 't', url: 'u' })).resolves.toBe('cancelled')
  })

  it('无系统分享：复制链接返回 copied', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
    await expect(shareDemoLink({ title: 't', url: 'u' })).resolves.toBe('copied')
    expect(writeText).toHaveBeenCalledWith('u')
  })

  it('分享失败且无剪贴板 → failed', async () => {
    Object.defineProperty(navigator, 'share', {
      value: vi.fn().mockRejectedValue(new Error('nope')),
      configurable: true,
    })
    await expect(shareDemoLink({ title: 't', url: 'u' })).resolves.toBe('failed')
  })
})
