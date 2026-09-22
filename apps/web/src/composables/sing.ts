/**
 * 唱吧全链路（M3 唱歌 P0）：
 * loadSongs（选歌）→ openSong（详情 + 40905 门禁）→ startRecording（≤180s）→
 * createSingSession → uploadSingAudio → 轮询 status（退避 + onUnmounted 中止）→
 * 结果（逐句 + D3 图数据）。
 *
 * 本轮询为组件无关组合式：MobileSingView（真形态）与 SingingPreview（联调页）共用同一逻辑，
 * UI 侧只订阅 phase/result 状态。中止纪律：组件卸载必须调 stop()（防泄漏定时器）。
 */
import { computed, onUnmounted, ref, toRef } from 'vue'
import type { Ref } from 'vue'

import { VoiceRecorder, micErrorMessage } from '@/audio/recorder'
import { useSingStore } from '@/stores/sing'
import { track } from '@/api/events'
import {
  createSingSession,
  fetchSingResult,
  fetchSingStatus,
  fetchSongDetail,
  setSongFavorite,
  singErrorMessage,
  singFailureMessage,
  favoriteErrorMessage,
  uploadSingAudio,
} from '@/api/sing'
import type {
  SingAttemptResult,
  SingAttemptStatus,
  SongDetail,
  SongSummary,
} from '@/api/sing'

export type SingPhase =
  | 'pick'
  | 'loading'
  | 'idle'
  | 'recording'
  | 'uploading'
  | 'processing'
  | 'done'
  | 'failed'

/**
 * 跟唱单次录音上限（ms）：180s（docs/06 §9.4「整首 ≤180s」口径）。
 *
 * 单一来源：既作为 `recorder.start()` 的自动停止上限，也作为面板头部录音进度线的分母
 * （2026-09-22 排版优化把「录音 3 分钟自动停止」从底部一行小字变成可见进度，
 * 两处若各写一个字面量，改一处就会出现「进度条走完了录音还没停」）。
 */
export const SING_MAX_RECORD_MS = 180_000

export interface SingPlay {
  songs: Ref<SongSummary[]>
  detail: Ref<SongDetail | null>
  phase: Ref<SingPhase>
  error: Ref<string | null>
  status: Ref<SingAttemptStatus | null>
  result: Ref<SingAttemptResult | null>
  progressPct: import('vue').ComputedRef<number>
  loadSongs: () => Promise<void>
  openSong: (songId: number) => Promise<boolean>
  /**
   * 收藏切换（同一按钮再点取消）：乐观更新 + 失败回滚；
   * 返回新状态（true=已收藏 / false=已取消），失败返回 null（原因见 favoriteError）。
   */
  toggleFavorite: (songId: number) => Promise<boolean | null>
  /** 最近一次收藏失败的原因文案（按 HTTP 状态区分：404=后端未重建 / 401=登录过期 / 5xx=未迁移等） */
  favoriteError: Ref<string | null>
  /** 已收藏歌曲（「收藏」tab 数据源；顺序同歌曲列表） */
  favorites: import('vue').ComputedRef<SongSummary[]>
  /** 提交整首音频（自动建会话 + 上传 + 轮询；recorder onStop 与外部上传共用） */
  submitAudio: (blob: Blob) => Promise<void>
  startRecording: () => void
  stopRecording: () => void
  /** 暂停 = 录音仍在进行但暂停采集（暂停段不入音频） */
  pauseRecording: () => void
  /** 继续：结算暂停时长并按剩余额度重挂自动停止 */
  resumeRecording: () => void
  /** 是否处于「录音暂停中」（2026-09-22 深色录唱页：中心钮变「继续」、计时与歌词游标冻结） */
  paused: Ref<boolean>
  cancelRecording: () => void
  /** 同一录音流（实时音准线用，docs/06 §9.4 注记；录音态非空、停止后 null） */
  getLiveStream: () => MediaStream | null
  retry: () => void
  reset: () => void
  stop: () => void
}

