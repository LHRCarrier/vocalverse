/**
 * `/m/sing` **P1 批次**视图测试（2026-09-10，拷问报告 §3.2）：
 * - P1-5 参考旋律与录音互斥（录音前必须停播，否则原唱入麦）；
 * - P1-7 参考旋律 ObjectURL 回收 + 加载中重入守卫（不再叠播/泄漏）；
 * - P1-6 列表加载失败 = 错误态 + 重试（不再永久「加载中…」+ 谎报空态）；
 * - P1-8 报告图表以模板 ref 渲染（不再靠 `document.getElementById` 静默跳过）。
 *
 * 脚手架在 `singViewUtils.ts`（非测试文件）；基础用例见 `MobileSingView.test.ts`。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'

import { renderSingChart } from '@/lib/sing-chart'
import * as clientApi from '@/api/client'
import * as singApi from '@/api/sing'

import {
  audioInstances,
  btn,
  createdUrls,
  installApiMocks,
  mountView,
  openSheet,
  resetEnvironment,
  revokedUrls,
  songs,
} from './singViewUtils'

vi.mock('@/audio/recorder', () => ({
  MIN_RECORD_MS: 1000,
  micErrorMessage: (e: unknown) => String(e),
  VoiceRecorder: class {
    state = 'idle'
    liveStream: MediaStream | null = null
    onStateChange?: (s: string) => void
    onStop?: (blob: Blob) => void
    async start() {
      if (this.state === 'recording') return
      this.state = 'recording'
      this.liveStream = {} as MediaStream
      this.onStateChange?.('recording')
    }
    pause() {
      if (this.state !== 'recording') return
      this.state = 'paused'
      this.onStateChange?.('paused')
    }
    resume() {
      if (this.state !== 'paused') return
      this.state = 'recording'
      this.onStateChange?.('recording')
    }
    stop() {
      if (this.state !== 'recording') return
      this.state = 'stopped'
      this.liveStream = null
      this.onStateChange?.('stopped')
      this.onStop?.(new Blob(['x']))
    }
    cancel() {
      this.state = 'idle'
      this.liveStream = null
      this.onStateChange?.('idle')
    }
  },
}))

vi.mock('@/api/sing', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/sing')>()
  return {
    ...actual,
    fetchSongs: vi.fn(),
    fetchSongDetail: vi.fn(),
    setSongFavorite: vi.fn(),
    createSingSession: vi.fn(),
    uploadSingAudio: vi.fn(),
    fetchSingStatus: vi.fn(),
    fetchSingResult: vi.fn(),
  }
})

vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, loadAudioBlob: vi.fn(async () => new Blob(['ref-audio'])) }
})
vi.mock('@/lib/sing-chart', () => ({ renderSingChart: vi.fn() }))

beforeEach(() => {
  vi.clearAllMocks()
  resetEnvironment()
  installApiMocks()
})

describe('MobileSingView · P1（参考旋律 / 加载错误态 / 报告图）', () => {
  it('P1-5：点「开始跟唱」会先停参考旋律（修复前原唱被一起录进麦克风）', async () => {
    const w = await mountView()
    await openSheet(w)
    await btn(w, '听参考旋律').trigger('click')
    await flushPromises()
    expect(audioInstances).toHaveLength(1)
    expect(audioInstances[0].play).toHaveBeenCalled()

    await btn(w, '开始跟唱').trigger('click')
    await flushPromises()
    expect(audioInstances[0].pause).toHaveBeenCalled() // 修复前：仍在播放（原唱入麦）
  })

  it('P1-7：加载中连点不叠出第二路 Audio；停止即 revoke（不再泄漏整份音频）', async () => {
    const pending: { resolve?: (b: Blob) => void } = {}
    vi.mocked(clientApi.loadAudioBlob).mockImplementationOnce(
      () =>
        new Promise<Blob>((res) => {
          pending.resolve = res
        }),
    )
    const w = await mountView()
    await openSheet(w)

    await btn(w, '听参考旋律').trigger('click') // 第一次：挂起中
    await btn(w, '听参考旋律').trigger('click') // 第二次：应被重入守卫忽略
    await flushPromises()
    expect(audioInstances).toHaveLength(0)

    pending.resolve?.(new Blob(['audio']))
    await flushPromises()
    expect(audioInstances).toHaveLength(1) // 修复前：会创建第二个 Audio（首路永不可停）
    expect(createdUrls).toHaveLength(1)

    await btn(w, '停止参考旋律').trigger('click')
    await flushPromises()
    expect(revokedUrls).toEqual(createdUrls) // 修复前：三处退出路径都只 pause，从不 revoke
  })

  it('P1-6：加载失败显示错误态 + 重试（修复前永久「加载中…」且无重试入口）', async () => {
    vi.mocked(singApi.fetchSongs).mockRejectedValue(new Error('网络断了'))
    const w = await mountView()
    expect(w.text()).toContain('歌曲库加载失败')
    expect(w.text()).toContain('网络断了')
    expect(w.text()).not.toContain('加载中…')

    vi.mocked(singApi.fetchSongs).mockResolvedValue(songs.map((s) => ({ ...s })))
    await btn(w, '重试').trigger('click')
    await flushPromises()
    expect(singApi.fetchSongs).toHaveBeenCalledTimes(2)
    expect(w.findAll('.m-sing-row')).toHaveLength(3)
  })

  it('P1-8：结果就绪即以模板 ref 渲染图表（不再靠 document.getElementById 找元素）', async () => {
    vi.useFakeTimers()
    try {
      const w = await mountView()
      await openSheet(w)
      await btn(w, '开始跟唱').trigger('click')
      await flushPromises()
      await btn(w, '停止并评分').trigger('click')
      await flushPromises()
      await vi.advanceTimersByTimeAsync(2000) // 轮询 1500ms 后 done
      await flushPromises()

      expect(renderSingChart).toHaveBeenCalledTimes(1)
      const [el] = vi.mocked(renderSingChart).mock.calls[0]
      expect(el).toBeInstanceOf(HTMLElement) // 传的是 ref 命中的容器本身
    } finally {
      vi.useRealTimers()
    }
  })

  it('P1-8：源码契约——图表容器不得再退回 id + getElementById', () => {
    // 该组合在"元素尚不存在"时静默跳过（面板关闭时结果落地 → 永久空盒，拷问报告 A-F4）。
    // 2026-09-22：报告（含图表容器与 ref）随 `SingReport.vue` 下沉 → 契约指向新文件。
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const src = readFileSync(resolve(process.cwd(), 'src/components/sing/SingReport.vue'), 'utf-8')
    expect(src).not.toContain("getElementById('m-sing-chart')")
    expect(src).toContain('ref="chartEl"')
    // 视图侧不得再自己找元素渲染图表（渲染职责已下沉）
    const view = readFileSync(resolve(process.cwd(), 'src/views/mobile/MobileSingView.vue'), 'utf-8')
    expect(view).not.toContain('renderSingChart')
  })
})

/**
 * 歌单屏状态与文案（2026-09-22 歌单排版优化）——与 P1-6/P1-8 同主题，故并到本文件。
 *
 * 修复前：加载态是「深青大卡写加载中…」再跳变成内容卡；错误态也用同一张内容卡（语义混淆）；
 * 加载中还会同时出现「共 0 首」与「这个分类还没有歌」两句自相矛盾的话（P1-6 只修了 hero 卡）。
 */
