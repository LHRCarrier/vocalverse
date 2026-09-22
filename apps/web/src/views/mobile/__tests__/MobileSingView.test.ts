/**
 * MobileSingView（/m/sing）收藏行为测试 —— 2026-09-10 组长需求：
 * 「收藏部分的歌曲应该由用户自主选择，每首歌都要有收藏按钮，再点取消」。
 *
 * 覆盖：
 * - 收藏 tab = **用户收藏**（不再是 level ≤ 2 的难度过滤）——未收藏的歌不出现在该 tab；
 * - 每首歌一颗收藏按钮：点一下→PUT 收藏，再点→DELETE 取消（服务端 favorited 为真源）；
 * - 收藏 tab 内取消 → 该行立即消失（乐观更新）、空态文案出现；
 * - 请求失败 → 状态回滚（不留下假的已收藏），不静默。
 *
 * 修复前必失败证据：改动前 fav tab 过滤条件是 `s.level <= 2`，且行内没有收藏按钮
 * （`button.m-sing-fav` 不存在）——本文件的选择器与断言在修复前取不到任何元素。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileSingView from '@/views/mobile/MobileSingView.vue'
import * as singApi from '@/api/sing'
import type { SongSummary } from '@/api/sing'
import { useUiStore } from '@/stores/ui'

vi.mock('@/audio/recorder', () => ({
  MIN_RECORD_MS: 1000,
  micErrorMessage: (e: unknown) => String(e),
  VoiceRecorder: class {
    state = 'idle'
    liveStream: MediaStream | null = null
    onStateChange?: (s: string) => void
    onStop?: (blob: Blob) => void
    async start() {
      if (this.state === 'recording') return // 与真实实现同款守卫：同态重复 start 静默早退
      this.state = 'recording'
      this.liveStream = {} as MediaStream
      this.onStateChange?.('recording')
    }
    /** 暂停/继续（2026-09-22 深色录唱页新增能力；状态机与真实实现同序） */
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
    /** 正常停止：stopped → onStop（真实实现同序） */
    stop() {
      if (this.state !== 'recording') return
      this.state = 'stopped'
      this.liveStream = null
      this.onStateChange?.('stopped')
      this.onStop?.(new Blob(['x']))
    }
    /** 放弃：cancelled=true → onstop → setState('idle')，不触发 onStop */
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
    // P1-8 需要驱动完整链路（录音→停止→上传→轮询 done）
    createSingSession: vi.fn(),
    uploadSingAudio: vi.fn(),
    fetchSingStatus: vi.fn(),
    fetchSingResult: vi.fn(),
  }
})

// P1-5/P1-7：参考旋律播放走 loadAudioBlob（避免真网络）；图表渲染走 mock（断言"被调用"而非测 d3）
vi.mock('@/api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/client')>()
  return { ...actual, loadAudioBlob: vi.fn(async () => new Blob(['ref-audio'])) }
})
vi.mock('@/lib/sing-chart', () => ({ renderSingChart: vi.fn() }))

/** 三首歌：L1 未收藏 / L3 已收藏 / L4 未收藏（旧的 level≤2 口径会把「L1 未收藏」也算进收藏 tab） */
const songs: SongSummary[] = [
  { id: 1, title: 'Twinkle', artist: 'Traditional', album: '童谣精选集', level: 1, duration_s: 30, pitch_ref_status: 'ready', expected_lines: 6, favorited: false },
  { id: 2, title: 'Mary Had a Little Lamb', artist: 'Traditional', album: '童谣精选集', level: 3, duration_s: 20, pitch_ref_status: 'ready', expected_lines: 4, favorited: true },
  { id: 3, title: 'Ode to Joy', artist: 'Beethoven', album: '古典小品集', level: 4, duration_s: 20, pitch_ref_status: 'ready', expected_lines: 4, favorited: false },
]

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/sing', component: MobileSingView },
    { path: '/m/learn', component: { template: '<div />' } },
  ],
})

