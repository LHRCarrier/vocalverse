# 52 · 酒馆跑团（TRPG）实施设计

> 状态：**已实施（2026-09-21）**。来源：组长拍板「全量迁移 ai4u 的酒馆游戏板块，替代 VocalVerse 原来的学英语场景板块」，
> 四个已定口径（见 §1.2）。**本文是酒馆域的权威设计**；`docs/14`（M2 场景对话规格）中与该域冲突的部分自动失效（见 §9 退役说明）。
>
> 执行人：LHRCarrier（AI 代工），2026-09-21。

## 1. 背景与范围

### 1.1 背景

- ai4u（同人协作 Agent 桌面应用）中的「酒馆」= **TRPG 跑团模块**：单 DM（主持人）+ 事实表/快照/校验「三件套」+ SSE 流式 + 主持台；
- VocalVerse 原「学英语场景对话」= 8 套预置场景 + 覆盖度/语料 + 三维评分 + 教练笔记（docs/14）；
- 迁移目标：**用酒馆（TRPG）替代「场景对话」这一闭环**，让对话练习从「题卡式」变成「持续世界 + 自由行动」的玩法。

### 1.2 已定口径（2026-09-21 组长确认）

| 事项 | 结论 |
|---|---|
| 替换边界 | **只换「场景对话」闭环**：`/m/chat` 场景对话 + 桌面 `/practice` + 8 套 scenario 内容 + 覆盖度/语料链路；保留打卡/报告/生词/书房/发音/社区足迹/自由说 |
| 端与语音 | **移动端优先（`/m/*`）+ 接 TTS/ASR**：DM 回复逐句 TTS，玩家可按住说话（ASR） |
| 后端落地 | **新建 trpg 域 + 新表**（不挂 sessions/scenario_messages）；完整移植三件套 + 提取/校验/骰子 |
| 老模块处置 | **彻底删除并同步文档契约**（前端页面/后端 dialog 链路/Java 管理端场景 CRUD/seed 场景/派生分析链路） |

## 2. 总体架构

```
App（/m/tavern）  ── POST /api/v1/trpg/campaigns/{id}/turns（multipart text|audio）──▶  Python FastAPI
   │  ▲                                                                                    │
   │  │  SSE：trpg_ready / user_transcript / text_delta / status / audio_chunk /           │
   │  │        system(open|scene|dice) / turn_end / error                                   │
   │  │                                                                                     ▼
   │  └── 逐句播放（GET /api/v1/audio/tts/{name}，复用练习域音频管道）                app/trpg/*
   │                                                                        ┌──────────────┴──────────────┐
   主持台（底部抽屉）── 面板/桌骰 REST ───────────────────────────────────▶ │ service（DM 门面）           │
                                                                           │  ├ state（唯一写入口）        │
                                                                           │  ├ turn（工具循环）→ DeepSeek │
                                                                           │  ├ extractor（每 2 回合）     │
                                                                           │  ├ facts/dice/snapshot/verify │
                                                                           │  └ prompts/events             │
                                                                           └──────────────┬──────────────┘
                                                                                          ▼
                                                              trpg_* 7 张表（Python 写；迁移 0018）
```

## 3. 数据模型（迁移 0018，7 张表；0019 扩场景卡/偏好见 §12）

| 表 | 说明 | 关键列 |
|---|---|---|
| `trpg_campaigns` | 剧本实例（用户私有） | user_id / name(60) / narrative_summary / last_active_at |
| `trpg_facts` | 剧情事实表（**唯一 upsert 锚点 `(campaign_id, fact_key)`**） | kind(state/fact) / fact_key(80) / value(200) / modality(fact/claim/rumor) / speaker / importance / version / user_touched_at / **user_deleted_at（墓碑）** |
| `trpg_tasks` | 任务行 | title / status(active/done/failed) / scene / last_mentioned_at |
| `trpg_clues` | 线索行 | title / content / scene / found / recovered / last_mentioned_at |
| `trpg_entities` | 实体注册表（唯一键 `(campaign_id, kind, name)`） | kind(npc/pc/task/clue/scene) / status(active/pending/cleared) / pending |
| `trpg_events` | 事件日志（append-only） | round / summary(300) |
| `trpg_messages` | 对话流水 + 系统卡 | role(user/assistant) / kind(text/system) / content / payload(JSONB) / meta / usage / audio_url |