describe('MobileSingView · 歌单屏状态与文案', () => {
  it('加载中 → 骨架卡（aria-busy），不再出现「加载中…」深青卡，也不出现自相矛盾的空态', async () => {
    let resolveSongs!: (v: typeof songs) => void
    vi.mocked(singApi.fetchSongs).mockImplementationOnce(
      () =>
        new Promise<typeof songs>((res) => {
          resolveSongs = res
        }),
    )
    const w = await mountView() // flushPromises 不会 resolve 这个挂起请求 → 停在 loading
    const skel = w.find('.u-comm-skel')
    expect(skel.exists()).toBe(true)
    expect(skel.attributes('aria-busy')).toBe('true')
    expect(w.text()).not.toContain('加载中…')
    expect(w.text()).not.toContain('共 0 首')
    expect(w.text()).not.toContain('这个分类还没有歌')

    resolveSongs(songs.map((s) => ({ ...s })))
    await flushPromises()
    expect(w.find('.u-comm-skel').exists()).toBe(false)
    expect(w.findAll('.m-sing-row')).toHaveLength(3)
    expect(w.text()).toContain('歌曲库 · 共 3 首')
  })

  it('加载失败 → u-comm-empty（与兄弟页同款），文案与重试入口保留', async () => {
    vi.mocked(singApi.fetchSongs).mockRejectedValueOnce(new Error('网络断了'))
    const w = await mountView()
    expect(w.find('.u-comm-empty').exists()).toBe(true)
    expect(w.find('.u-comm-empty__title').text()).toBe('歌曲库加载失败')
    expect(w.find('.u-comm-empty__sub').text()).toContain('网络断了')
    expect(w.find('.u-comm-empty__btn').text()).toContain('重试')
    expect(w.text()).not.toContain('这个分类还没有歌')
    expect(w.text()).not.toContain('共 0 首')
  })

  it('精选卡已抽成组件；「热门」口径改名「短歌」', async () => {
    const w = await mountView()
    expect(w.find('.m-feat').exists()).toBe(true) // SingFeaturedCard 根节点
    expect(w.find('.m-feat__facts').text()).toBe('6 句 · 可跟唱')
    expect(w.text()).toContain('短歌')
    expect(w.text()).not.toContain('热门')
  })
})
