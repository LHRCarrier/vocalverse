/**
 * 分享演示工具（2026-09-05 统一：社区/我的/唱吧/报告共用）
 * 系统分享面板可用 → share；不可用 → 复制链接；返回状态供页面 toast。
 */
export type ShareResult = 'shared' | 'copied' | 'cancelled' | 'failed'

export async function shareDemoLink(opts: { title: string; text?: string; url: string }): Promise<ShareResult> {
  if (navigator.share) {
    try {
      await navigator.share(opts)
      return 'shared'
    } catch (err) {
      // 用户取消分享面板（AbortError）不打 toast，其余按失败
      return err instanceof DOMException && err.name === 'AbortError' ? 'cancelled' : 'failed'
    }
  }
  try {
    await navigator.clipboard?.writeText(opts.url)
    return 'copied'
  } catch {
    return 'failed'
  }
}