明细表对 `trpg_campaigns` CASCADE；`user_id` 对 `users` RESTRICT（与 sessions 同口径）。
**与 ai4u 的差异**：ai4u 是单用户桌面应用（无 user 归属、无 conversation 表）；VocalVerse 版所有表按 campaign 归属用户，
且**不复制 ai4u 的 conversation 抽象**（一个剧本 = 一条连续对话流，历史即 `trpg_messages`）。

## 4. 接口契约（Python，`/api/v1/trpg`，14 op）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/campaigns` | 我的剧本列表（last_active_at 倒序） |
| POST | `/campaigns` | 新建剧本 `{name?}` |
| GET | `/campaigns/{id}` | 全量状态：campaign + messages + facts/tasks/clues/entities/events + snapshot + verify |
| DELETE | `/campaigns/{id}/messages` | 重开本剧本（清空对话，事实/任务/线索保留） |
| POST | `/campaigns/{id}/turns` | **回合主入口（SSE）**：multipart `text` / `audio` 至少其一 |
| POST | `/campaigns/{id}/facts/edit` · `/facts/delete` · `/facts/restore` | 主持台事实手改（置 userTouched）/ 墓碑删除 / 恢复 |
| POST | `/campaigns/{id}/tasks` · `/tasks/{taskId}/status` | 建任务 / 改状态（同步 `quest.*.status` 事实） |
| POST | `/campaigns/{id}/clues` · `/clues/{clueId}/recover` | 建线索 / 标记回收（回收后不再进快照） |
| POST | `/campaigns/{id}/scene` | 切场景（写 `scene.current`） |
| POST | `/campaigns/{id}/roll` | 桌骰：系统判定 + 落表 + 事件日志 |
| POST | `/campaigns/{id}/narrative/refresh` | 重新渲染叙事摘要（状态模板，零 LLM） |

- 归属：所有端点先校验 campaign 属于当前用户，越权 → `404/40401`（不泄露存在性）；
- 限流：`turns` 扣 `llm` 桶（带音频再扣 `asr`）；预检（归属/时长/入参）通过后才扣（审计 R-06 口径）；
- 错误码：`47001`（422 入参非法：名称/key/场景名/骰子/缺输入/语音过长）、`47002`（503 酒馆 AI 未配置，fail-fast）。

### 4.1 SSE 协议（前端手写镜像 `apps/web/src/audio/trpg-sse-types.ts`）

| type | 字段 | 时机 |
|---|---|---|
| `trpg_ready` | campaign_id / campaign_name / is_first | 流开始（对齐剧本与首回合语义） |
| `system` | trpg_sys=open\|scene\|dice / payload | 开场卡 / 过场卡 / 判定卡（**同时落库**，刷新不丢） |
| `user_transcript` | text / audio_url / words | 语音轮 ASR 回显（打字轮不下发） |
| `text_delta` | text | DM 正文增量 |
| `status` | stage=rolling\|scene | 工具执行中 |
| `turn_end` | message_id / usage | DM 消息已落库 |
| `audio_chunk` | url / duration | DM 回复逐句 TTS（前端排队播放） |
| `error` | code / recoverable | 流内错误 |

序列化复用 `app/practice/events.py` 的 `sse_payload` 与 `heartbeat_stream`（心跳 `: ping` ≤15s）。
**未复用练习域 9 类事件**（那套带 turn_index/评分语义且被 dialog/defense/shadow/free-chat 四方共用、golden 语料锁定）。

## 5. 三件套（迁移自 ai4u，逐条保留）

1. **事实表**（`app/trpg/facts.py` 纯函数 + `state.py` 唯一写入口）
   - key 两级白名单：域 `pc|scene|rel|quest|clue` × 属性（hp/location/inventory/current/attitude/trust/status/found）；
   - 写权限矩阵：LLM 写 State 域拒（`llm-state`）、墓碑拒（`tombstone`）、用户手改拒（`user-touched`）、未注册实体 → 注册 pending 懒确认；
   - 用户路径（主持台）不受矩阵限制：手改置 `user_touched_at`、删除写墓碑（防提取复活）、恢复清墓碑。
2. **状态快照**（`snapshot.py`，纯函数，每回合注入）
   - State 一行式（HP/位置/持有 + 场景）+ 活动任务全量 + 完成/失败折叠计数 + 线索（当前场景/未回收/上限 8）+ 关系子集（importance 降序/上限 6）。
