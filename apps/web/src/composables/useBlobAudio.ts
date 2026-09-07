import { getCurrentInstance, onBeforeUnmount } from 'vue'

/**
 * Blob → objectURL 生命周期管理（性能拷问 fe-01 修复）。
 *
 * 背景缺陷：TTS 播放各视图 `URL.createObjectURL(blob)` 后只在 `audio.onended` revoke；
 * 暂停/切换/卸载时 `onended` 永不触发 → 每个 Blob 必泄漏，移动 WebView 长会话累积 OOM。
 *
 * 约定：`createUrl` / `revokeUrl` 配对使用；`releaseAll` 挂到组件卸载兜底
 * （只要组件还活着，未回收 URL 至少会在卸载那一刻全部销毁）。
 * 播放/回填/重听状态仍由调用方各自管理，本钩子只管 URL 生命周期。
 */
export function useBlobAudio() {
  const urls = new Set<string>()

  function createUrl(blob: Blob): string {
    const url = URL.createObjectURL(blob)
    urls.add(url)
    return url
  }

  function revokeUrl(url: string): void {
    if (urls.delete(url)) URL.revokeObjectURL(url)
  }

  function releaseAll(): void {
    for (const url of urls) URL.revokeObjectURL(url)
    urls.clear()
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(releaseAll)
  }
  return { createUrl, revokeUrl, releaseAll }
}
