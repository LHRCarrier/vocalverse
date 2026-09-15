/**
 * 运营域 DTO：内容上下架与工单（docs/50 §6.1 / §10.2、docs/06 §9.6）。
 *
 * ⚠️ 内容行**不是一个形状**。权威来源：`console/content/ConsoleContentController` 的四个
 * record（`SongRow` / `MaterialRow` / `ScenarioRow` / `QuestionRow`）+ `PublishView`，
 * 以及 `console/content/PublishService.PublishResult`。
 *
 * v1 用**单个** `ContentRow {id,title,status,meta,updatedAt}` 覆盖四个域，而后端返回四种形状、
 * 且**没有** `meta` 字段 —— 于是内容页的「元数据」列在运行时恒为空（`row.meta ?? '—'` 永远走 `—`）。
 * 本版按域拆开，页面直接读真实字段。
 */

// ── 运营（内容上下架） ───────────────────────────────────────────────────

export type PublishStatus = 'draft' | 'published' | 'archived'

/** 上下架内容域（`PublishService.DOMAIN_*`）：题库无 draft 故无 publish（docs/50 §4.2） */
export type PublishDomain = 'song' | 'listening' | 'scenario'

/** 上架流水按目标类型过滤（`ConsoleContentController.publishEvents` 的 `targetType` 正则） */
export type PublishTargetType = 'song' | 'listening_material' | 'scenario' | 'book' | 'chapter'

/**
 * 四个内容域的**公共可读字段**。
 *
 * 只放后端确实都有的三个字段：题库的题干是 `prompt` 而不是 `title`（`QuestionRow`），
 * 所以标题列由各域的列定义自己提供 —— 这里刻意不放 `title`，避免再造一个"看着能用、取到 undefined"的字段。
 */
export interface ContentRowBase {
  id: number
  status: PublishStatus | string
  updatedAt: string
}

/** `ConsoleContentController.SongRow`（`GET /content/songs`） */
export interface SongRow extends ContentRowBase {
  title: string
  artist: string | null
  level: number | null
  audioUrl: string | null
  /** 参考旋律状态：`missing|building|ready|invalid`；上架前置校验要求 `ready` */
  pitchRefStatus: string | null
}

/** `ConsoleContentController.MaterialRow`（`GET /content/listening-materials`） */
export interface MaterialRow extends ContentRowBase {
  title: string
  level: number | null
  audioUrl: string | null
  /** 服务端算好的布尔位（`transcript != null && !isBlank`），不是原文 */
  hasTranscript: boolean | null
}

/** `ConsoleContentController.ScenarioRow`（`GET /content/scenarios`） */
export interface ScenarioRow extends ContentRowBase {
  title: string
  sceneType: string | null
  difficulty: number | null
  /** `PublishService.countCorpusItems`：按 `English|中文` 逐行计数（与 Python 解析同口径） */
  corpusItemCount: number
}

/** `ConsoleContentController.QuestionRow`（`GET /content/questions`，只读） */
export interface QuestionRow extends ContentRowBase {
  examRevision: number | null
  itemIndex: number | null
  kind: string | null
  prompt: string | null
}

/**
 * 上架校验失败项（46011 的 `data.violations[]`）。
 * 权威：`PublishService.Violation(field, code, message)` —— v1 写成 `{field, reason}`，
 * 于是字段级原因在弹窗里恒为 `undefined`（会显示成「· lrc：undefined」）。
 */
export interface PublishViolation {
  field: string
  code: string
  message: string
}

/** `ConsoleContentController.PublishView`（`POST /content/{domain}/{id}/publish` 的 data） */
export interface PublishResult {
  domain: string
  id: number
  prevStatus: string | null
  nextStatus: string
  publishedAt: string
}

/**
 * 上架流水一行（`GET /content/publish-events`）。
 *
 * ⚠️ 该端点的 data 不是 record 而是 `LinkedHashMap`（`ConsoleContentController.publishEvents`
 * 明确列出键名），且**没有** `domain` / `prevStatus` / `nextStatus`：
 * - 内容域由 `action`（`content.{domain}.publish`）推导 —— 与后端 `applyPublish` 的写法一致；
 * - 前后状态只存在于 `detail`（`AdminAuditLogEntity.detail` 的原始 JSON 文本）里，故需解析。
 * v1 的 `adminUsername` 真实字段名是 `operator`；时间列是 `createdAt`（后端**没有** `publishedAt`）。
 */
export interface PublishEventRow {
  id: number
  /** 形如 `content.song.publish` */
  action: string
  targetType: string
  targetId: string
  /** 操作人账号名（`admin_audit_logs.admin_username` 快照） */
  operator: string
  adminUserId: number | null
  summary: string | null
  /** 未解析的 JSON 文本；前后状态经 `publishEventDetail()` 取 */
  detail: string | null
  createdAt: string
}