3. **防遗忘校验**（`verify.py`，纯函数）
   - 静态悬空（任务 active 超 2 天 / 线索未回收超 2 天）→ 落差（标题前缀未被摘要承接）→【待记住】补丁注入 DM prompt；
   - 矛盾检测（反向词表）→ 标记摘要需以事实表为准重写。
   - **较 ai4u 的改进**：叙事摘要从「仅手动刷新」改为**每回合自动增量渲染**（状态模板渲染，零 LLM 成本）。

## 6. DM 回合与工具循环

- **工具**（`tools.py`）：`roll_dice`（骰面 2-1000/骰数 1-10/|调整值|≤50/effects 仅 pc|scene 域；系统判定并先落表再回文本）、`set_scene`（显式切场景）；
- **循环**（`turn.py`）：最多 2 轮可调工具 + 最后 1 轮 `tool_choice=none` 强制正文；工具轮 max_tokens 4096 / 正文轮 1200；工具文本回填后继续生成；
- **LLM 能力**：`DeepSeekLLMClient.stream_with_tools`（流式工具调用，事件 `delta|tool_calls|usage`）+ Fake 同形桩；
- **上下文**（`service.py::_build_dm_context`）：DM system 人设（NPC 台词「名：……」一行一句协议）→ 叙事摘要 → 快照 →【待记住】补丁 → 最近 8 条 **kind=text** 历史（修复 ai4u 系统卡空 assistant 混入 prompt 的缺陷）→ 本回合输入；
- **后台**：`extractor.py` 每 2 个玩家回合提取叙事事实（light 语义 / 最多 3 条 / usage 分账 `factExtract`）+ 待确认实体懒清理。

## 7. 前端（移动端真形态）

| 文件 | 职责 |
|---|---|
| `views/mobile/MobileTavernView.vue` | 页面编排（开局引导/状态带/消息流/输入 dock/剧本切换/主持台入口） |
| `components/mobile/trpg/TrpgStageHeader.vue` | 状态带（氛围四色条/HP/位置/持有/任务数/悬空徽章/AI 状态点） |
| `components/mobile/trpg/TrpgMessageItem.vue` | 系统卡（open/scene/dice）+ 气泡；NPC 台词分人名段；**文本插值禁 v-html**（docs/13 §5） |
| `components/mobile/trpg/TrpgActionDock.vue` | 快捷行动芯片 + 文本 + 语音（≤30s） |
| `components/mobile/trpg/TrpgConsoleSheet.vue` | 主持台抽屉四 tab：状态/事实表/任务线索/桌骰 |
| `components/mobile/trpg/TrpgOnboarding.vue` | 开局引导（示例剧本「迷雾酒馆」/自建） |
| `composables/useTavernSession.ts` | 剧本装载/开局/SSE 回合/状态刷新（音频委托 useTavernAudio） |
| `composables/useTavernConsole.ts` | 主持台动作（手改/墓碑/任务线索/切场景/桌骰/摘要） |
| `composables/useTavernAudio.ts` | 单元素串行播音器 + 逐句音频队列 + 重听 |
| `api/trpg.ts` + `audio/trpg-sse-types.ts` | 14 端点封装 + SSE 类型镜像 |
| `styles/mobile-uic.css`（酒馆段） | `t-*` 样式（状态带/系统卡/主持台/开局引导） |

入口：底栏学习组「🍺 酒馆」（`/m/tavern`）与桌面导航「酒馆」；`/m/chat`、`/practice` 路由已删除。

## 8. 删除清单（老场景对话链路）

**Python**：`GET /scenarios`；`create_session` 的 dialog 分支与 `scenario_id` 入参；`orchestrator._dialog_turn` / `_persist_dialog_turn` / `_fallback_reply`；`practice/corpus.py`；`agent/runtime/context_builder.py`、`meta_executor.py`、`agent/domains/learner.py`；`api/routes/agent_lab.py`；`difficulty/batch.py` 与 `rules.scenario_prior`；`rec.recommend_scenes` 与 `type=scene` 推荐；`mastery` 句级 `user_corpus_mastery` 写入；`warmup` 场景预热与启动预热；`seed_scenarios` 与 `data/seed/scenarios.json`；`seed_recommend` 演示场景/场景难度；`config.agent_lab_enabled`。

**Java/管理端**：`ScenarioEntity`/`ScenarioRepository`；控制台场景 CRUD/上架/权限码（36→33，operator 16→13）；`validateScenario`；管理端 `ScenariosView`/`ScenarioFormModal`/`scenarioColumns` 与相关 API/测试。

