# 英文歌打分 · 系统集成拷问报告（轴线 D：离线提取管线与 Java 薄管理端边界）

> **拷问官**：系统集成拷问官（轴线 D）　**状态**：成稿（待组长/架构拍板项见 §3）
> **截止口径**：以代码实测 + 迁移为准，文档/代码冲突处以 docs/21 明确声明的「以代码为准」。
> **图例**：【事实】= 代码/迁移/文档原文已确认；【推断】= 依据现状推导的方案/取舍。

---

## 0. 拷问目标

在「Java 写主数据 / Python 写算法产物」的单写方纪律下，把**离线参考旋律提取管线**（`song_pitch_refs`）与 **Java 薄管理端**之间的边界拷问到没有再问的细节：音频从哪来、谁触发提取、状态怎么流转、任务要不要单独建表、薄管理端要补哪些最小端点、并发/幂等怎么守、合规红线在哪。逐一用代码 / 文档 / 网络（nightingale）核实，区分【事实】与【推断】。

---

## 1. 问题清单

| # | 主题 | 问题 |
|---|---|---|
| Q1 | 音频来源与耦合 | `songs.audio_url` 指向什么？谁收录/存储/上线？Python 离线提取能否直接拿到该音频？给出几种解耦方案及取舍 |
| Q2 | 提取触发时机 | 谁把 `pitch_ref_status` missing→building→ready？是 Python 轮询，还是 Java 调「触发端点」，还是消息/DB 作信号？ |
| Q3 | 重提取触发链 | LRC 整首重写→`song_pitch_refs` 级联删除→如何通知 Python 重提？extractor/version 怎么用？blake3 缓存复用 nightingale 吗？失败回滚？ |
| Q4 | 提取任务状态 | 任务要不要单独一张表 / Redis 键？`pitch_ref_status` 够吗？building/失败→invalid 的语义？跟唱/评分请求在「生成中/缺词」时返回什么错误码？ |
| Q5 | 薄管理端最小集 | Java 到底提供什么（保持薄）？给出「最小增补端点清单」及其边界（Java 不做评分/提取/算法）。 |
| Q6 | 幂等 / 并发 | 同歌多次触发、并发重提取、提取中再改 LRC、失败重试策略怎么定？ |
| Q7 | 合规 | 商用音乐严禁入库；离线提取需下载音频、是否本地处理；人声分离产物（stems）的版权/存储怎么处理？ |

---

## 2. 逐问 Q/A

### Q1 · 音频来源与 Java↔Python 最大耦合点

**【事实】`songs.audio_url` 只是 Java 写入的一个 URL 字符串，没有任何「收录/上传/对象存储」机制。**

- `SongEntity.audio_url` 为 `@Column(nullable=false, length=512)`（`services/java/.../content/SongEntity.java:46-47`）；`SongUpsert.audioUrl` 为 `@NotBlank @Size(max=512)`（`ContentAdminController.java:92`）。即：管理端创建歌曲时**由管理员手工填入一个 URL 字符串**，Java 只把它原样入库，既不校验可下载性，也不做对象存储。
- Java 端 **没有** 任何上传端点（`services/java` 下无 Upload/Multipart 控制器）；`docker-compose.yml:82-108` 中 java-api **不挂任何音频卷**（无 `volumes`），而 python-api 只挂 `./data/audio:/app/data/audio`（`docker-compose.yml:52`）——该卷是**用户录音/评分结果**的存储（`config.py:70` `audio_dir="./data/audio"`，仅 Python 使用），不是歌曲母带库。
- seed 不写入歌曲：`app/db/seed.py` 只 seed `scenarios` 与 `placement_questions`（`seed.py:23-29`），**无 `Song`/`Lrc`**（grep `Song|audio_url|lrc` 零命中）。因此 `songs`/`lrc` 只能靠 Java 管理端接口人工录入。
- docs 声称的引导脚本**不存在**：`docs/06 §9.7:179` 与 `docs/07:312` 都提到「`scripts/setup-assets.ps1` 从授权源下载模型 + 内置公有领域歌曲」，但仓库内**没有**该脚本（`scripts/` 下只有 bootstrap/dev/refresh-openapi + poc/healthcheck），`scripts/poc/*.mp3` 只是语音管线样例，非歌曲库。→ 歌曲音频「如何进入系统」在现状下**完全未定义**。

