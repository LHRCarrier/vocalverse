/**
 * 媒体选择器（社区 S3 · docs/47 §5.2 · docs/48 B13）
 *
 * 锁三件事：
 * 1. 选文件 → 前端预校验（超大/非法类型当场拒绝，不发请求）；
 * 2. 上传成功 → 把 `MediaAssetView` 交回父级（发布时进 `media.items`）；
 * 3. 上传失败 → **弹层内内联报错**（不用 toast：toast z-index 9 < 遮罩 60，看不见）。
 *
 * 注意：组件走 `Teleport to="body"`，断言一律查 `document`。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'

import MobileMediaPicker from '@/components/mobile/MobileMediaPicker.vue'

const api = vi.hoisted(() => ({ uploadMedia: vi.fn() }))

vi.mock('@/api/media', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/media')>()
  return { ...actual, uploadMedia: (...a: unknown[]) => api.uploadMedia(...a) }
})

function makeFile(name: string, type: string, size = 2048): File {
  const f = new File([new Uint8Array(1)], name, { type })
  Object.defineProperty(f, 'size', { value: size })
  return f
}

/** 给 file input 装一个可反复覆盖的 files（原生 files 只读且不可重定义） */
let current: File[] = []
function setFiles(input: HTMLInputElement, files: File[]) {
  current = files
  if (!Object.getOwnPropertyDescriptor(input, 'files')) {
    Object.defineProperty(input, 'files', {
      configurable: true,
      get: () => current,
    })
  }
  input.dispatchEvent(new Event('change'))
}

async function mountPicker(props: Record<string, unknown> = {}) {
  const wrapper = mount(MobileMediaPicker, {
    props: { open: true, kind: 'image', selected: [], ...props },
  })
  await flushPromises()
  return wrapper
}

function fileInput(): HTMLInputElement {
  return document.querySelector('input[type="file"]') as HTMLInputElement
}

function errText(): string {
  return document.querySelector('.u-mp__err')?.textContent ?? ''
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

/**
 * happy-dom 不真正解码 blob 图片（既不发 load 也不发 error）→ readMeta 会等满超时。
 * 这里替换成同步触发的假 Image，让上传流程在测试里立即推进。
 */
class FakeImage {
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  naturalWidth = 800
  naturalHeight = 600
  set src(_v: string) {
    queueMicrotask(() => this.onload?.())
  }
}

describe('MobileMediaPicker', () => {
  beforeEach(() => {
    current = []
    vi.stubGlobal('Image', FakeImage)
    api.uploadMedia.mockReset().mockResolvedValue({
      id: 'pub1',
      url: '/api/v1/media/pub1',
      kind: 'image',
      mimeType: 'image/png',
      size: 2048,
      width: 800,
      height: 600,
      durationS: null,
    })
  })

  it('选图 → 上传成功 → emit update:selected 带 MediaAssetView', async () => {
    const wrapper = await mountPicker()
    setFiles(fileInput(), [makeFile('a.png', 'image/png')])
    await flushPromises()

    expect(api.uploadMedia).toHaveBeenCalledTimes(1)
    const events = wrapper.emitted('update:selected')
    expect(events).toBeTruthy()
    const list = events!.at(-1)![0] as Array<{ url: string }>
    expect(list[0].url).toBe('/api/v1/media/pub1')
    wrapper.unmount()
  })

  it('超大体积：不发请求，弹层内内联报错', async () => {
    const wrapper = await mountPicker()
    setFiles(fileInput(), [makeFile('big.png', 'image/png', 21 * 1024 * 1024)])
    await flushPromises()
    expect(api.uploadMedia).not.toHaveBeenCalled()
    expect(errText()).toContain('20MB')
    wrapper.unmount()
  })

  it('非法类型：不发请求 + 内联报错（type 为空时放行交给服务端魔数嗅探）', async () => {
    const wrapper = await mountPicker()
    setFiles(fileInput(), [makeFile('x.exe', 'application/x-msdownload')])
    await flushPromises()
    expect(api.uploadMedia).not.toHaveBeenCalled()
    expect(errText()).toContain('JPG')

    setFiles(fileInput(), [makeFile('unknown', '')])
    await flushPromises()
    expect(api.uploadMedia).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('上传失败：错误行内联展示，可重试', async () => {
    api.uploadMedia.mockRejectedValueOnce(new Error('图片超过 20MB'))
    const wrapper = await mountPicker()
    setFiles(fileInput(), [makeFile('a.png', 'image/png')])
    await flushPromises()
    expect(errText()).toContain('图片超过 20MB')

    setFiles(fileInput(), [makeFile('a.png', 'image/png')])
    await flushPromises()
    expect(api.uploadMedia).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('视频 kind：已选 1 个后按钮禁用（视频恒为 1）', async () => {
    const wrapper = await mountPicker({
      kind: 'video',
      selected: [
        {
          id: 'v1',
          url: '/api/v1/media/v1',
          kind: 'video',
          mimeType: 'video/mp4',
          size: 100,
          width: null,
          height: null,
          durationS: 12,
        },
      ],
    })
    const addBtn = document.querySelectorAll('.u-mp__actions button')[0] as HTMLButtonElement
    expect(addBtn.disabled).toBe(true)
    wrapper.unmount()
  })
})