/** 工单状态机（docs/06 §9.6）：open → processing → resolved → closed，**禁回退**、closed 终态 */
export type TicketStatus = 'open' | 'processing' | 'resolved' | 'closed'

/** 工单类型：反馈 / 报错 / 内容纠误（content_correction 时才有 targetType/targetId） */
export type TicketKind = 'feedback' | 'bug' | 'content_correction'

// ── Python 写方：书籍 / 章节 / 媒体（`/api/v1/console/library/**`） ────────
// 权威：`services/python/app/console/api/routes/library.py` 的
// `_book_view`(:285) / `_chapter_view`(:298) / `_media_view`(:311)。
// 书籍与媒体由 Python 服务写（单写方矩阵），故字段名同为 snake_case。

export type BookLevel = 'L1' | 'L2' | 'L3' | 'L4'

/** 书籍列表行（library.py:285-295） */
export interface LibraryBookRow {
  id: number
  title: string
  author: string
  level: BookLevel
  status: PublishStatus
  /** 书的**全部**章节数（seed 派生计数）——列表响应**没有**"已上架章节数" */
  chapter_count: number
  word_count: number
  updated_at: string | null
}

/** 章节行（library.py:298-308） */
export interface LibraryChapterRow {
  id: number
  book_id: number
  chapter_no: number
  title: string
  status: PublishStatus
  word_count: number
  char_count: number
  updated_at: string | null
}

/** 媒体类型：`image|video|avatar`（models/media.py:62 的 CHECK；**没有 audio**） */
export type MediaKind = 'image' | 'video' | 'avatar'
/** 媒体状态（models/media.py:65 的 CHECK） */
export type MediaStatus = 'ready' | 'hidden' | 'deleted'

/**
 * 媒体行（library.py:311-322）。
 * ⚠️ 后端**不返回** `width`/`height`/`duration_s`（DB 里有列，但 `_media_view` 未投影），
 * 因此尺寸与时长在控制台无数据可显示，页面不得再读它们。
 */
export interface MediaAssetRow {
  /** 后端把 public_id 同时塞进 id 与 public_id（library.py:313-314） */
  id: string
  public_id: string
  owner_id: number
  kind: MediaKind
  mime_type: string
  size_bytes: number
  status: MediaStatus
  /** 公共读取地址 `"/api/v1/media/{public_id}"`（隐藏后该端点即读不到） */
  url: string
  created_at: string | null
}

// ── 内容写入（运营的增改删） ─────────────────────────────────────────────
//
// 权威：`console/content/ConsoleContentWriteController` 的六个 record 与四个 `xView`。
// ⚠️ 两个容易踩的形状差异：
// 1. **列表行 ≠ 可编辑实体**。`GET /content/songs` 的 `SongRowList` 只有 6 个字段，
//    而表单要的 `durationS`/`bpm`/`musicalKey`/`lrcUrl`/`coverUrl` 只在**单条读取**
//    （`GET /content/songs/{id}` 的 `songView`）里才有 —— 所以编辑弹窗必须按 id 回读，
//    不能拿列表行凑（那会把没显示的字段清空）。
// 2. **更新是 PUT 而不是 PATCH**，且请求体是**全量** `xUpsert`：漏字段 = 服务端按
//    `applySong` 的默认值覆盖（`interestTags→"[]"`、`source→public_domain`、
//    `status→draft`、`pitchRefStatus→missing`）。因此表单必须把 status 显式回填，
//    否则"编辑一次歌曲"会把已上架的歌曲悄悄打回草稿。

/** 内容审核态（`PublishService.STATUS_*`）；题库的取值域只有 publish/archive 两态 */
export type ContentStatus = 'draft' | 'published' | 'archived'

/** 歌曲版权来源（`SongUpsert.source` 的 `@Pattern`） */
export type SongSource = 'public_domain' | 'original' | 'demo_only'

/** 参考旋律状态（`SongEntity.pitchRefStatus`，Python 离线任务写、Java 只读） */
export type PitchRefStatus = 'missing' | 'building' | 'ready' | 'invalid'

/** 场景类型（`ScenarioUpsert.sceneType` 的 `@Pattern`，是**封闭**取值域，不是自由文本） */
export type SceneType = 'cafe' | 'airport' | 'interview' | 'library' | 'other'

/** 题目类型（`QuestionUpsert.kind` 的 `@Pattern`）：read = 朗读题、qa = 问答题 */
export type QuestionKind = 'read' | 'qa'

/**
 * 歌曲**单条**视图（`ConsoleContentWriteController.songView`）。
 * 与列表 `SongRowList` 是两个形状 —— 这里刻意不复用，避免"取到 undefined 还以为是空值"。
 */