**【事实】Python 有能力下载 URL、并已具备存字节到音频卷的设施。**

- Python 依赖 `httpx`（`pyproject.toml:16`），现有用途是 LLM/ISE/Java 内部 REST（`app/audio/llm.py`、`ise.py`、`placement.py:179`），可复用 `httpx.AsyncClient` 对 `audio_url` 做 `GET`。
- `save_audio_bytes(data)`（`app/practice/orchestrator.py:63-74`）会把字节写进 `settings.audio_dir` 并生成带前缀文件名，返回 URL 字符串；因此「下载远端音频到本地卷再处理」的技术管线是现成的。
- 注意：`app/audio/base.py` 只有 `ASRClient/TTSClient/ScorerClient/LLMClient` 四个 ABC（`base.py:46-89`），**没有**「歌曲母带获取 / 人声分离 / 音高提取」的端口抽象；`save_audio_bytes` 是**具体实现直接写死在 orchestrator**（docs/19 §7 已点名「对象存储抽象只留接口未抽，`AudioStore` 是 P2-1 预留」）。

**【推断】解耦方案与取舍（本轴线最大耦合点）**

| 方案 | 做法 | 优点 | 代价/风险 |
|---|---|---|---|
| **A. 共享音频卷（推荐，最贴合现状）** | 把歌曲母带 mp3 放进 `./data/audio`（或新卷），Java 管理端在上传/选曲时写 `audio_url = /api/v1/audio/{file}` 或卷内相对路径；Python 直接从卷读 | 本地、无外网、下载即文件读，稳定可靠；符合「本地处理不对外传输」的合规口径；与 `docs/08:203`「demo 用本地卷共享」一致 | 需新增「管理端上传接口 + 1 个只写文件卷」；Java 目前没挂卷、没上传端点（要补）；多容器同卷是 P2-1 才定的 `AudioStore` 抽象 |
| **B. Python 直连 `audio_url`** | 复用 `httpx` 下载 URL（外链或对象存储签名 URL）再处理 | 实现最轻，几乎零新基建；适合公有领域外链 | 依赖外网可达 + 无鉴权；内容可能外泄/受控性差；与「本地处理不传输」合规不契合；URL 失效即提取失败（缺 offline 缓存与重试） |
| **C. Java 内部 REST 供字节** | 新增 `GET /internal/songs/{id}/audio`，Python 按需拉取 | 单一入口、能带服务令牌、可控 | **违反架构**：Java 严禁进入音频热路径/带宽（docs/20 §3.1 Java「明确不做语音/LLM」）；每次提取都要 Java 流式搬文件，边界反了 |
| **D. 种子脚本物化到卷** | 实现 `scripts/setup-assets.*` 把 3~5 首公有领域歌下载进共享卷，`audio_url` 指向卷内 / 服务 URL | 与 docs/07 Q47 / §9.7 口径完全对齐；可复现 | 脚本目前缺失；仍要一个「卷内→可下载 URL」的映射（谁提供静态/受控访问） |

**结论**：Q1 属**未决**。现网只有「Java 存 URL 字符串」这一事实，没有配套存储；**必须先拍板音频收录与共享方式**，否则提取管线无从落地。推荐 **A（共享卷）+ D（Setup 脚本物化公有领域素材）** 组合，保留 `AudioStore` 端口抽象（P2-1）以在 M3 之后不返工。

---

### Q2 · 提取触发时机与编排

**【事实】设计文档描述的是「Python 被动检测」，不是 Java 调触发端点。**

- `docs/10 §3.2-2:77-78`：「LRC 改动（Java 侧整首重写）→ 旧行级联删除 → **Python 离线任务检测缺失并重提取**」；`docs/20 §4.2-2:237` 同句「→ Python 离线检测重提取」。
- `docs/20 §3.2:182` 明确指出内部委托**仅一条** `POST /internal/level`，方向为 **Python→Java**；`docs/21 §2.3:102`「internal | /internal/level | Java | 仅 Python→Java；服务内网直连、不过网关」。

**【事实】没有任何「Java→Python」内部通道。**

- Python 侧 `/internal/**` 不需要服务令牌，也没写任何接收内部触发的端点（`app/api/routes/` 只有 audio/defense/events/health/placement/practice；`main.py` 不含 `internal` 路由）。
- 双向服务令牌只配在 Java（`SecurityConfig.ServiceTokenFilter` 只匹配 `/internal/**`，`SecurityConfig.java:87`）。所以「Java 主动调 Python 触发端点」需要**新建反向内部 REST + 给 Python 配受保护端点 + 独立共享密钥**，属于全新设施。