**前端**：`MobileSpeakingView`/`PracticeView`/`PracticeHubView`/`ScenePickerSheet` 与测试、`/m/chat`、`/practice` 路由、`api/practice.ts` 场景段、事件 `corpus_hit` 生产点、`useP5Wave` 与 **p5 依赖**（包门禁改「p5 零残留」）、预览页 `AgentLabPreview`。

**保留（不做物理删除）**：
- 表 `scenarios` / `scenario_messages` / `sessions.kind=dialog` / `attempts.kind=dialog_speech` / `reports` 的 coverage·semantic 字段：**历史数据保留**，枚举取值不迁移（`models/base.py` 已标注「退役」）；
- 报告页/打卡页：保留（打卡口径见 §8.1）；`docs/14` 标注退役。
- Java 工单 `targetType=scene`（App 侧对象类型，与内容管理无关）保留。

### 8.1 打卡聚合口径修订

`_aggregate_day`（`app/practice/checkin.py`）：

- `practiceCount` = 当日酒馆回合数（`trpg_messages` role=user、kind=text，即玩家行动数）+ 当日已完成的其他类型会话数（影子/答辩/唱歌）；
- `overall/pron/gram/fluency` = 当日 attempts（任意 kind、overall 非空）最佳总分 + 最新子分（酒馆不产分，不影响打卡）；
- `turns` = 酒馆回合数 + 其他会话 turn_count；`durationS` = 其他会话时长合计。

## 9. 退役说明（旧文档）

- `docs/14-M2场景对话与答辩导师规格.md`：**场景对话部分退役**（答辩导师部分仍有效）；冲突以本文与 `docs/30`/`docs/42` 现行口径为准。
- `docs/06 §9.1` 埋点 `corpus_hit` 不再有新生产者；`scene_start`/`practice_complete` 仍由答辩/入学测试上报。
- `docs/13 §8` 预览工作流：**联调测试页强制项已撤销**（2026-09-21 组长拍板），酒馆直接在真页 `/m/tavern` 验收。
- `docs/21`/`docs/42`/`docs/10`/`README.md` 已同步本次改动。

## 10. 验证与门禁

- **Python**：`ruff check` / `ruff format --check` / `pytest -q`（含 `tests/test_trpg.py` **18 例**：三件套纯函数矩阵、裁决矩阵、骰子、快照、SSE 文本/语音/工具轮、归属越权、墓碑、报告口径）；
- **前端**：`pnpm lint && pnpm typecheck && pnpm test:run && pnpm build`（`MobileTavernView` 8 例 + 底栏断言更新）、`node scripts/check-bundle.mjs`（p5·echarts 零残留）；
- **契约**：`python-openapi.json`（81 op）与 `java-openapi.json` 重刷 + `pnpm gen:api`；CI 三步对账；
- **Java**：`mvn test`（179 例，`ContractSnapshotTest` 需快照刷新后绿）；管理端 `pnpm typecheck/test:run/lint`。


## 12. 场景卡与用户设置（2026-09-21 组长追加，同日实施）

> 需求原文：「按 mobile 页面惯例，设置管理里要能设置语言（中英切换）、语音开关、语音声音选择
> （前端先展示，后续功能）；管理端可以管理固定场景卡（供用户选择），也提供随机生成的选项
> （有合适的就上架给所有用户用），还能够让 LLM 根据用户输入的词汇随机生成场景（用户自己管理）」。

### 12.1 场景卡体系（开局模板）

**三种来源**（同表 `trpg_scenario_cards`，`owner_user_id` 区分归属）：

| 来源 | owner | 生成者 | 状态流 | 可见性 |
|---|---|---|---|---|
| 平台固定卡 | NULL | 管理端手工 + 「随机生成」草稿（LLM） | draft → published → archived | 上架后所有用户在开局引导可选 |
| 用户私有卡 | user_id | App 内「按关键词生成」（LLM）或手动新建 | 创建即可用；删除 = archived | 仅本人可见/管理 |

**字段**：`title(60)` / `summary(300)` / `language(zh|en)` / `tags(≤6)` / `scene(40)` /
`opening_line(600)` / `template(JSONB)` / `keywords(200, 生成输入留痕)` / `generated_by(llm|manual)`。
`template` 形如 `{pc_name, pc:{hp,location,inventory}, facts:[{key,value,modality,speaker}],
tasks:[...], clues:[{title,content,scene}]}`。