export interface SongDetail extends ContentRowBase {
  title: string
  artist: string | null
  level: number | null
  durationS: number | null
  bpm: number | null
  musicalKey: string | null
  audioUrl: string | null
  lrcUrl: string | null
  coverUrl: string | null
  interestTags: string | null
  source: string | null
  pitchRefStatus: string | null
}

/** 场景单条视图（`scenarioView`） */
export interface ScenarioDetail extends ContentRowBase {
  title: string
  sceneType: string | null
  difficulty: number | null
  description: string | null
  systemPrompt: string | null
  openingLine: string | null
  targetCorpus: string | null
  interestTags: string | null
  promptVersion: number | null
  estimatedTurns: number | null
  estimatedMinutes: number | null
}

/** 听力素材单条视图（`materialView`）；注意这里**有** transcript 原文（列表行只有布尔位） */
export interface MaterialDetail extends ContentRowBase {
  title: string
  level: number | null
  audioUrl: string | null
  durationS: number | null
  transcript: string | null
  interestTags: string | null
  source: string | null
  license: string | null
}

/** 题目单条视图（`questionView`） */
export interface QuestionDetail extends ContentRowBase {
  examRevision: number
  itemIndex: number
  kind: string
  prompt: string
  referenceAnswer: string | null
}

/**
 * LRC 单行（`GET|PUT /content/songs/{id}/lrc` 的元素）。
 * `seq` 由服务端按请求数组顺序重排（`replaceLrc`），前端**不回传** seq。
 */
export interface LrcLineRow {
  seq: number
  offsetMs: number
  endOffsetMs: number | null
  lineText: string
  /** 继承 `songs.source`（docs/11 Q-B19 冗余一致性），前端只读 */
  source: string | null
}

/** LRC 行写入体（`ConsoleContentWriteController.LrcLine`） */
export interface LrcLineInput {
  offsetMs: number
  endOffsetMs: number | null
  lineText: string
}

/** LRC 整首重写体（`LrcUpsert`） */
export interface LrcUpsert {
  lines: LrcLineInput[]
}

/** 歌曲写入体（`SongUpsert`）。`pitchRefStatus` 不在前端表单里，见 `contentFormPayload` 的说明。 */
export interface SongUpsert {
  title: string
  artist: string | null
  level: number
  durationS: number | null
  bpm: number | null
  musicalKey: string | null
  audioUrl: string
  lrcUrl: string | null
  coverUrl: string | null
  interestTags: string | null
  source: SongSource | null
  status: ContentStatus | null
}

/** 场景写入体（`ScenarioUpsert`） */
export interface ScenarioUpsert {
  title: string
  sceneType: SceneType
  difficulty: number
  description: string | null
  systemPrompt: string
  openingLine: string
  targetCorpus: string | null
  interestTags: string | null
  promptVersion: number | null
  estimatedTurns: number | null
  estimatedMinutes: number | null
  status: ContentStatus | null
}

/** 听力素材写入体（`MaterialUpsert`） */
export interface MaterialUpsert {
  title: string
  level: number
  audioUrl: string
  durationS: number | null
  transcript: string | null
  interestTags: string | null
  source: SongSource | null
  license: string | null
  status: ContentStatus | null
}

/** 题目**新建**体（`QuestionUpsert`）：版本号与序号只在新建时可定 */
export interface QuestionUpsert {
  examRevision: number
  itemIndex: number
  kind: QuestionKind
  prompt: string
  referenceAnswer: string | null
  status: 'published' | 'archived' | null
}

/**
 * 题目**编辑**体（`QuestionPatch`，`PUT /content/questions/{id}`）。
 *
 * ⚠️ 后端**不允许**改 `examRevision`/`itemIndex` —— 它们是题目身份（docs/10 §3.2：
 * 改题=新版本，不改历史）。所以编辑表单里这两项只读回显。
 */
export interface QuestionPatch {
  prompt: string
  referenceAnswer: string | null
  status: 'published' | 'archived' | null
}

/**
 * 工单行。
 * ⚠️ 字段与 Java `TicketView` 逐字对齐（`services/java/.../ticket/dto/TicketView.java`）——
 * v1 的 `{id,userId,kind,status,subject,...}` 是**臆造**的（没有 `subject`，有 `title`/`content`/`adminReply`），
 * 这类"看着合理但后端没有"的字段会让页面在运行时静默空白。
 */
export interface TicketRow {
  id: number
  userId: number
  kind: TicketKind | string
  targetType: string | null
  targetId: number | null
  title: string | null
  content: string
  status: TicketStatus | string
  adminId: number | null
  adminReply: string | null
  resolvedAt: string | null
  createdAt: string
  updatedAt: string
}