**【推断】推荐方案：Python 定时/增量轮询为主，Java 触发视为可选优化。**

1. **主方案（现状断言 + 被动）**：一个 Python 后台任务周期扫描 `songs where pitch_ref_status='missing' or 'invalid' and status='published' and exists(lrc)`，对每首「原子抢占」后进 `anyio.to_thread` 载荷提取。理由：
   - 与 `docs/10/20` 已拍板口径「Python 离线检测重提取」完全一致，**零新增跨服务通道**；
   - `uvicorn --workers 1`（`docs/06 §8`）+ 内存 ≥2GB（compose `mem_limit:2g`），单进程轮询天然规避多实例竞争；
   - 重提取/触发天然幂等：无论多少次 LRC 改动，最终都收敛到「抓到 missing 就重跑」；
   - 失败后可重扫，无需协调者。
2. **可选触发端点（降延迟）**：若希望「管理端点 LRC 后即刻起跑」，新增 **Java→Python** 内部 REST（如 `POST /api/v1/internal/pitch-ref/reanalyze`）作为「投喂加速器」，但**不能依赖它作为唯一触发**——因为跨服务通道会把单写方/编排耦合到 Java 侧，且 Java 也不该知道提取任务内部实现。触发端点只负责「热启动」，可靠性仍由轮询兜底。

> ⚠️ 触发者选择的**关键约束**：无论谁触发，`pitch_ref_status` 这一列都触发一个**跨写方**问题——见 Q4/§3-阻塞1。

---

### Q3 · 重提取触发链 / extractor·version / blake3 / 失败回滚

**【事实】LRC 整首重写 → `song_pitch_refs` 级联删除，由 DB FK 自动完成。**

- `replaceLrc`（`ContentAdminController.java:328-355`）是 `@Transactional`：`lrcs.deleteBySongId(id)` → 按 seq 1..n 重插 → 若原 `pitchRefStatus=="ready"` 置回 `missing`。`song_pitch_refs` 的删除不写 Java 代码，靠 0001 迁移的 FK（`fk_song_pitch_refs_lrc_id_lrc ON DELETE CASCADE`，`0001_initial_schema.py:894-896`）在 DB 层级联。

**【事实】「通知 Python 重提」目前只是 `pitch_ref_status=missing` 这一隐式信号，没有主动调用。**

- `replaceLrc` 注释写「触发 Python 离线重提取」（`ContentAdminController.java:348`），但代码**没有任何**对 Python 的 RPC/HTTP，也没有写 Redis；纯粹靠把状态置为 `missing`，等待 Q2 的轮询。

**【事实】extractor/version 语义。**

- `song_pitch_refs.extractor` 默认 `'pyin'`（`content.py:236-238`、`0001:884-886`），`version` `VARCHAR(16) NOT NULL` **无服务端默认**（`0001:887`）——Python 写入时必须显式给 `version`（算法参数/版本号，如 `pyin@1.0`）。
- `docs/10 §4.2:143`：「extractor(默认 pyin)/version（算法可追溯，同曲重提取后旧分数可解释）」。用途 = 算法升级或 pyin 参数变更后，用 `version` 区分新旧标定，复现/解释旧 `sing_attempts` 分数。

**【事实】`sing_attempts.lines` 无 `ref_seq`/`no_ref` 列（与 docs/11 Q-B10 的完整建议不符）。**

- `SingAttempt.lines` JSONB 结构注释只列 `{seq, start_ms, end_ms, pitch_score, rhythm_score, pron_score, synced, skipped}`（`practice.py:193`），**没有** docs/11 Q-B10 建议的 `ref_seq`（指向评分时 lrc seq）与 `no_ref`（缺参考句布尔）；`sing_attempts.lrc_id` 为 **SET NULL**（`practice.py:210-212`、`0001:847`）。影响：LRC 整首重写后旧 `lrc_id` 置空，历史评分只能靠 `lines[].seq` 快照锚定新 LRC 的 seq，**无法精确回溯**「评价的是哪一版 lrc」→ 建议补 `ref_seq`/`no_ref`（P1 级）。

**【推断】blake3 缓存：可直接复用 nightingale 的「按源哈希失效」思路，但必须扩展为「音频 + LRC」双因子。**