async function mountView() {
  await router.push('/m/sing')
  await router.isReady()
  const wrapper = mount(MobileSingView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

/** 切到某个分类（推荐/收藏；2026-09-23 起为 QQ 式横滑 tab） */
async function switchTab(w: Awaited<ReturnType<typeof mountView>>, label: string) {
  const btn = w.findAll('.m-sing-cat').find((b) => b.text().includes(label))
  expect(btn, `分段「${label}」应存在`).toBeTruthy()
  await btn!.trigger('click')
  await flushPromises()
}

/** 某首歌所在的歌单行 */
function rowOf(w: Awaited<ReturnType<typeof mountView>>, title: string) {
  return w.findAll('.m-sing-row').find((r) => r.text().includes(title))
}

/* ---------- P1-5/P1-7：参考旋律播放的假件与句柄记录 ---------- */
const audioInstances: FakeAudio[] = []
const createdUrls: string[] = []
const revokedUrls: string[] = []

class FakeAudio {
  src: string
  onended: (() => void) | null = null
  pause = vi.fn()
  play = vi.fn(async () => {})
  constructor(src: string) {
    this.src = src
    audioInstances.push(this)
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  setActivePinia(createPinia())
  document.body.style.overflow = ''
  audioInstances.length = 0
  createdUrls.length = 0
  revokedUrls.length = 0
  vi.stubGlobal('Audio', FakeAudio)
  // happy-dom 可能未实现 ObjectURL：先补齐再替身，避免 spyOn 抛错
  URL.createObjectURL = ((blob: Blob) => {
    void blob
    const u = `blob:mock/${createdUrls.length}`
    createdUrls.push(u)
    return u
  }) as typeof URL.createObjectURL
  URL.revokeObjectURL = ((u: string) => {
    revokedUrls.push(u)
  }) as typeof URL.revokeObjectURL

  vi.mocked(singApi.fetchSongs).mockResolvedValue(songs.map((s) => ({ ...s })))
  vi.mocked(singApi.fetchSongDetail).mockImplementation(async (songId: number) => {
    const s = songs.find((x) => x.id === songId)!
    return {
      ...s,
      audio_url: '/data/audio/song_twinkle.wav', // P1-5/P1-7：参考旋律可用
      lines: [{ seq: 1, start_ms: 0, end_ms: 1000, text: 'Twinkle twinkle', pitch_ref: { f0s: [440, 440] } }],
    }
  })
  vi.mocked(singApi.setSongFavorite).mockImplementation(async (songId, favorited) => ({
    song_id: songId,
    favorited,
  }))
  // P1-8：完整链路（上传 → 轮询 done → 结果）
  vi.mocked(singApi.createSingSession).mockResolvedValue({ id: 5, kind: 'sing', song_id: 1 })
  // P1-14：受理回执只有 {attempt_id, status}（progress 由轮询端点给，别在后端契约里多写）
  vi.mocked(singApi.uploadSingAudio).mockResolvedValue({
    attempt_id: 9,
    status: 'queued',
  })
  vi.mocked(singApi.fetchSingStatus).mockResolvedValue({
    attempt_id: 9,
    status: 'done',
    progress: { done_lines: 1, total: 1 },
  })
  vi.mocked(singApi.fetchSingResult).mockResolvedValue({
    id: 9,
    song_id: 1,
    duration_s: 30,
    overall: 88,
    pitch: 90,
    rhythm: 80,
    pron: 75,
    is_complete: true,
    expected_lines: 1,
    scoring_version: 'v5',
    lines: [],
    alignment: {},
  })
})

describe('MobileSingView · 收藏', () => {
  it('每首歌都有收藏按钮（三首 → 三颗），初始态取自服务端 favorited', async () => {
    const w = await mountView()
    const rows = w.findAll('.m-sing-row')
    expect(rows).toHaveLength(3)
    expect(w.findAll('button.m-sing-fav')).toHaveLength(3)
    // 已收藏的那首 is-on，其余不亮
    expect(rowOf(w, 'Mary Had a Little Lamb')!.get('button.m-sing-fav').classes()).toContain('is-on')
    expect(rowOf(w, 'Twinkle')!.get('button.m-sing-fav').classes()).not.toContain('is-on')
  })

  it('点收藏按钮 → PUT 收藏；再点 → DELETE 取消（服务端为真源）', async () => {
    const w = await mountView()
    const btn = () => rowOf(w, 'Twinkle')!.get('button.m-sing-fav')

    await btn().trigger('click')
    await flushPromises()
    expect(singApi.setSongFavorite).toHaveBeenCalledWith(1, true)
    expect(btn().classes()).toContain('is-on')
    expect(btn().attributes('aria-pressed')).toBe('true')

    await btn().trigger('click')
    await flushPromises()
    expect(singApi.setSongFavorite).toHaveBeenLastCalledWith(1, false)
    expect(btn().classes()).not.toContain('is-on')
  })

  it('收藏 tab 只显示用户收藏的歌（不是难度过滤：L1 未收藏的歌不出现）', async () => {
    const w = await mountView()
    await switchTab(w, '收藏')
    // 只看歌单行：精选卡固定展示 songs[0]，与 tab 过滤无关
    const rows = w.findAll('.m-sing-row').map((r) => r.text())
    expect(rows).toHaveLength(1)
    expect(rows[0]).toContain('Mary Had a Little Lamb')
    expect(rows.join('|')).not.toContain('Ode to Joy') // L4 未收藏
    expect(rows.join('|')).not.toContain('Twinkle') // L1 未收藏（旧 level≤2 口径会误入）
  })

  it('收藏 tab 内取消收藏 → 该行消失并出现空态文案', async () => {
    const w = await mountView()
    await switchTab(w, '收藏')
    await rowOf(w, 'Mary Had a Little Lamb')!.get('button.m-sing-fav').trigger('click')
    await flushPromises()
    expect(w.findAll('.m-sing-row')).toHaveLength(0)
    expect(w.text()).toContain('还没有收藏的歌曲')
  })

  it('无任何收藏时收藏 tab 为空态（含引导文案）', async () => {
    vi.mocked(singApi.fetchSongs).mockResolvedValue(songs.map((s) => ({ ...s, favorited: false })))
    const w = await mountView()
    await switchTab(w, '收藏')
    expect(w.findAll('.m-sing-row')).toHaveLength(0)
    expect(w.text()).toContain('还没有收藏的歌曲')
    expect(w.text()).toContain('点歌曲右侧的心形按钮收藏')
  })

  it('收藏请求失败 → 状态回滚（不留下假的已收藏）且提示失败', async () => {
    vi.mocked(singApi.setSongFavorite).mockRejectedValue(new Error('network down'))
    const w = await mountView()
    const btn = () => rowOf(w, 'Twinkle')!.get('button.m-sing-fav')

    await btn().trigger('click')
    await flushPromises()
    expect(btn().classes()).not.toContain('is-on')
    expect(useUiStore().toastText).toContain('收藏操作失败')
  })

  it('后端未更新（404）→ toast 直接说明「服务端没有收藏接口」（2026-09-10 真机复现）', async () => {
    const { ApiError } = await import('@/api/client')
    vi.mocked(singApi.setSongFavorite).mockRejectedValue(new ApiError(-1, 'HTTP 404', 404))
    const w = await mountView()
    await rowOf(w, 'Twinkle')!.get('button.m-sing-fav').trigger('click')
    await flushPromises()
    expect(rowOf(w, 'Twinkle')!.get('button.m-sing-fav').classes()).not.toContain('is-on')
    expect(useUiStore().toastText).toContain('服务端没有收藏接口')
  })
})

/**
 * 「放弃重录」后整页按钮失效（2026-09-10 组长真机反馈）——
 * 修复前：cancel() 发出的 'idle' 被 onStateChange 丢弃 → phase 停在 'recording' →
 * 主按钮一直 disabled、停止条两个按钮都成空操作、实时音准线不停 →
 * 用户看到「整个页面功能都失效卡住了」。
 */
describe('MobileSingView · 放弃重录（录音态复位）', () => {
  /** 打开某个歌的跟唱面板并进入录音态 */
  async function startRecording(w: Awaited<ReturnType<typeof mountView>>) {
    await rowOf(w, 'Twinkle')!.get('button.m-sing-row__sing').trigger('click')
    await flushPromises()
    // 2026-09-22 深色录唱页：中心主钮只有图标 → 按 aria-label 定位（旧版按可见文案会取不到）
    const start = w.findAll('button').find((b) => (b.attributes('aria-label') ?? '') === '开始跟唱')
    expect(start, '跟唱面板应有「开始跟唱」').toBeTruthy()
    await start!.trigger('click')
    await flushPromises()
    return start!
  }

  it('放弃重录 → 回到未录音态、主钮重新可用（可再点开始跟唱）', async () => {
    const w = await mountView()
    await startRecording(w)
    // 录音态：底部五键容器带 is-recording；「重录」可点（2026-09-22 深色录唱页：文案缩短为「重录」，
    // 动作全名在 aria-label，测试按 aria-label 定位）
    expect(w.find('.m-sing-dock.is-recording').exists()).toBe(true)
    expect(w.find('button[aria-label="放弃重录"]').exists()).toBe(true)

    await w.get('button[aria-label="放弃重录"]').trigger('click')
    await flushPromises()

    // 复位：回到未录音态，主钮回到「开始跟唱」且可点（修复前这里仍停在录音态且按钮 disabled）
    expect(w.find('.m-sing-dock.is-recording').exists()).toBe(false)
    const start = w.findAll('button').find((b) => (b.attributes('aria-label') ?? '') === '开始跟唱')
    expect(start, '放弃后主钮应回到「开始跟唱」').toBeTruthy()
    expect(start!.attributes('disabled')).toBeUndefined()
  })

  it('放弃后再次开始录音仍然正常进入录音态', async () => {
    const w = await mountView()
    await startRecording(w)
    await w.get('button[aria-label="放弃重录"]').trigger('click')
    await flushPromises()

    await w.get('button[aria-label="开始跟唱"]').trigger('click')
    await flushPromises()
    expect(w.find('.m-sing-dock.is-recording').exists()).toBe(true)
  })

  it('录音中关闭面板 → 录音被取消；重新打开仍能开始录音（修复前必失败）', async () => {
    const w = await mountView()
    await startRecording(w)
    expect(w.find('.m-sing-dock.is-recording').exists()).toBe(true)

    // chevron 关闭（startOver → play.reset()）：修复前只清状态，录音被遗弃在后台
    await w.get('button[aria-label="关闭"]').trigger('click')
    await flushPromises()
    expect(w.find('.m-sing-sheet').exists()).toBe(false)

    // 重新打开同一首歌 → 点开始跟唱：修复前被 start() 同态守卫静默吞掉（界面毫无反应）
    await startRecording(w)
    expect(w.find('.m-sing-dock.is-recording').exists()).toBe(true)
  })

  /**
   * 深色录唱页（2026-09-22 参考图口径）：中心键「开始 ⇄ 暂停 ⇄ 继续」+ 底部「已录 / 全长」。
   * 暂停是新能力（`VoiceRecorder.pause`），本用例锁「点得动 + 状态对 + 文案对」。
   */
  it('中心键：开始 → 暂停 → 继续（aria-label 三态）', async () => {
    const w = await mountView()
    await rowOf(w, 'Twinkle')!.get('button.m-sing-row__sing').trigger('click')
    await flushPromises()
    expect(w.find('button[aria-label="开始跟唱"]').exists()).toBe(true)

    await w.get('button[aria-label="开始跟唱"]').trigger('click')
    await flushPromises()
    expect(w.find('button[aria-label="暂停跟唱"]').exists()).toBe(true)

    await w.get('button[aria-label="暂停跟唱"]').trigger('click')
    await flushPromises()
    expect(w.find('button[aria-label="继续跟唱"]').exists()).toBe(true)
    expect(w.find('.m-sing-dock.is-paused').exists()).toBe(true)
    expect(w.find('.m-sing-top__mode').text()).toBe('暂停中')

    await w.get('button[aria-label="继续跟唱"]').trigger('click')
    await flushPromises()
    expect(w.find('button[aria-label="暂停跟唱"]').exists()).toBe(true)
    expect(w.find('.m-sing-dock.is-paused').exists()).toBe(false)
  })

  it('底部一行显示「歌名 · 已录 / 全长」；未录音时为 00:00 / 全长（契约 duration_s）', async () => {
    const w = await mountView()
    await rowOf(w, 'Twinkle')!.get('button.m-sing-row__sing').trigger('click')
    await flushPromises()
    const foot = w.find('.m-sing-foot')
    expect(foot.exists()).toBe(true)
    expect(foot.find('.m-sing-foot__name').text()).toBe('Twinkle')
    expect(foot.text()).toContain('00:00')
    expect(foot.text()).toContain('00:30') // 契约 duration_s=30 → 全长 00:30
  })

  it('顶栏评级条：无实时分为占位，录音中录音进度线就位', async () => {
    const w = await mountView()
    await startRecording(w)
    expect(w.find('.m-sing-grade').exists()).toBe(true)
    expect(w.find('.m-sing-grade__letter').text()).toBe('—') // 未出声 → 不猜等级
    expect(w.find('.m-sing-top__recbar').exists()).toBe(true) // 3 分钟进度线（只动 transform）
  })

  /**
   * 首帧人声锚点加固（2026-09-22 用户实测「暂停后进度有时候归零」）。
   *
   * 修复前直接把事件值写进 `voiceAtMs`：检测重启（暂停等）会再次触发 `firstVoice`，而 Worker 的
   * 帧时间戳是**跨会话累加**的 → 第二个锚点是个很大的值 → 游标算成负数 → clamp 到 0 →
   * 歌词进度与高亮整个归零。现在**同一轮只认第一个**，且拒绝明显来自上一轮的时间戳。
   */
  it('首帧人声锚点：同一轮只认第一个；跨会话的离谱值被丢弃（修复前必失败）', async () => {
    const w = await mountView()
    await startRecording(w)
    const lane = w.findComponent({ name: 'LivePitchChart' })
    expect(lane.exists(), '引导条组件应已挂载').toBe(true)
    // 第一次锚点：正常值 500ms
    lane.vm.$emit('firstVoice', 500)
    await flushPromises()
    expect((w.vm as unknown as { voiceAtMs: number | null }).voiceAtMs).toBe(500)
    // 第二次锚点（模拟检测重启后 Worker 用累计时间戳重放首帧）：必须被忽略
    lane.vm.$emit('firstVoice', 999_999)
    await flushPromises()
    expect((w.vm as unknown as { voiceAtMs: number | null }).voiceAtMs).toBe(500)
  })
})

/**
 * P0-4（2026-09-10）：跟唱面板曾是 `position:absolute` 挂在随内容长高的 `.u-phone` 上 →
 * 页面滚动后打开面板，面板顶部（关闭/开始跟唱）落在视口上方，用户看到灰白空屏。
 * happy-dom 无排版引擎，故用两层断言钉住修复：
 * ① **样式契约守卫**：读样式表断言面板为视口锚定（`fixed` + 居中 `translateX(-50%)`），
 *    一旦有人改回 `absolute/inset` 立刻红（这正是本 bug 的根因，必须有守卫）；
 * ② **滚动锁行为**：打开面板锁 body 滚动、关闭与卸载都还原（防"锁死整页"）。
 */
describe('MobileSingView · 跟唱面板视口锚定（P0-4）', () => {
  it('样式契约：.m-sing-sheet 必须是 fixed 视口锚定（不得回退为 absolute）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-sing.css'), 'utf-8')
    const block = css.slice(css.indexOf('.m-sing-sheet {'), css.indexOf('.m-sing-top {'))
    expect(block).toContain('position: fixed')
    expect(block).not.toContain('position: absolute')
    expect(block).toContain('translateX(-50%)') // 与 .u-phone（max-width:480px 居中）对齐
    expect(block).toContain('max-width: 480px')
    expect(block).toMatch(/top:\s*0/)
    expect(block).toMatch(/bottom:\s*0/) // 高度由视口决定 → 内部 body 才真正滚动
  })

  it('打开面板锁 body 滚动，关闭后还原（卸载也还原）', async () => {
    const w = await mountView()
    expect(document.body.style.overflow).toBe('')
    await rowOf(w, 'Twinkle')!.get('button.m-sing-row__sing').trigger('click')
    await flushPromises()
    expect(w.find('.m-sing-sheet').exists()).toBe(true)
    expect(document.body.style.overflow).toBe('hidden')

    await w.get('button[aria-label="关闭"]').trigger('click')
    await flushPromises()
    expect(document.body.style.overflow).toBe('')

    // 面板开着直接卸载 → 不得把整页锁死
    await rowOf(w, 'Twinkle')!.get('button.m-sing-row__sing').trigger('click')
    await flushPromises()
    expect(document.body.style.overflow).toBe('hidden')
    w.unmount()
    expect(document.body.style.overflow).toBe('')
  })
})