export function useSingPlay(): SingPlay {
  /**
   * 歌曲列表真源在 store（2026-09-21）：「当前跟唱歌曲」要能被导航栏等其他模块同步读取，
   * 列表不能只活在本组合式实例里；页面 / 桌面顶栏 / 移动选曲 sheet 共读同一份，
   * 收藏态的乐观更新也改的是同一批对象（不再是「页面一份、导航一份」）。
   * 本组合式的**公开 API 不变**（`songs` 仍是 `Ref<SongSummary[]>`）。
   */
  const sing = useSingStore()
  const songs = toRef(sing, 'songs')
  const detail = ref<SongDetail | null>(null)
  const phase = ref<SingPhase>('pick')
  /** 录音暂停中（phase 仍为 'recording'：会话未结束） */
  const paused = ref(false)
  const error = ref<string | null>(null)
  const status = ref<SingAttemptStatus | null>(null)
  const result = ref<SingAttemptResult | null>(null)
  const favoriteError = ref<string | null>(null)

  const recorder = new VoiceRecorder()
  /**
   * recorder 状态 → 视图 phase 的映射（单一约定：**非 recording 即复位**，与
   * PlacementView / DefenseView / MobileFreeChatView / MobileTavernView 等录音页同款）。
   *
   * 2026-09-10 BUG 修复：「放弃重录」后整页按钮失效——`cancel()` 走
   * `recorder.stop() → onstop(cancelled) → setState('idle')`，旧实现只处理
   * error/recording、**丢掉 idle** → phase 永远停在 'recording'：主按钮一直 disabled
   * （录音中…），「停止并评分」被 `stop()` 的非录音态守卫挡成空操作，「放弃重录」再点也只是
   * 重复发同一个被忽略的 idle，实时音准线因无响应式变化而不冷却（读数冻结在最后一帧）。
   * 现在 idle/stopped 只在「确实处于 recording」时复位（正常停止路径随即被 submitAudio
   * 同步置为 'uploading'，不会闪回）。
   */
  recorder.onStateChange = (s) => {
    if (s === 'error') phase.value = 'failed'
    else if (s === 'recording') {
      phase.value = 'recording'
      paused.value = false
    } else if (s === 'paused') {
      // 暂停（2026-09-22 深色录唱页）：**会话仍在进行** → phase 保持 recording，
      // 只翻 paused 标志（视图据此把中心钮变「继续」、冻结计时/歌词游标与进度线）。
      paused.value = true
    } else if (phase.value === 'recording') {
      phase.value = 'idle'
      paused.value = false
    }
  }
  recorder.onStop = (blob) => {
    void submitAudio(blob)
  }

  let pollTimer: ReturnType<typeof setTimeout> | null = null
  let sessionId = 0
  let attemptId = 0
  /**
   * 轮询**世代号**（P1-2，2026-09-10）：换歌/重置/重试后自增，在飞请求回来时先校验
   * `my !== epoch` 即静默丢弃——修复前 `stop()` 只 `clearTimeout`，已经发出的 status/result
   * 请求仍会落地并写 `result/phase`，于是"评分中关面板→换歌→等落地"会在**新歌标题下渲染旧歌
   * 成绩**（拷问报告 P1-2 / A-F2 实测：RTT 放大到 5s 时 100% 命中）。
   * 依据：docs/21 §3.6（轮询语义）、docs/35（App 交互确定性）。
   *
   * **世代不变量（2026-09-14 评审 R4 收紧）**：一次提交 + 它引发的整轮轮询**共用一个世代**
   * （`submitAudio` 取一次、`poll(my)` 沿用）；`poll()` **不得自增**——旧写法在 `poll()` 里
   * 再自增一次，会覆盖 `reset()`/`openSong()` 在 `uploadSingAudio` await 期间的 bump
   * （`my === epoch` 成立）→ 迟到结果照写，"换歌/重置即作废"并没真正成立。
   * 会在飞请求作废的入口：`openSong()`（换歌）、`reset()`（关面板/再来一遍）、`retry()`。
   */
  let epoch = 0
  let pollAbort: AbortController | null = null

  const progressPct = computed(() => {
    const p = status.value?.progress
    if (!p || !p.total) return 0
    return Math.round((p.done_lines / p.total) * 100)
  })

  /** 收藏列表（收藏 tab：由用户自主选择，不再是难度等启发式过滤） */
  const favorites = computed(() => songs.value.filter((s) => s.favorited))

  function stop() {
    if (pollTimer) {
      clearTimeout(pollTimer)
      pollTimer = null
    }
    // P1-2：同时作废**在飞**的 status/result 请求（只清定时器挡不住已发出的那一个）
    pollAbort?.abort()
    pollAbort = null
  }

  async function loadSongs() {
    phase.value = 'loading'
    error.value = null
    await sing.loadSongs()
    // 列表真源在 store：把它的三态映射回本组合式的 phase/error ——
    // 视图侧判据（`phase==='loading'` 骨架、`phase==='failed'` 错误态）与既有测试断言一律不变。
    if (sing.songsStatus === 'failed') {
      phase.value = 'failed'
      error.value = sing.songsError
      return
    }
    phase.value = 'idle'
  }

  /** 选歌：详情 + 就绪门禁（40905 语义前置提示，不进入跟唱） */
  async function openSong(songId: number): Promise<boolean> {
    // P1-2/P1-5：换歌即作废旧轮询与在录录音——否则旧 attempt 的结果会写到新歌上
    stop()
    // 评审 R4：换歌也必须作废**在飞**的提交（只 abort 轮询挡不住 submitAudio 的 await——
    // 否则旧歌的上传落地后会写 status/phase 并在新歌页面上继续轮询旧 attempt）。
    epoch += 1
    recorder.cancel()
    // 评审 R3：换歌要清干净——`reset()` 清的 `status`/`result`/`phase` 这里同样要清，
    // 否则**报告态直接换歌**时旧报告仍挂在状态里（新歌标题下渲染旧成绩）。
    detail.value = null // 清旧详情：避免换歌瞬间旧标题/歌词/图表串台
    status.value = null
    result.value = null
    error.value = null
    phase.value = 'idle'
    try {
      detail.value = await fetchSongDetail(songId)
    } catch (e) {
      error.value = singErrorMessage(e)
      return false
    }
    if (detail.value.pitch_ref_status !== 'ready') {
      error.value = '参考旋律生成中或缺失（暂时不能跟唱）：等提取完成后刷新即可'
      return false
    }
    // 门禁通过才落选（2026-09-21）：顶栏/导航的选中高亮不会指向一首点不开的歌
    sing.selectSong(songId)
    phase.value = 'idle'
    return true
  }

  /**
   * 收藏切换（2026-09-10）：先乐观翻转列表态（点下去立刻有反馈），
   * 请求失败回滚成原状态并返回 null —— 不静默吞错，也不让失败的点击留下假状态；
   * 失败原因按 HTTP 状态映射进 `favoriteError`（404=后端未重建 / 401=登录过期 / 5xx=未迁移）。
   */
  async function toggleFavorite(songId: number): Promise<boolean | null> {
    const song = songs.value.find((s) => s.id === songId)
    if (!song) return null
    const before = song.favorited
    const next = !before
    song.favorited = next
    favoriteError.value = null
    if (detail.value?.id === songId) detail.value.favorited = next
    try {
      const r = await setSongFavorite(songId, next)
      song.favorited = r.favorited // 以后端返回为准（幂等语义下二者应一致）
      if (detail.value?.id === songId) detail.value.favorited = r.favorited
      return r.favorited
    } catch (e) {
      song.favorited = before
      if (detail.value?.id === songId) detail.value.favorited = before
      favoriteError.value = favoriteErrorMessage(e)
      return null
    }
  }

  function startRecording() {
    error.value = null
    paused.value = false
    void recorder.start(SING_MAX_RECORD_MS).catch((e) => {
      phase.value = 'failed'
      error.value = micErrorMessage(e)
    })
  }

  /** 暂停录音（录音态有效；暂停段不入音频、不计入时长——见 VoiceRecorder.pause） */
  function pauseRecording() {
    recorder.pause()
  }

  /** 继续录音（暂停态有效；按剩余额度重挂自动停止定时器） */
  function resumeRecording() {
    recorder.resume()
  }

  function stopRecording() {
    recorder.stop()
  }

  function cancelRecording() {
    recorder.cancel()
  }

  function getLiveStream(): MediaStream | null {
    return recorder.liveStream
  }

  async function submitAudio(blob: Blob) {
    if (!detail.value) return
    stop()
    // 评审 R4：本轮的**唯一**一次自增——提交 + 它引发的整轮轮询共用这个世代；
    // 期间任何换歌/重置/重试都会再自增 → 下面每个 await 之后都要重新校验。
    const my = ++epoch
    phase.value = 'uploading'
    try {
      const sess = await createSingSession(detail.value.id)
      if (my !== epoch) return // 期间换歌/重置：不写 sessionId，也不提交
      sessionId = sess.id
      const submitted = await uploadSingAudio(sessionId, blob)
      if (my !== epoch) return // 期间换歌/重置：丢弃迟到回执（不写 attemptId/status/phase）
      attemptId = submitted.attempt_id
      // 受理回执只有 {attempt_id, status}（无 progress）；补一条本地 queued 快照，
      // 让 `status` 的类型与实际字段一致（P1-14：旧的手写 DTO 声称 ack 带 progress，
      // 运行时其实是 undefined → 进度条靠 `progressPct` 的兜底才没崩）
      status.value = {
        attempt_id: submitted.attempt_id,
        status: 'queued',
        progress: { done_lines: 0, total: 0 },
        code: null,
        error: null,
      }
      phase.value = 'processing'
      poll(my) // 沿用同一世代（poll 内部不再自增）
    } catch (e) {
      if (my !== epoch) return // 世代失效（含 abort 引发的异常）：不作为失败上报
      phase.value = 'failed'
      error.value = singErrorMessage(e)
    }
  }

  /** 轮询一次（递归续期）。`generation` 由调用方给出，**本函数不自增世代**（见 `epoch` 注释）。 */
  function poll(generation: number = epoch) {
    stop()
    const my = generation
    pollTimer = setTimeout(async () => {
      pollAbort = new AbortController()
      const signal = pollAbort.signal
      try {
        const s = await fetchSingStatus(attemptId, signal)
        // P1-2：世代校验——期间发生过换歌/重置/重试 → 本次结果一律丢弃（不写任何状态）
        if (my !== epoch) return
        status.value = s
        if (s.status === 'done') {
          const r = await fetchSingResult(attemptId, signal)
          if (my !== epoch) return
          result.value = r
          phase.value = 'done'
          // 埋点（docs/53 P1）：唱吧评分完成 → score_event；整首完成（is_complete）→ practice_complete
          void track('score_event', {
            targetType: 'song',
            songId: r.song_id,
            payload: { overall: r.overall ?? undefined, is_complete: r.is_complete },
          })
          if (r.is_complete) {
            void track('practice_complete', {
              targetType: 'song',
              songId: r.song_id,
              payload: { kind: 'sing' },
            })
          }
          return
        }
        if (s.status === 'failed') {
          phase.value = 'failed'
          // P0-5：优先按后端回带的 code 映射（50003/50002），message 仅作兜底
          error.value = singFailureMessage(s)
          return
        }
        poll(my) // 续期沿用同一世代
      } catch (e) {
        if (my !== epoch) return // 世代失效（含 abort 引发的异常）：不作为失败上报
        phase.value = 'failed'
        error.value = singErrorMessage(e)
      }
    }, 1500)
  }

  function reset() {
    stop()
    epoch += 1 // P1-2：作废在飞轮询
    // 关闭跟唱面板 / 预览页「再来一遍」：**必须同时取消在录的录音**（2026-09-10 BUG 修复）。
    // 旧实现只清状态，录音会被遗弃在后台：① 麦克风一直采集到 ≤180s 自动停（面板已关，无 UI 可停）；
    // ② recorder 仍占着 state='recording' → 之后点「开始跟唱」被 start() 的同态守卫静默吞掉
    // （界面毫无反应），而旧录音到点后 onStop 会带着**新歌**的 detail 上传 → 旧音频按新歌评分。
    recorder.cancel()
    detail.value = null
    status.value = null
    result.value = null
    error.value = null
    phase.value = 'idle'
  }

  function retry() {
    stop()
    epoch += 1 // P1-2：作废在飞轮询
    recorder.cancel() // 错误态复位同样收尾，杜绝「上一次录音还活着」
    error.value = null
    phase.value = 'idle'
  }

  onUnmounted(() => {
    stop()
    recorder.cancel()
  })

  return {
    songs,
    detail,
    phase,
    error,
    status,
    result,
    progressPct,
    loadSongs,
    openSong,
    toggleFavorite,
    favorites,
    favoriteError,
    submitAudio,
    startRecording,
    stopRecording,
    pauseRecording,
    resumeRecording,
    paused,
    cancelRecording,
    getLiveStream,
    retry,
    reset,
    stop,
  }
}

/** 60s 内无任务进展的友好提示文案（轮询超时场景，前端兜底） */
export const SING_POLL_HINT = '评分计算中...（约 10~30 秒，长歌约 1 分钟）'