- nightingale（github.com/rzru/nightingale）实测：「Analysis results are cached using **blake3 file hashes**. Re-analysis only happens if the **source file changes**, the user triggers it **manually**, or you choose to **shift key/tempo** and create playback variants.」并由 UVR Karaoke/Demucs 人声分离 + WhisperX 对齐构成离线参考。
- 映射到 VocalVerse：参考旋律取决于 **① 音频母带**（音高内容）**② LRC 句窗口**（`start_ms/end_ms`，逐句切分的依据）。因此缓存键应为 `blake3(audio 字节 + LRC 行表)`，而**不只是 audio**——否则改 LRC（时间轴）不会失效。
- 失效条件自然对应三类：**源变了**（`audio_url` 变 / LRC 重写）、**手动重算**（Q5 的触发端点）、**变调/变键**（改 `musical_key` 或未来「变调练唱」→ 视为 version 升级/重新标定）。
- `version` 字段正是用来承载「算法/参数升级」这一失效维度的：boost `version`（或 `extractor`）→ 旧 `song_pitch_refs` 判失效 → 重提（对应 nightingale 的「变键变调」）。

**【推断】失败回滚语义。**

- 提取失败应把 `pitch_ref_status` 置 `invalid`（而不是停在 `building` 造成「永远生成中」）；`invalid` 之后管理端可手动重触发（Q5），或轮询任务按规定重试 N 次后落 `invalid`。**现状没有 `invalid` 的自动恢复路径**，只有人工。

---

### Q4 · 提取任务状态 / 错误码

**【事实】没有任务表，也没有任务相关的 Redis 键；`pitch_ref_status` 是唯一状态。**

- 0001/0002 迁移里没有任何 `song_pitch_jobs`/`extraction_tasks` 表；`app/models` 也没有对应模型；`config.py`/`redis_client.py` 没有为「提取任务」定义的键。`docs/06 §8:121` 说的「唱歌/长音频评分走 **Redis 任务状态轮询** 异步化」是 `sing_attempts` 评分侧（M3 必项），**没有延伸到离线提取任务**。
- `pitch_ref_status` CHECK 限定 `missing/building/ready/invalid`（`0001:279-282`、`content.py:164-180`、`PitchRefStatus` enum `base.py:137-141`）。

**【事实】进度/失败细节无载体**：`building` 只表示「在跑」，没有 progress、error 快照、耗时；排查「卡在 building」只能靠日志。这不符合可观测诉求。

**【事实】Java 管理端可被客户端直接改 `pitch_ref_status`（弱化就绪门禁）。**

- `createSong` 与 `updateSong` 都会采用请求里的 `pitchRefStatus`（`ContentAdminController.java:273`、`305-307`）。即管理员可通过 PUT `/songs/{id}` **把状态写成 `ready`/`building`**，绕过真实提取 → `ready` 门禁可被伪造。应改为：**管理端写入时忽略/禁改该列**，只由提取流程或「触发端点」翻转。

**【事实】错误码表没有「参考旋律未就绪」类目。**

- `docs/api/error-codes.md` 现有 40001/40002/40101/40301/40401/40901/40902/40903/41001/41301/42201/42202/42901/50001/50301/50302。其中 **40401 = 资源不存在**、**40902 = 会话状态不允许该动作**、**40903 = stale turn**。**没有**「歌曲参考旋律生成中/缺词/参考旋律无效」的码。

**【推断】该返回什么错误码（需要新增）。**

- 跟唱/评分请求在 `pitch_ref_status != 'ready'` 时应返回明确、可区分的前端提示，不能静默算分（`docs/11 Q-B11:144` 已定「遇 status!='ready' 返回「参考旋律生成中」而非静默算分」）。
- **推荐新增一个 409 族码**：`40904`（409）「参考旋律未就绪（生成中/缺失/无效）」，并**先登记 `docs/api/error-codes.md` 再用**（AGENTS「新增错误码先在 docs/api/error-codes.md 登记」）。不建议复用 40401（那是 404「资源不存在」，语义是找不到资源而非「存在但未就绪」）；也不建议复用 40902（那是「会话状态机不允许该动作」，语义偏调度而非内容未就绪）。
- 建议把 `500/400` 与 `40904` 区隔：**network/算法侧失败**是 5xx，**「歌曲本身未就绪而无法打分」**是 40904 业务语义，前端据此提示「稍后重试」而非「系统故障」。

