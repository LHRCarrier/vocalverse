/**
 * `/m/sing` 视图测试共享脚手架（**非测试文件**：文件名不以 .test.ts 结尾，vitest 不会收集它）。
 *
 * 抽出的背景（2026-09-10）：`MobileSingView.test.ts` 与拆分出的 `MobileSingView.p1.test.ts`
 * 都要 ① mock 路由/挂载 ② 三首歌夹具 ③ Audio/ObjectURL 假件与句柄记录 ④ 默认 API mock 实现；
 * 复制两份必然漂移，且两个文件各自都逼近 eslint `max-lines 350` 门禁。
 *
 * 注意：`vi.mock(...)` 是**文件级**且被提升，必须留在各测试文件内；本模块只放"可以共享的实现"。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { vi } from 'vitest'

import MobileSingView from '@/views/mobile/MobileSingView.vue'
import * as singApi from '@/api/sing'
import type { SongSummary } from '@/api/sing'

/** 三首歌：L1 未收藏 / L3 已收藏 / L4 未收藏（旧「难度 ≤2」口径会把 L1 也算进收藏 tab） */
export const songs: SongSummary[] = [
  { id: 1, title: 'Twinkle', level: 1, pitch_ref_status: 'ready', expected_lines: 6, favorited: false },
  { id: 2, title: 'Mary Had a Little Lamb', level: 3, pitch_ref_status: 'ready', expected_lines: 4, favorited: true },
  { id: 3, title: 'Ode to Joy', level: 4, pitch_ref_status: 'ready', expected_lines: 4, favorited: false },
]

export type SingView = Awaited<ReturnType<typeof mountView>>

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/m/sing', component: MobileSingView },
    { path: '/m/learn', component: { template: '<div />' } },
  ],
})

export async function mountView() {
  await router.push('/m/sing')
  await router.isReady()
  const wrapper = mount(MobileSingView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

/** 某首歌所在的歌单行 */
export function rowOf(w: Awaited<ReturnType<typeof mountView>>, title: string) {
  return w.findAll('.m-sing-row').find((r) => r.text().includes(title))
}

/** 按文案找按钮（找不到即断言失败，避免断言里到处 `!`） */
export function btn(w: Awaited<ReturnType<typeof mountView>>, text: string) {
  const found = w.findAll('button').find((b) => b.text().includes(text))
  if (!found) throw new Error(`按钮不存在：${text}`)
  return found
}

/* ---------- 参考旋律（P1-5/P1-7）假件与句柄记录 ---------- */
export const audioInstances: FakeAudio[] = []
export const createdUrls: string[] = []
export const revokedUrls: string[] = []

export class FakeAudio {
  src: string
  onended: (() => void) | null = null
  pause = vi.fn()
  play = vi.fn(async () => {})
  constructor(src: string) {
    this.src = src
    audioInstances.push(this)
  }
}

/** 每例重置：假 Audio、ObjectURL 记录、body 滚动锁残留 */
export function resetEnvironment() {
  setActivePinia(createPinia())
  document.body.style.overflow = ''
  audioInstances.length = 0
  createdUrls.length = 0
  revokedUrls.length = 0
  vi.stubGlobal('Audio', FakeAudio)
  URL.createObjectURL = ((blob: Blob) => {
    void blob
    const u = `blob:mock/${createdUrls.length}`
    createdUrls.push(u)
    return u
  }) as typeof URL.createObjectURL
  URL.revokeObjectURL = ((u: string) => {
    revokedUrls.push(u)
  }) as typeof URL.revokeObjectURL
}

/** 默认 API mock 实现（各测试可再覆盖） */
export function installApiMocks() {
  vi.mocked(singApi.fetchSongs).mockResolvedValue(songs.map((s) => ({ ...s })))
  vi.mocked(singApi.fetchSongDetail).mockImplementation(async (songId: number) => {
    const s = songs.find((x) => x.id === songId)!
    return {
      ...s,
      audio_url: '/data/audio/song_twinkle.wav', // P1-5/P1-7：参考旋律可用
      lines: [
        { seq: 1, start_ms: 0, end_ms: 1000, text: 'Twinkle twinkle', pitch_ref: { f0s: [440, 440] } },
      ],
    }
  })
  vi.mocked(singApi.setSongFavorite).mockImplementation(async (songId, favorited) => ({
    song_id: songId,
    favorited,
  }))
  vi.mocked(singApi.createSingSession).mockResolvedValue({ id: 5, kind: 'sing', song_id: 1 })
  // 受理回执只有 {attempt_id, status}（P1-14：后端 SubmitAck 无 progress；
  // 进度由 fetchSingStatus 轮询给出——旧的手写 DTO 多写了 progress，属类型谎报）
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
}

/** 打开某歌的跟唱面板 */
export async function openSheet(w: Awaited<ReturnType<typeof mountView>>, title = 'Twinkle') {
  await rowOf(w, title)!.get('button.m-sing-row__hit').trigger('click')
  await flushPromises()
}