**服务端白名单收口**（LLM 输出不可信）：`normalize_card` 对 facts 的 key 做 `parse_key` +
`DOMAIN_PROPERTIES` 校验（非法条目静默丢弃）、长度截断、tags 去重、上限裁剪；**只有 title 必填**。

**开局语义**（`POST /api/v1/trpg/cards/{id}/start`）：建 campaign（name=title）→ 应用模板
（pc/facts 走 `upsert_facts(writer="system")`，不置 `userTouched`，任务/线索直接建行）→ 写 `scene.current`
→ 落**开场系统卡**（open）+ **开场叙述消息**（卡自带文本，不花 LLM）→ 首回合 `is_first=False`，
不会重复出开场卡。

**管理端**（Python 控制台：`/api/v1/console/trpg/cards/**`，admin SPA「运营 → 场景卡」）：

| 端点 | 权限码 | 说明 |
|---|---|---|
| `GET /` | `content:scenario:read` | 平台卡分页（仅 owner NULL；用户卡不属管理端内容） |
| `POST /` · `PUT /{id}` | `content:scenario:write` | 新建（草稿）/ 编辑 |
| `POST /{id}/publish` | `content:scenario:publish` | 上/下架/归档；上架校验失败 → **46011 + data.violations[]** |
| `POST /generate` | `content:scenario:write` | **随机生成草稿**（keywords 空 = 内置主题池轮换；不落库，人工修订后保存） |

RBAC 三码 `content:scenario:{read,write,publish}` 在 Java `PermissionCatalog` 登记（36 = 原 33 + 3），
**operator 角色持有**（Python 控制台端点已上线，不存在「有码无处可用」）。

**App 端点**（用户侧）：`GET /cards`（我的卡在前 + 平台已上架）、`POST /cards`、
`PUT /cards/{id}`、`DELETE /cards/{id}`（归档）、`POST /cards/generate`（扣 llm 桶；失败 47003）、
`POST /cards/{id}/start`。

### 12.2 用户设置（跨设备偏好）

`trpg_user_prefs`（user_id 唯一）：`lang(zh|en)` / `voice_enabled(bool)` / `voice_name(40, 预留)`。

| 端点 | 说明 |
|---|---|
| `GET /api/v1/trpg/preferences` | 未设置过返回默认（`lang=zh, voice_enabled=true, persisted=false`） |
| `PUT /api/v1/trpg/preferences` | 部分更新（只改传入字段）；lang 非 zh|en → 47001 |

**作用面**：
- `lang` **只切 DM 输出语言**（`build_dm_system_prompt` 追加语言指令；NPC 台词协议保持中文冒号以兼容前端分段）；
  界面文案不切换（全 App i18n 不在本期）；
- `voice_enabled=false` → 回合**服务端不再逐句 TTS**（省配额；前端也即时 flush 播放队列）；
- `voice_name` 暂时只读展示（音色少，选择器禁用，等音色库扩充后开放）。

**App 入口**（mobile 惯例：每页右上角放本页功能）：酒馆页右上角 `⚙️ 设置` + `⭐ 场景卡` +
`📖 切换剧本` + `⚙ 主持台`（后两者仅游玩态）。
## 11. 已知欠账

1. **酒馆无评分/报告**：TRPG 不产发音分，报告页对酒馆无内容（打卡可计练习量）；
2. **TTS 上限**：单回合最多 10 句（`TTS_MAX_SENTENCES`），超长旁白只回文本；
   **音色选择未开放**（`voice_name` 字段与前端选择器已就位，仅禁用展示）；
   用户卡「编辑」只覆盖标题/场景/开场（模板 JSON 编辑在管理端，App 端后续按需补）；
3. **`recommend_shadow` 复习席**在候选不足时依赖 L−1 档 `material_difficulty` 行（本次已修 `_review_slots` 参数错位 bug，语义仍以 shadow 为主）；
4. **`scenarios` 表/管理端权限码的历史行**：RbacBootstrap 为 upsert-only，线上自定义角色残留的场景权限码为孤立行（不影响功能，如需清理走数据迁移）；
5. **酒馆埋点**：暂未新增事件类型（仅复用 `page_view`）；若需「回合数/剧本开卡数」看板，按 docs/06 §9.1 四处同步纪律新增。