**【推断】是否单独建任务表 / Redis 键**：建议**建一张轻量任务表**（`pitch_extract_jobs`：`id, song_id, lrc_epoch(或 lrc 行快照hash), extractor, version, status(pending/running/success/failed), attempt, last_error, started_at, finished_at`），**仅 Python 写**（归属 Python 才不与歌曲表单写方冲突）。理由：① `pitch_ref_status` 只有 4 态，无法表达 `failed` 与重试计数；② 进度/错误/耗时可观测；③ 天然支持幂等去重与并发（同一 `song_id` 同 `lrc_epoch` 只跑一次）。`songs.pitch_ref_status` 保留作「读侧快速就绪门禁」，真正任务详情进任务表。若坚持不建表，则退化为「Redis 键 `pitch_job:{song_id}` 存任务态（TTL 短）」，但这只是状态旁路，丢失历史。

---

### Q5 · 「薄管理端」最小增补端点清单及其边界

**【事实】Java 现状只有内容 CRUD，无任何「重提取/查看提取状态」端点。**

- `docs/21 §2.2` Java 端点清单里歌曲域只有 `GET/POST /songs`、`GET/PUT/DELETE /songs/{id}`、`GET/PUT /songs/{id}/lrc`；**没有** trigger/reanalyze/status 端点。`docs/20 §3.1` 明确 Java「明确不做」= 语音/SSE/LLM 热路径、指标口径公式、DDL、刷新后写 Python 表。

**【推断】薄管理端最小增补清单（保持薄：只做「编排触发 + 状态/结果只读」）。**

| # | 端点（服务原生，经网关 `/manage/`） | 作用 | 边界（Java 不做） |
|---|---|---|---|
| 1 | `POST /api/v1/admin/songs/{id}/pitch-ref/reanalyze` | 管理员主动「重提取」：置 `pitch_ref_status=missing`（若 `ready|invalid|missing`）+（可选）热启动已实现的 Python 触发；**幂等**（重复调用无害） | 不做提取、不解析音频 |
| 2 | `GET /api/v1/admin/songs/{id}/pitch-ref/status` | 读 `pitch_ref_status` + 关联任务（若建任务表则读 `pitch_extract_jobs` 最新一条：status/attempt/error） | 不算任何指标；只读映射 |
| 3 | `GET /api/v1/admin/songs/{id}/scoreboard`（只读、可选） | 每首歌 best 成绩 / 榜单（`sing_attempts` 按 `overall_score` 降序取 top-N） | 「排序取 top」是查询而非口径公式（R4 允许）；口径分数由 Python 写，Java 只 SELECT |
| 4 | `GET /api/v1/admin/songs/{id}/scores`（只读） | 列出该歌所有跟唱评分 | 同上只读 |

**边界钉牢**（对每个新增端点）：Java **不触发也不消费**任何语音/LLM/评分；不计算音准/节奏/发音；不写 `sing_attempts`（Python 独占）；不把 `pitch_ref_status` 暴露为可被客户端直接改的输入（见 Q4）。

**必须修正的既有问题**：`createSong`/`updateSong` 目前允许请求体直接设 `pitchRefStatus`（`ContentAdminController.java:273,305-307`），应**改为忽略该字段**或仅允许在「触发端点」里由系统翻转，否则就绪门禁可被伪造。

---

### Q6 · 幂等 / 并发

**【事实】`songs` 无乐观锁**：`SongEntity` 无 `@Version`、无 `@Lock`（grep 命中仅 `ScenarioEntity.prompt_version` 是业务字段）。`replaceLrc` 用 `@Transactional`（`ContentAdminController.java:329`），`lrc` 的 `(song_id, seq)` 唯一（`0001:361`），`song_pitch_refs.lrc_id` 唯一（`0001:898`）。

**【事实】`uvicorn --workers 1`**（`docs/06 §8`，`Dockerfile` 已声明）→ Python 提取任务在**单个进程**内跑，天然避免「多 worker 抢同一首歌」；但单进程意味着**一个卡死的任务会让整个服务阻塞/停摆**（docs/19:115 已点名「没有第二个进程兜底，一个坏音频文件可让整个服务停摆」）。

**【推断】幂等/并发对策。**

1. **同歌重复触发**：触发端点只做「置 missing + 可选热启动」，本身幂等；提取任务的去重靠「原子抢占」——Worker 用 `UPDATE songs SET pitch_ref_status='building' WHERE id=:id AND pitch_ref_status IN ('missing','invalid')`（条件更新），只抢到 true 的那次才跑，抢到 false 即已有人在跑。`lrc_id` UNIQUE 兜底（同句不重复插入）。
2. **并发重提取（同歌多实例/跨进程）**：单 worker 基本消除；若未来扩到多副本，需把「抢占」改为「DB 条件更新」而非内存判断，`song_pitch_refs` 以 `lrc_id` UNIQUE + upsert（`ON CONFLICT (lrc_id) DO UPDATE`）保证幂等。
3. **提取中再次改 LRC（竞态，高危）**：现状 `replaceLrc` **只在原状态==ready 时**才置回 missing（`ContentAdminController.java:349`）。若歌曲处于 `building` 时改了 LRC，状态保持 `building`，但旧 `song_pitch_refs` 已被级联删除——**在跑任务会给「已被删除的旧 lrc_id」写 `song_pitch_refs` → FK 违约 / 或读到的就是新 lrc**，都可能错乱。
   - **对策**：`replaceLrc` 应**无论当前状态一律置 `missing`**（不只 ready），并把「原状态、lrc 快照(epoch/行hash)」喂给提取任务做「世代校验」；Worker 在提交前重读 `lrc`，若 `lrc_epoch` 与开跑时不一致则**放弃本次、重排队**。用「lrc 世代（epoch）」当并发版本号，替代缺失的 `@Version`。
4. **失败重试**：建议「自动重试 ≤N 次（如 3，指数退避）→ 落 `invalid`」；`invalid` 后不再自动重试，由管理员手动 `reanalyze`（Q5-1）。重试计数存任务表（Q4 推断）。

---

### Q7 · 合规

**【事实】商用音乐严禁入库。**

- `songs.source` CHECK 限定 `public_domain|original|demo_only`（`content.py:156-157`、`0001:283-285`）；`docs/06 §9.7:179`「demo 用公有领域/自创曲目（童谣、民歌），流行曲目仅答辩说明思路、不随仓库分发」。`docs/19 商业可行性与合规风险:340-350,422` 进一步列红线和答辩口径（只公有领域 + 授权曲库）。

**【事实】原始音频被 `.gitignore` 整体屏蔽**（`*.wav/*.mp3/*.lrc` + `data/` `models/`），公开仓库 clone 下来「无模型无歌」（`docs/07:310`）。因此歌曲音频**不能随仓库分发**，必须走「本地卷 + Setup 脚本物化」或外链。而 `scripts/setup-assets.ps1` 现状缺失（见 Q1）。

**【推断】合规处理。**

- **下载即本地处理**：离线提取应把 `audio_url` 的音频拉取到**本地临时文件**用 ffmpeg/sox 处理（人声分离 + 音高提取），**不对外二次传输**；处理完即删临时源音频（或按 24h 惰性过期，与 `docs/06 §9.7` 一致）。`AudioStore` 端口（P2-1）将来落到 S3/MinIO 时同样只做「内部读写」。
- **人声分离产物（stems）**：UVR/Demucs 分离出的 vocals/instrumental 是**母带的衍生音频**，涉及录音制作者邻接权；**不应持久化入库**。VocalVerse 只存 `song_pitch_refs.pitch_ref` 的 **`{"f0s":[...], "notes":[...]}` 元数据**（音高序列，非音频波形），这是可复用但**非音频复制**的算法产物，版权风险低。结论：**stems 用完即删，仅落音高序列元数据**。若确需缓存 stems 提速（nightingale 确实缓存 stems），仅限「公有领域/自创」且加 TTL/可清；`song_pitch_refs` 里不要存音频。
- **nightingale 授权**：其 README 标注 **GPL-3.0-or-later**。VocalVerse **参考其设计/思路（UVR+WhisperX+blake3 缓存+变调失效）是可接受的**，但**不得直接拷贝其代码**（拷入即受 GPL 传染，与项目「不引重量级许可」冲突）。答辩口径照 `docs/19:343`：只做公有领域示例 + 表述为「可扩展内容库架构能力」。
- **合规红线清单**：入库严禁 `*.mp3/*.wav/*.lrc`、原始音频、商用音乐、模型权重、真实用户数据；密钥只走 `.env`（`.env.example` 占位符与 compose 回退一致）。

---

## 3. 未决缺口清单（阻塞 / 需拍板）

| # | 缺口 | 为什么重要 | 建议 | 级别 |
|---|---|---|---|---|
| **G1（阻塞）** | **`pitch_ref_status` 写方冲突**：`songs` 表 Java 独占（单写方矩阵 docs/10 §3.1），但 docs/11 Q-B11 设计与 `SongEntity / `songs.pitch_ref_status` 翻转都默认「Python 离线任务翻转」。而 M-1（docs/20 §4.4，随 0003 落地）会给 `vv_python` **只授 `songs` 的 SELECT**——Python 将**物理无法 UPDATE `songs.pitch_ref_status`**（DB 42501）。 | 这是轴线 D 成败命门：若状态列写不了，整个「missing→building→ready」状态机与就绪门禁都悬空。 | 三选一：① **把状态列迁到 Python 拥有的表**（如 `song_pitch_jobs.status`/`song_pitch_status`，推荐，彻底解耦单写方）；② 新增 **Java 内部端点** `POST /internal/pitch-ref-status` 让 Python 委托 Java 写（还原有 `/internal/level` 模式）；③ 给 `vv_python` 专门授权 songs 状态列（破单写方，需明确豁免）。 | 🔴 阻塞 |
| **G2（阻塞）** | **歌曲音频收录/共享未定**：`audio_url` 只是 URL 字符串，无上传端点、无对象存储、无共享音频卷、Setup 脚本缺失（见 Q1）。 | Python 拿到不到音频就无法提取；学习者也无处播放母带。 | 拍板 Q1 方案 A/D；补管理端上传接口 + 挂共享卷；`AudioStore` 端口提前抽（P2-1）。 | 🔴 阻塞 |
| **G3（需拍板）** | **`replaceLrc` 只在原状态==ready 时置 missing**（`ContentAdminController.java:349`）：building 时改 LRC 状态错乱；且客户端可通过 `createSong/updateSong` 直写 `pitchRefStatus`。 | 并发窗口会「卡在 building 无任务」或「伪造 ready」，直接破坏就绪门禁与评分正确性。 | ① LRC 重写**无条件**置 missing；② 管理端写入忽略该列；③ 引入 `lrc` 世代（epoch/行hash）做并发校验。 | 🟠 高 |
| **G4（需拍板）** | **无提取任务表**：`pitch_ref_status` 4 态表达不了 `failed`/重试计数/进度/错误；无任务可观测。 | 「卡 building 排查」只能靠日志；失败不能自动重试。 | 建 Python 独有的 `pitch_extract_jobs`（status/attempt/last_error/…），`songs.pitch_ref_status` 只作读侧快速门禁。 | 🟠 高 |
| **G5（需拍板）** | **错误码缺失**：无「参考旋律未就绪」类目。 | 跟唱请求在生成中/缺词/无效时无法给出明确前端提示；同 40401 会误报「不存在」。 | 新增 `40904`（或规格 409 族）「参考旋律未就绪，稍后重试」，**先登记 `docs/api/error-codes.md`**。 | 🟠 高 |
| **G6（需拍板）** | **`sing_attempts.lines` 无 `ref_seq`/`no_ref`**（`practice.py:193`），`lrc_id` SET NULL。 | LRC 重写后历史评分无法精确回溯「评的是哪版 lrc/哪句」。 | 补 `ref_seq`（指向评分时 lrc seq）与 `no_ref`（缺参考句）；`lrc_id` 保留 SET NULL。 | 🟡 中 |
| **G7（需澄清）** | **服务令牌头不统一**：设计文档（docs/06/10/20/21/envelope）写 `X-Service-Token`，**代码实测用 `Authorization: Bearer <service-token>`**（`placement.py:183`、`SecurityConfig.java:85-88`），docs/21:90 已注明「以代码为准」。 | 新增任何 Java→Python / 或复用内部 REST 时，若照抄文档头会 401。 | 统一成代码现状（Bearer），并回头修订 docs/06/10/20/envelope。 | 🟡 中 |
| **G8（需澄清）** | **跨服务字段名**：`/internal/level` 契约要求 camelCase `userId`（`InternalLevelController.LevelRequest`，`InternalLevelController.java:22`），但 Python `placement.py:182` 仍发 **`user_id`** → Jackson 无 SNAKE_CASE 策略，反序列化得 null → 400；Error 被 `except Exception` 静默吞（docs/21 §4 P0-6 仍复核在）。 | 是「内部契约命名」的活样板：任何新内部端点字段名必须用 camelCase。 | 修复 `placement.py` 发 `userId` + `raise_for_status`（0.5 人天），加契约测试。 | 🟡 中 |
| **G9（需拍板）** | **nightingale 复用边界**：其缓存/分离/对齐设计值得借鉴，但代码 GPL-3.0。 | 防止误引入 GPL 传染代码；答辩口径要能说清「参考而非拷贝」。 | 只借鉴思路（UVR/Karaoke+WhisperX+blake3+变调失效+session 复用分析器），不拷贝代码；保留 `version/extractor` 做算法溯源。 | 🟡 中 |

---

## 4. 结论

1. **耦合主线已澄清**：`audio_url` 是 Java 写入的 URL 字符串，无存储/收录机制；Python 有 `httpx`+`save_audio_bytes` 可下载并落盘，但无音频来源。**Q1 是最大解耦点，必须拍板共享卷（A）+ Setup 脚本物化公有领域素材（D）**，并保留 `AudioStore` 抽象。
2. **触发编排**：设计文档是「Python 被动检测重提取」；推荐 **Python 轮询为主（扫描 missing/invalid + 有条件 UPDATE 抢占）**，无新增跨服务通道；Java 主动触发端点仅作提速可选。现有内部 REST 只有 Python→Java `/internal/level`，**没有 Java→Python 通道**。
3. **单写方是硬约束，且已被 M-1 角色**（vv_python 对 songs 只 SELECT）**推向物理不可写**：`pitch_ref_status` 的写方必须要么迁到 Python 持有的表，要么走 Java 内部 REST，要么明确豁免——这是最需要一拍板（G1）。这比 Q2 的「谁触发」更根本。
4. **状态机 4 态不够**：`building` 表达不了 failed/进度/重试；建议加 Python 独有 `pitch_extract_jobs`，`songs.pitch_ref_status` 只当读侧门禁；新增 409 族「参考旋律未就绪」错误码（先登记）。
5. **薄管理端**：补「重提取触发 + 提取状态/成绩只读」4 个端点即可，Java 绝不进语音/评分/提取热路径；须顺手修掉「管理端直写 pitchRefStatus」与「只在 ready 时置 missing」两个现状缺陷。
6. **并发/幂等**：靠「building 抢占 + lrc_id UNIQUE(upsert) + lrc 世代校验」；单 worker 缓解跨实例竞争，但单进程也有「坏文件拖垮全服务」风险（docs/19:115）。失败重试 ≤N 后落 invalid，人工重触发。
7. **合规**：商用音乐严禁入库为硬编码 CHECK；原始音频 gitignored 不得随库；离线提取只在本地处理、**stems 用完即删、只落音高序列元数据**（非音频复制）；nightingale 只借鉴不拷代码（GPL）。

> **一句话**：坐标轴 D 的最大难点不是「提取算法」，而是「**音频从哪来 + `pitch_ref_status` 这个 Java 拥有表上的列到底谁能写**」这两个边界，二者都必须在实现 M3 前排板，否则存在「离线产物无法落地 / 单写方与 M-1 冲突」的结构性风险。

（已核实来源：`services/java/.../content/ContentAdminController.java`、`SongEntity.java`、`LrcEntity.java`、`SongRepository/LrcRepository`、`SecurityConfig.java`、`InternalLevelController.java`、`application.yml`；`services/python/app/models/content.py`、`practice.py`、`base.py`、`core/config.py`、`db/seed.py`、`audio/base.py`、`alembic/versions/0001_initial_schema.py`、`0002_m2_practice.py`、`pyproject.toml`；`docs/06-技术框架决策.md §8/§9.4/§9.7/§10`、`docs/10-数据库设计.md §3.2/§4.2`、`docs/11-数据库拷问报告.md Q-B10/Q-B11`、`docs/20-系统架构设计说明书.md §2.1/§3.2/§4.4`、`docs/21-接口设计说明书.md §2.2/§4/§5`、`docs/07-需求拷问报告.md Q47`、`docs/19-架构与实现模式评审报告.md`、`docs/api/error-codes.md`、`docker-compose.yml`；网络核实 nightingale README：[github.com/rzru/nightingale](https://github.com/rzru/nightingale)。）
