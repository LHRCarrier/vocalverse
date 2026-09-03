# VocalVerse · 工作日志

> 团队可见的工作记录（入库）。负责维护：LHRCarrier（组长）；其他成员需补充时经 PR 追加到 `VocalVerse工作日志.md`。
> 用途：按日记录项目关键改动、验证结果与踩坑；新记录追加在最上方。正式决策看 `docs/06-技术框架决策.md`（ADR 唯一权威）。

## 2026-09-03 整合完善 · 修复 alembic 漂移 + C4/C6 建档→场景难度过滤

### schema 一致性（alembic check 零 diff）
- `app/models/skill.py`：`user_skill_state.user_id` 由 `unique=True`（生成 `uq_user_skill_state_user_id`）改为显式
  `UniqueConstraint("user_id", name="uq_user_skill_state_user")`，与 **0003 迁移**实际名对齐（DB 名
  `uq_user_skill_state_user`）→ 消除 `alembic check` 的"remove_constraint/add_constraint"漂移。
- 验证：`alembic check` → **No new upgrade operations detected**（此前仍报 `user_skill_state` 漂移）。

### C4/C6 建档→难度衔接
- `PracticeHubView.vue`：新增 `visibleScenes`（仅显示 `[L, L+1]` 档场景，L=入学档 `cefr_level`→难度映射）；
  无档则全部展示（顶部 NAlert 引导去入学测试）。把"入学档位"真正接入场景卡过滤（此前只当装饰）。

### 门禁
- Python 全量 `pytest -q` **155 passed**；`ruff check` + `ruff format --check` 全绿。
- 前端 `lint` / `typecheck` / `test:run`(18) / `build` 全绿。

—— 执行人：Faust-sudo

## 2026-09-03 阶段E落地 · 入学测试前端 UX（双模式 / 试音示范重录跳过 / 等级条 / 未定档引导 / 错误文案）

### 前端（apps/web）
| 项 | 落点 | 依据 |
|---|---|---|
| API 模块 | 新增 `src/api/placement.ts`：status/retest/skip/questions/scoreItem/finalize 封装（本地 interface 声明响应） | docs/06 §9.2；C1/C5/C8 |
| 错误文案映射 | 新增 `src/api/errorCopy.ts`：`ApiError.code → 中文`（40002/40302/40303/40910/42901/42902/42203…），未登记回退 `message(code N)` | docs/api/error-codes.md；docs/19 P0-6/P1-11 |
| PlacementView 双模式 | 重写：intro（试音 🎙+回听）/ 答题（🔊 听示范 TTS + 🎙 录音 + 重录一次 + 下一题 + QA 参考提示 + 跳过）/ 结果（两维 S + L1~L4 + 去练习/再测）；retest 模式经 `startRetest()` 触发 40302/42902 gate | C1/C5/C8；docs/19 §3.5 敢开口包 |
| 等级条 + 复测入口 + 未定档引导 | `PracticeHubView`：无 level → NAlert「去入学测试（可跳过）」CTA；有 level → 水平 NTag + 「重新测试」入口（status.can_retest）；用 `errorCopy` 消裸错误码 | docs/19 P1-1；C8 |

### 后端（skip 支撑 C5 跳过）
- 新增 `POST /api/v1/placement/skip`：无 completed → 建 **provisional** completed placement（level=L2、`details.skipped=True`）→ 使 `/sessions` 40303 门禁通过；幂等（已有 completed 返回现有）。
- `_latest_real_completed`（冷却 gate 用，**忽略 skipped**）——跳过后可立即实测定级（否则 skip 会触发 42902冷却）。

### 契约同步
- Python OpenAPI 快照重导出（新增 /skip）+ `pnpm gen:api` 前端类型；python-ci 校验 MATCH。

### 门禁
- Python 全量 `pytest -q` **155 passed**（placement 32，含 skip 3 用例）；`ruff check`+`format --check` 全绿。
- 前端 `lint` / `typecheck` / `test:run`(18 passed) / `build` 全绿（build 仅 chunk>500kB 告警，非错误）。

—— 执行人：Faust-sudo

## 2026-09-03 阶段D落地 · 入学测试断点修复（Java /internal/level 回写 + 前置 40303）

**最重要断点：定档回写链路（P0-6/C2/C9）真正跑通。**

| 项 | 落点 | 依据 |
|---|---|---|
| **D3 回调 payload 修复** | `placement.py:_callback_level`：键改 `userId`（原 `user_id` 致 400 被吞）+ `source='placement'` + `levelAt`；`raise_for_status()` + 失败**记日志告警**（不再静默）；不阻塞入学测试 | docs/19 P0-6；local/34 D-3；C2 |
| **D2 Java 幂等 PUT** | `InternalLevelController.LevelRequest` 加 `source/levelAt`；仅当 `levelAt` 不早于 `cefrLevelAt` 才落（旧数据不覆盖）；`source` 缺省 `placement` | local/34 D-2；C9 |
| **🔴 JwtAuthFilter 关键修复** | `/internal/**` 跳过 JWT 解析——否则 `Authorization: Bearer <service-token>` 被当 JWT 解析失败 → `clearContext()` 清掉 ServiceTokenFilter 的 ROLE_SERVICE → 403。这是回调不通的**深层根因**（非仅字段名） | SecurityConfig 过滤器链 |
| **D1 前置 40303** | `create_session`：`kind=DIALOG` 需已有 completed placement，否则 40303（C5 跳过会建 provisional 档，故凡有档位即可） | local/34 D-1 |

**契约同步（E-5，因变更了 Java LevelRequest 与 Python 端点而必须）**：重导出 `apps/web/src/api/specs/{python,java}-openapi.json` + `pnpm gen:api` 前端类型；`python-ci` 快照校验 MATCH、`ContractSnapshotTest` 通过、前端 `typecheck` 通过。
**错误码登记**：40302（复测未获准）、40303（未定档）、40910（并发 run）、42203（read 不足）→ `docs/api/error-codes.md`。
**新增测试**：`tests/placement/test_callback.py`（payload 键名 userId）、`InternalLevelControllerTest`（回写更新 + 幂等忽略旧数据 + 无 token 401）、`test_m2_core::test_dialog_session_requires_placement`（40303）。

**门禁**：Python 全量 `pytest -q` **152 passed**；`ruff check` + `ruff format --check` 全绿；Java `mvn test` **18 passed**（含新 InternalLevelControllerTest 3/3，ContractSnapshotTest 已对账）；前端 `typecheck` 通过。

—— 执行人：Faust-sudo

## 2026-09-03 阶段C落地 · 入学测试复测=重考（eligible 预检 / 冷却 / 幂等）

按冻结清单 C3t + C8（精简复测、无 XP 经验制）实现：

| 项 | 落点 | 依据 |
|---|---|---|
| 冷却 gate(42902) | `_get_or_create_run` 新建 run 前：若已有 completed 定档且距其 < `placement_retest_cooldown_days` → 42902 | local/34 C-3；防频繁刷分 |
| eligible 预检(40302) | `POST /api/v1/placement/retest`：无已完成基线 → 40302 | local/34 C-3 |
| 复测入口 | `POST /api/v1/placement/retest`：40302/42902 通过后建立 in_progress run + 返回题型快照+`exam_revision`（取当前发布版本） | C5/C11 |
| 资格预检 | `GET /api/v1/placement/status`：has_completed / completed_count / current_level / last_completed_at / can_retest / cooldown_remaining_days | local/34 C-5（精简） |
| 配置 | `placement_retest_cooldown_days=1`（config.py） | — |
| 语义 | latest completed placement 的 level = 当前档（`/status` 与回写按此）；复测生成新 completed 记录，`finalize` 幂等（B3）已复用 | C8 |

**错误码登记**：`40302`（复测未获准：尚无已完成测试）、`42902`（复测冷却中）→ `docs/api/error-codes.md`。
**门禁**：`pytest tests/placement/` 27 passed（+4 复测用例）；全量 `pytest -q` **149 passed**；`ruff check` + `ruff format --check` 全绿。
**待办（E-5 契约同步，需起服务）**：新增 `GET /placement/status`、`POST /placement/retest` 两端点 → 需 `scripts/refresh-openapi.ps1` 刷新 `apps/web/src/api/specs/python-openapi.json` 并 `pnpm gen:api`（本阶段未做，避免无服务跑出错误快照）。

—— 执行人：Faust-sudo

## 2026-09-03 阶段A完善 + 阶段B落地 · 入学测试 run 状态机 / QA 标签 / 幂等

### 阶段 A 完善
- 新增 `tests/placement/test_grammar.py`（8 用例）：`judge_grammar` / `judge_qa_answer` 快路径（合法 JSON→{grammar,relevance}）、fail-open（非 JSON/空转写→None）、score 钳制、relevance 白名单、`_extract_json` 边界；用 stub LLM + `asyncio.run`（不依赖 anyio 插件）。
- `placement.py:finalize` 加防御：`compute_s` 前校验 A/F 非空，缺任一 → 42203（不静默用部分数据判档）。

### 阶段 B
| 子任务 | 落点 | 依据 |
|---|---|---|
| B1 run 状态机 + 并发 | `_get_or_create_run`：评分首题惰性创建该用户 `in_progress` run（placements 行），后续题续用；`(user_id) WHERE status='in_progress'` 部分唯一索引兜底并发 → 40910 | local/34 B-1；docs/10 §6 B-2 |
| B2 QA 相关度标签 | `grammar.py` 新增 `judge_qa_answer`（一次 LLM 调用返 `{grammar, relevance}`）；qa 分支落 `details.qa.relevance`；删除旧 `QA_REF` | local/34 B-2；C1 语法仅诊断；local/16 控次数 |
| B3 finalize 幂等 | run 已 `completed` 直接返回缓存结果（不重复落库）；attempt 经 `placement_id` 作**消费标记**（不可被其他 placement 复用） | local/34 B-3；C9 |

### schema / 迁移
- `attempts.placement_id`（FK placements.id SET NULL）+ `ix_attempts_placement_id`（models/practice.py）。
- `placements` 部分唯一索引 `uq_placements_user_inprogress`（models/user.py）。
- 新增 `alembic/versions/0004_placement_run_state.py`（SQLite batch + PG partial index）。
- 错误码：登记 `40910`（已有进行中的考试）。

### 门禁
- `pytest tests/placement/` 23 passed；全量 `pytest -q` **145 passed**；`ruff check` + `ruff format --check` 全绿。
- 迁移：`alembic heads` 单头 `0004`；`alembic upgrade head --sql`（PG 离线编译）正确；**真 PG `alembic upgrade head` 已应用 0004**。
- ⚠️ `alembic check` 仍报一处**既有无关漂移**：`user_skill_state` 唯一约束名 DB=`uq_user_skill_state_user` vs 模型=`uq_user_skill_state_user_id`（来自 0003 推荐迁移），非本阶段引入，建议另开 PR 修复（不在 A/B 范围）。本阶段涉及的 `attempts.placement_id`、`placements` 部分索引**无漂移**。

—— 执行人：Faust-sudo

## 2026-09-03 阶段A落地 · 考试域两维评分与 gram 修复（C1/C5/C11）

按冻结任务清单（见下一条）实现阶段 A（P0）：两维综合分 + LLM 语法判定诊断 + config 单源。

| 子任务 | 落点 | 依据 |
|---|---|---|
| A1 可复用 LLM 语法判定 | 新增 `app/placement/grammar.py`（`judge_grammar(transcript, reference)` → `{score, errors[]}`；fail-open） | local/34 A-1；C1；docs/06 §9.3 |
| A2 评分通道分离 + gram 化 | `placement.py:score_item` — `kind='qa'` 只 ASR 不 ISE（不耗 ISE 桶）；read 走 ISE；read/qa 均补调 LLM 语法；`gram_score=None` 化 | C1；A2；docs/10 §4.3 不伪造分 |
| A3 finalize 两维公式 | `placement.py:finalize` — `S=0.6·A+0.4·F`，`A=mean(read pron)`、`F=0.7·mean(flu)+0.3·mean(completeness)`；`min_read_items=1` 齐句校验（不足→42203）；`placements.exam_revision` 从所考题库版本写入 | C1/C5/C11；local/24 v4 §2.1、local/26 §2 |
| A5 配置单源 | 新增 `Settings`：`score_w_accuracy/score_w_fluency/score_f_fluency/score_f_integrity/level_threshold_l4~l2/placement_min_read_items`；废弃硬编码 `_level_for` 常量 | C1；A5；C10 |
| 错误码 | 登记 `42203`（入学测试已评分 read 题不足）到 `docs/api/error-codes.md` | AGENTS.md 先登记后使用 |
| 模型 docstring | `models/user.py` Placement 注释改两维口径 | C1 |

**新增文件**：`app/placement/__init__.py`、`app/placement/scoring.py`（纯函数：`compute_accuracy/compute_fluency/compute_s/level_for`）、`app/placement/grammar.py`。
**新增测试**：`tests/placement/test_scoring.py`（公式/边界/completeness 缺失→仅 flu）、`tests/placement/test_placement_api.py`（qa 只 ASR、finalize 两维、42203、exam_revision 记录）。

**门禁**：`pytest tests/placement/` 13 passed；全量 `pytest -q` 135 passed；`ruff check` + `ruff format --check` 全绿。
（注：全量首跑 `test_save_audio_and_ownership` 偶发 410 vs 403，为该用例**顺序依赖 flake**（`./data/audio-test` 跨测试残留）、与本次改动无关，单跑与重跑均绿。）

**A4 阈值标定** 未含在本次代码（需 ≥3 人 × 每档数据 + σ 实测，= F2 交付物，算法/组长）。

—— 执行人：Faust-sudo

## 2026-09-03 入学测试功能 · 需求分歧澄清与任务清单冻结（C1~C11 决策合流）

**背景**：按「信息压缩 → 冲突澄清 → 任务拆解」推进入学测试功能。依据 docs/06 §9.2、docs/07、docs/10、docs/18、docs/20/21、docs/13/14/19，并核对 local/04~06 三份（需求规格/产品功能/成员分工 .docx）与推荐系统代码（`app/rec/service.py`、`app/rec/*`、local/26~31）。产出：开发词典、技术栈、冲突清单 → 逐项拍板 → 任务拆解表 + 分支命名 + ER 图。

**已固化的拍板决策**：

| 项 | 结论 |
|---|---|
| C1 | 考试域改**两维**，对齐推荐系统统一尺度：`S = 0.6·A + 0.4·F`，`A=mean(read pron)`、`F=0.7·mean(flu)+0.3·mean(integrity)`，档界 85/70/55；`kind='qa'` 只 ASR 不 ISE，**额外调 DeepSeek 判语法** → `gram_score`+错误类型进报告/教练反馈，**不进 S 权重**；DeepSeek 失效 → `gram_score=None`（禁静默 0）、QA fail-open、S 不变；权重/阈值进 `scoring_config` 单源 |
| C2 | 修 `_callback_level`：`user_id→userId` + `raise_for_status`+log + 双侧契约测试（Java `@SpringBootTest` + Python `respx`） |
| C3 | 推荐冷启动不落 `placement_level`，与水平预测目标错峰避循环（属 M3） |
| C4 | 难度衔接：场景筛选读 `cefr_level`（入学档）；`preferred_difficulty` 仅覆盖难度映射、不动 `cefr_level` |
| C5 | 入学测试「**可跳过 + 2 题迷你版**」：默认跳过发 L2 入门套；想定级的做 1 read + 1 QA，每题 🔊 示范 + 重录；QA 必须下发 `reference_answer`；`min_read_items=1` 齐句校验，A/F 对 read 题取均值 |
| C6 | 档位快照产物 = `placements`(completed) + `user_profiles.cefr_level`；难度衔接在 `/practice` 按档读卡 |
| C7 | DB 角色权限化（vv_python/vv_java/vv_seed）+ CI 静态探针，把单写方从约定变约束 |
| C8 | 定期复测=**精简版**：可重做入学测试（新 `placements(kind=upgrade)` → latest completed 回写 `cefr_level`，配 eligible 预检/冷却/幂等）；**不做** XP 经济 / `level_progress` / `xp_ledger`（与 `user_skill_state` 动态水平重复、控范围） |
| C9 | 档位对账：`cefr_level_source/cefr_level_at` + 幂等 PUT（level_at≤现值忽略）+ 读前对账 |
| C11 | `placements.exam_revision` 在 finalize 从所考题库版本写入，可追溯 |

（C10 公式/阈值集中 `scoring_config` 单源；C12 ISE 桶 60/h vs ADR 30/h 待评分子任务确认。）

**冻结任务清单**（阶段 A→F，按依赖）：

| 阶段 | 任务 | 端 | 决策 |
|---|---|---|---|
| A | A1 可复用 LLM 语法判定模块；A2 `score_item`（qa 只 ASR + 补调 LLM 语法，gram=None 化）；A3 `finalize` 两维公式 + `min_read_items=1`；A4 阈值标定；A5 配置单源 | Py/算法 | C1/C5/C10/C11 |
| B | B1 run 状态机 + 并发 40910；B2 QA 端点 ASR+LLM 标签；B3 `finalize` 幂等 + 乐观锁 + 消费标记 | Py | C1/C9 |
| C | C3t 复测=重考（预检 40302 / 冷却 42902 / latest completed 回写） | Py | C8 |
| D | D1 `POST /sessions` 未定档 40303；D2 Java `/internal/level` 修 `user_id→userId` + 幂等 PUT | Py+Java | C2/C9 |
| E | E1 `PlacementView` 双模式（试音/示范/重录/跳过/QA 参考）；E2 复测入口+等级条；E3 未定档强制跳+错误文案映射；E4 建档→/practice 难度衔接 | 前端 | C5/C8/C4/C6 |
| F | F1 pytest（两维公式/落位/幂等/QA fail-open/对账）；F2 阈值标定报告；F3 文档同步+worklog | 组长/算法 | C1/C9/C10/C12 |

**分支命名**：`feat/placement-scoring-2d`、`chore/placement-score-calibration`、`feat/placement-run-state-machine`、`feat/placement-qa-answer`、`feat/placement-retest`、`fix/placement-level-callback`、`feat/placement-gate`、`feat/placement-view-redesign`、`feat/placement-handoff`、`test/placement-e2e`、`chore/docs-sync`。

—— 执行人：Faust-sudo

## 2026-09-09 PR#25 推荐系统落地 · 复审整改与合入（模型同步 / 契约快照 / CI 兜底）

复审发现并修复 3 个阻断项（评审结论见 PR#25 review，2026-09-02）：
1. **模型-迁移不同步**：迁移 0003 已扩 `sessions.kind='shadow'`、新增 `sessions.shadow_material_id`、扩 `attempts.kind='shadow_speech'`，但 `models/practice.py` 未同步 → shadow 会话落库 CHECK 违约；`mastery/service.py` 读 `session.shadow_material_id` 抛 AttributeError 被收尾钩子吞掉（动态水平/掌握度静默不更新）。已补模型同步 + 2 条回归测试（`tests/mastery/test_session_model_sync.py`：修复前 2 failed，修复后绿）。
2. **合并冲突 + 契约快照未刷新**：worklog 与 main 后到 9/7~9/9 记录冲突（已合并解决；推荐系统 13 段记录按规范补署名）；`apps/web/src/api/specs/python-openapi.json` 缺 `/api/v1/recommendations`→ CI 契约步骤必红（已刷新快照 + `pnpm gen:api`）。
3. **CI 从未运行**：PR #24/#25 打开与同步推送均 0 run（`pull_request` 触发当前未生效）→ python-ci 增加 `workflow_dispatch` 手动触发 + `push(main)` 自动兜底；合入前本地全量门禁复核通过（ruff / format / pytest 83 passed / alembic 单头 / 契约一致）。

—— 执行人：LHRCarrier

## 2026-09-07 Java 启动日志两坑修复（安全密码 WARN + spring-boot:run 中文乱码）

用户实测暴露两个启动问题（commit `5ad2c8c` + `16a4e6b`）：

1. **「Using generated security password」WARN**：项目是自定义 JWT 过滤器 + BCrypt（AuthController 自己校验），从不创建 `UserDetailsService` bean → Boot 的 `UserDetailsServiceAutoConfiguration` 兜底生成随机密码并打误导性 WARN。已 `exclude UserDetailsServiceAutoConfiguration` 消噪（测试证明 SecurityConfig 一直生效：链路失效则 /auth/** 被默认 basic auth 拦截，AuthFlowTest 必挂）。
2. **DemoSeeder 中文乱码（verify 正常、spring-boot:run 乱码）**：logback sett UTF-8 字节后，**mvn spring-boot:run 的 fork 子进程 stdout 经管道由 Maven 主进程按平台编码（GBK）解码** → UTF-8 字节被读错乱码；surefire 转发路径无此环节所以 verify 正常。修复三层对齐：`logback-spring.xml charset=UTF-8` + `.mvn/jvm.config -Dfile.encoding=UTF-8`（Maven 主 JVM）+ `spring-boot-maven-plugin jvmArguments -Dstdout.encoding/-Dstderr.encoding=UTF-8`（fork 子 JVM）。Linux/容器无影响（本然 UTF-8）。
3. 门禁：`mvn clean verify` 全绿（15 tests + spotless + 契约对账）。

**踩坑（并入 32 待登记）**：Windows 中文编码是「字节流向 × 每层的解码器」问题——logback 只管字节（charset），Maven 管道转发按自己编码解码；修编码先分清「哪层转码」再动手，单改一层必然残留（第一轮只加 logback charset 时 verify 好了 run 没好的原因）。

## 2026-09-07 Java 包结构按 Package-by-Feature 规范重整（专家子代理审计 + 实施）

**触发**：组长检查发现上轮「Controller 统一收 controller/」后分层不明确（Controller 按层、Entity/Repository 按域 = 混合分层）。派专家子代理审计（35 主 + 9 测文件全量清单为输入，结论可复现）：

- **诊断**：① 混合分层割裂——同域端点被拆到无归属层包（工单 = controller/TicketController + ticket/ 两地）；② ContentAdmin/QuestionAdmin 同属 content、InternalLevelController 实属 user，包名表达不了域归属；③ SecurityConfig/JwtService/JwtAuthFilter 是全局安全编织却塞在 auth 域；④ 测试主/镜像不一致（PingController 主在 controller/、测试在 health/）；⑤ AbstractAdminApiTest 跨域共享却放层包。
- **方案（唯一推荐）**：Package by Feature——域内自包含（`域/controller/` 子包 + 域根 entity/repository），跨域安全/种子上移 `config/`、健康探针归 `health/`、共享视图 DTO 归 `ticket/dto/`；测试镜像到 `域/controller/` + `support/` 基座。豁免项：薄端无 service 层（唯 AuthController 的密码/refresh 逻辑越界已标记，后续可选抽 AuthService）、controller 内嵌 record DTO（跨端点复用的仅 TicketView 例外）。
- **实施**：`117beef`（主代码 13 移 + 测试 4 移，git 识别 rename 90~100%）+ `28b5448`（测试镜像 import 同步）。**外部可见性零变化**：@RequestMapping 与内嵌 record 字段未动，`ContractSnapshotTest` 逐字通过（springdoc tag/operationId 不依赖包路径），前端契约/类型无需刷新。
- **门禁**：`mvn clean verify` 全绿（15 tests + spotless + 契约对账）。

**踩坑 31（实施自伤，已恢复）**：第一轮用 PowerShell `[regex]::Replace(..., "package $pkg;")` 替换 package 行——`.NET 正则替换的 replacement 中 `$pkg` 被解释为命名组引用`，导致整个文件被静默置换破坏（实测表现为源码字符错乱）→ 全量 `git checkout` 回滚后改用 `git mv` + **字面 `.Replace`（无 `$` 语法）** + 每步 `Contains` 校验，一次通过。教训：**批量改文本用字面替换 + 校验；正则 replacement 的 `$` 是陷阱**；另 `git mv` 会立刻 staged，别再用 `git add` 分批攒 commit（本次导致测试 rename 混入主代码 commit，无功能影响但分类不纯）。

## 2026-09-07 系统设计 Day1：架构设计说明书 + 接口设计说明书（docs/20、docs/21）

### 任务与产出

按分工（09/07，A 全天）：系统架构设计（分层、服务边界、写方唯一性约束、数据流图）+ 接口契约梳理（OpenAPI）。产出《系统设计说明书》两份分册（09/09 设计评审交付）：

| 交付物 | 文件 | 要点 |
|---|---|---|
| 架构分册 | `docs/20-系统架构设计说明书.md` | 系统上下文 DFD（mermaid）+ 五层划分 + 应用内三层端分层（route/service/port/adapter + 禁止规则 R1~R6）+ 服务职责边界表（含「新功能落位判据」）+ **表级单写方矩阵**（19 表 × 写方 × 现状代码）+ **守护机制设计 M-1~M-4**（DB 双角色 vv_python/vv_java/vv_seed、CI 静态探针、seed 只增不改 + slug 键、评审打回）+ 回合目标态时序图 + 报表流 + 写方边界图 + **D1~D14 设计决策/现状差异/排期表** |
| 接口分册 | `docs/21-接口设计说明书.md` | 双快照对账：Python 20 ops / Java 6 ops 端点总清单（方法/路径/鉴权/限流/备注）+ SSE 回合契约（事件序列）+ **内部 REST 契约正式登记**（`POST /internal/level`：userId 键名/3s/幂等/调用方义务/双侧契约测试）+ 整改项 **R-1~R-16** 登记表 + 错误码对账 + 契约变更流程 |
| 错误码补登记 | `docs/api/error-codes.md` | 补 40902/40903/41001/42202（代码已用未登记）+ 40901 预留 + 40301 语义扩注（越权统一按不存在处理） |

### 现状盘点结论（先答「有没有做过类似工作」）

- **分层/服务边界**：docs/06 §1、§2 已有文档级拓扑与职责表，但无设计说明书成文；docs/19 §1.1 是评审口径的现状速写（非设计）。
- **写方唯一性**：docs/10 §3 矩阵 + §5 细则已相当完整，但 **P0-7 实锤只有文档没有机制**：`seed.py` 直接写 Java 独占表（scenarios/placement_questions）、两服务共用同一 DB 账号、无任何守护。
- **数据流图**：此前**从未做过**正式 DFD（全仓无 mermaid/drawio），今天补齐 4 张（上下文/回合时序/报表流/写方边界）。
- **OpenAPI 契约**：基础设施此前已远超小组水平（双快照 + openapi-typescript 生成 + CI 三关卡 + refresh-openapi.ps1 + docs/06 §7），本次补的是「设计先行」的接口清单、内部 REST 契约与对账落地。

### 对账发现（2026-09-07 代码实测，全部登记进 R-1~R-16 / D1~D14）

1. **Python OpenAPI 快照中没有任何 operation 带 `security`**：practice/placement/defense/events 的 `Depends(get_current_user_id)` 因用 `Depends` 而非 `Security` 未进 OpenAPI；`/asr /score /tts /llm/chat` 四端点是真的裸奔（与 docs/19 P0-4 一致，未修）。
2. **docs/19 的 9 个 P0 经复核全部仍在**（2026-09-07 重查代码：进程内状态、同步 Session 跨 SSE、三处越权、裸接口、串行 TTS、`user_id` vs `userId`、seed 违例、reports 非 upsert、默认密钥/网关可达）——排期见 docs/20 §6 表（9/10~9/11 集中返工承接）。
3. **三处文档与代码不符（新发现）**：① docs/06 §7 写 `/api/auth/refresh`，实际网关路径 `/manage/auth/refresh`（R-15）；② docs/06 §7「评分 30/h」，代码 `ise_rate_per_hour=60`（R-16）；③ 错误码表落后代码 4 个码（本次已补）。
4. **快照口径修正**：Java 快照是服务原生路径，**对外契约以网关 `/manage/` 前缀为准**（docs/21 §2.2 已加说明）。

### 踩坑记录（追加第 29 条）

29. **「文档声称」必须与「代码事实」三方对账，不能拿 docs/06 当事实**：本次盘点靠逐条提取快照（PowerShell ConvertFrom-Json 列 paths + security）+ 关键行 grep 复核，发现 3 处 docs/06/docs/api 与代码不符（refresh 路径、ise 桶、错误码缺失）——这些差异如果只读文档永远不会暴露，而它们恰恰是接口设计说明书的「对账结论」最有价值的部分。做法：快照为唯一基准列端点，代码为唯一基准列鉴权/限流/字段名，docs 为第三列对比。

### 同日补记：Java 薄端管理端提前落地（超出分工计划）

把盘点出的 Java 缺口（admin 角色链路 / 用户管理 / 内容库 CRUD / 工单）全部实现，从 9/14~9/15 计划提前到设计日完成：

| 提交 | 内容 |
|---|---|
| `c8cbba2` | feat(java)：管理端最小集 —— JWT 加 role claim + `/api/v1/admin/**` hasRole(ADMIN)；用户管理（列表/详情/禁用启用/档案，改档 source=manual）；scenarios/songs/lrc/listening_materials/placement_questions 实体+CRUD（DELETE=归档；LRC 整首重写 → seq 重排 + pitch_ref_status→missing 触发 Python 重提取；题库 exam_revision 版本化 + 重复题 409）；工单（用户提交/我的 + 管理侧前向状态机 open→processing→resolved→closed，回复即认领）；Controller 按 Spring Boot 分层规范统一收 `controller/` 包，entity/repository 按域 |
| `b684e44` | test(java)：AdminUser/Content/Ticket 三组 API 测试（15 tests 全绿含既有） |
| `07a28a4` | chore(contract)：Java 快照 6→33 ops + `pnpm gen:api` 前端类型（现有调用零改动） |

门禁：`mvn verify` 全绿（15 tests + spotless + ContractSnapshotTest 对账新快照）；`pnpm typecheck` 通过（前端类型无破坏）。

### 踩坑记录（追加第 30 条）

30. **MockMvc `content(String)` 不是 UTF-8；Java 文本块里的 `\"` 是转义不是字面反斜杠**：单测两连坑——① 请求体含中文时 `content(String)` 按平台编码（ISO-8859-1）传输 → Jackson `JSON parse error` 400，必须 `content(body.getBytes(StandardCharsets.UTF_8))`；② 文本块（`"""`）中想表达 JSON 的 `\"` 实际是 `"`（转义生效），导致 `"interestTags":"["daily"]"` 这类 JSON 断裂——测试用 `[]` 或 `\\\"`。另：`git commit --amend` 会改 HEAD（上次 commit）不是任意 commit，错点后要用 `reset --soft` 重排队列。

---

## 2026-09-02 推荐系统落地实现 · 阶段 5（演示数据播种 + 链路冒烟）——推荐系统主体完成

> 阶段 0~4（地基/动态水平/素材难度/掌握度/推荐引擎）已交付。本阶段落地**演示播种**并做端到端冒烟，推荐系统主体代码闭环。**后续为前端联调 + Java 侧收尾（A-5.1 UserProfileEntity interest_tags 映射）。**

### 5.1 新增 `app/db/seed_recommend.py`（幂等演示播种）

| 播种项 | 说明 |
|---|---|
| 演示补充场景（L3/L4） | `面试 · 压力面（演示）` L3 + `商务谈判 · 深度磋商（演示）` L4（scene_type='other' 以过 CHECK；interest_tags 匹配 demo 账号）。**修 cross-exam A-5.2：现 seed 只有 difficulty 1/3、专家先验无 L4，L3/L4 账号无内容可推** |
| `seed_material_difficulty` | 全部 published 场景专家先验（复用 `app.difficulty.batch`）；演示场景强制 L3/L4 |
| `seed_demo_reco_accounts` | 3 个水平账号 `demo_reco_L2/L3/L4`：interest_tags + cefr_level + user_skill_state(est_level, confidence=1.0) |

写方唯一性：demo user 按 **seed 单写豁免**创建（docs/11 Q-A15，与 scenarios 同先例）；Java 侧如改 CommandLineRunner 播种需同步 interest_tags 映射。

### 5.2 `app/difficulty/batch.py` 微调

`upsert_scenarios` 改为**调用方统一 COMMIT**（batch.main --db 与 seed_recommend 各管自己事务），不再内部 commit。

### 5.3 新增 `tests/db/test_seed_recommend.py`（A-5.2 冒烟）

播种 → `recommend_scenes` 三账号 → 断言 **L2/L3/L4 推荐互异 + L4 命中商务谈判**。该用例同时验证了阶段 2~4 全链路（专家先验→难度→推荐）在真实 8+2 场景上端到端可跑。

### 5.4 验证

`pytest 79 passed`（+1 demo）；`ruff check .` 通过；`format --check .` 74 文件 all formatted。

### 5.5 踩坑记录（追加第 32 条）

32. **场景 scene_type CHECK 只允许 cafe/airport/interview/library/other**（content.py，与 docs/06 §9.6 一致）：自造演示场景用 `business` 会过不了 CHECK 建表即崩。改用 `other`（需求本就用其他兜底）。**教训：造 seed 数据前先核对目标表 CHECK 枚举，别凭直觉写 scene_type。**

### 5.6 阶段总览（0~5 完成，全部通过 ruff/format/pytest）

| 阶段 | 交付 |
|---|---|
| 0 | config 41 参数 + 5 张表模型 + 迁移 0003 |
| 1 | update_user_level（冷启动/滞回/低谷/幂等/事务，难度归一化符号修正） |
| 2 | 素材难度专家规则（词汇 CEFR 锚定/句法补全/发音 + 批量脚本 + 维度 A-5.2 修正） |
| 3 | 掌握度写入（user_mastery/user_corpus_mastery + 会话收尾挂钩，测试 DB 隔离修复） |
| 4 | 推荐引擎（recommend_scenes/shadow + 路由 + 缓存/主动失效，扩档 ±1 裁决） |
| 5 | 演示播种（L3/L4 场景 + 3 水平账号）+ 端到端冒烟 |

**待办（后续）**：① 前端推荐位联调（impression/click 上报）；② Java UserProfileEntity 补 interest_tags 映射 + InternalLevelController 幂等 PUT（A-2.2）；③ 迁移 0003 在真 PG 上 `alembic upgrade` + `alembic check` 零 diff；④ docs/10 写权矩阵补 shadow_materials（A-2.3）；⑤ 3 张新表演示账号/难度标签的契约（C10/D7）待 M3 排期。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统落地实现 · 阶段 4（规则推荐引擎 + 路由）

> 阶段 3（掌握度 + 收尾挂钩）已交付。本阶段落地**体系三匹配**：`app/rec` 的 recommend_scenes/recommend_shadow + 路由 `GET /api/v1/recommendations`。**可按评审后进入阶段 5（演示数据播种 + 端到端联调）。**

### 4.1 新增 `app/rec/service.py` + `__init__.py`

| 组件 | 说明 |
|---|---|
| `resolve_level` | 回退链 `user_skill_state.est_level(conf≥0.35) → user_profiles.cefr_level → L1` |
| `_candidates` | published 内容 + 难度档 ∈ levels **（md 优先，缺行内容方初评兜底）** + 掌握度（ORM 跨 SQLite/PG，等价 local/31 §4.3 CTE 的 LEFT JOIN 语义） |
| `_rank` | 排序 `未掌握(0)<进行中(1)<已掌握(2) → 难度距离 → 兴趣命中(↓) → 最近练过靠后` |
| `_diversify` | 同 scene_type ≤2（top-6 互异）；影子无约束 |
| `_order` | **扩档仅在 L±1 档内、距 L 近→远**（满足 local/32 C8 "L2 无 L4"；见下） |
| `_review_slots` | 复习席：L−1、in_progress/mastered、距上次 ≥review_gap_days、最久未练优先 |
| `_impression` | 写 `events.recommend_impression`（只追加；recommend_group_id + user_level + rule_version） |
| `_cache_get/_set` | Redis 缓存 `rec:{uid}:{type}`，`testing→None` 走直达 SQL（hermetic）；写后主动失效 |
| `recommend_scenes/shadow` | 主窗 [L,L+1] + 扩档 + 复习席 + 曝光埋点 + 缓存；对外返回**已清洗**（JSON 安全） |

**写方唯一性**：只读 6 表；只写 events（曝光）。

### 4.2 重要工程决策

1. **用 SQLAlchemy ORM 而非 raw CTE SQL**：等价实现 local/31 §4.3 语义，但**跨 SQLite/PG** → 推荐逻辑可在单测里跑（cross-exam 强烈要求可单测）；PG 专属 jsonb 函数不引入。
2. **扩档收窄为 ±1 档**：local/31 §5.3 写 [L−1, L+2]，但对 L2 会拉进 L4（违反 local/32 C8 "L2 用户不返回 L4"）。裁决：**扩档仅限于 L±1**（宁缺毋滥，不足就少返，不硬拉错档素材）。这解决了两处设计的真实冲突。
3. **缓存值清洗**：raw items 含 `_tag_hit/_dist/interest_tags/aware datetime`（不可 JSON 序列化）→ `_clean` 剥离，保证 `json.dumps` 与接口响应安全。落码时发现并修复。
4. **时间戳 aware 归一**：SQLite naive vs UTC aware 混比会 TypeError → `_aware` 统一。

### 4.3 新增 `app/api/routes/recommendations.py` + `main.py` 注册

`GET /api/v1/recommendations?type=scene|shadow&limit≤20`，`Depends(get_current_user_id)`，返回 `{type, items:[{id,content_type,title,scene_type,diff_level,mstatus,tag_hit}]}`。已验证 route 注册进 OpenAPI（`/api/v1/recommendations`）。

### 4.4 新增 `tests/rec/test_recommend.py`（5 条，local/31 §6.3 C 组）

L2 无 L4（C1/C8）/ 已掌握垫底（C9）/ 冷启动零档案返回默认（C7）/ L4 复习席补 L3（C3）/ 自有会话写曝光埋点（C5）。**全部用 function 级 `_fresh_db`（阶段 3 修的 isolation）跑，无跨测试泄漏。**

### 4.5 验证

`pytest 78 passed`（+5）；`ruff check .` 通过；`format --check .` 72 文件 all formatted；route 已在 OpenAPI。

### 4.6 踩坑记录（追加第 31 条）

31. **扩档与 cross-exam 冲突**：local/31 §5.3 的"先上后下 [L−1,L+2]"在 L2 用户会把 L4 拉进推荐（违反 local/32 C8）。**实现期用"扩档收窄 ±1 档 + 宁缺毋滥"裁决**，而非照抄文档数字——文档两处口径不一，以最新（cross-exam C8）+ 工程常识（不错档）为准。

### 4.7 待评审确认后继续

阶段 5：演示数据播种 + 端到端联调（`batch_calculate_difficulty --db` 预置 8 场景先验、3 个水平演示账号 L2/L3/L4 预置 user_skill_state、前端推荐位联调），并对齐 local/32 A-5.1~A-5.5 的演示前置。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统落地实现 · 阶段 3（掌握度写入 + 会话收尾挂钩）

> 阶段 2（素材难度专家规则）已交付。本阶段落地**体系三**：`app/mastery` 写 user_mastery（场景级）+ user_corpus_mastery（句级），并把 `update_user_level` + `update_session_mastery` 挂进 `complete_session` 收尾（A-3.3/A-6.5 完成）。**可按评审后进入阶段 4（推荐引擎 recommend_*）。**

### 3.1 新增 `app/mastery/service.py` + `__init__.py`

| 函数 | 作用 |
|---|---|
| `_attempt_score` | 场景级综合分 `0.6·pron+0.4·flu`（缺分自然排除，不按 0 计） |
| `_upsert_scene_mastery` | user_mastery：mastery_score = 会话均值增量混入、attempt_count/pass_count、`last_practiced_at`、status |
| `_corpus_line_map` | parse_corpus → phrase→line_index 映射 |
| `_upsert_corpus_mastery` | user_corpus_mastery：按 corpus_hit {phrase,state} 逐句 upsert（ok=100/达标、fix=30/待纠错） |
| `update_session_mastery` | 主入口：素材级（scene/shadow）+ 句级（仅 dialog 场景） |

**状态判定**（local/31 §5.1）：`mastered = 达标≥2 且均值≥75`；`in_progress = 60≤均值<75`；否则 not_mastered。**达标口径 = 会话级 S≥锚点(75)**（不是"任一轮达标"）——我初版按"any attempt≥75"误判为达标，实测后改为**会话均值**。

### 3.2 会话收尾挂钩（`app/practice/service.py`）

`complete_session` 在 `db.commit()`（报告）后新增 `_post_session_skills(db, session)`：try/except 守护调用 `update_session_mastery(db, session_id)` + `update_user_level(user_id, db)`；失败 `db.rollback()` + log 不阻塞报告（local/27 §9.4 降级纪律；A-6.5 独立 PR/全量回归）。

### 3.3 新增 `tests/mastery/test_mastery.py`

'句级+场景级' 端到端：达标句 mastered、待纠错句 not_mastered；场景级 pass_count=1/in_progress。

### 3.4 关键修复：测试 DB 隔离（`tests/conftest.py`）

**发现跨测试数据泄漏**：`test_mastery` 写 user_id=1，`test_skill` 的 `_mk_user` 又拿 id=1 → 其 attempts 崩入冷启动（est 66.7 而非 50）。根因 = `:memory:` + StaticPool 共享单连接，跨测试复用自增主键/数据。**修复**：conftest 的 `_create_schema` 从 session 级改为 **function 级 autouse** `_fresh_db`（`reset_engine()` + `create_all_for_tests()`）——每个测试一个全新 :memory: 库。这是测试隔离的正确做法（docs/06 第 6 章）。

### 3.5 验证

`pytest 73 passed`（含 master 1 + skill 6 + difficulty 7 等全部）；`ruff check .` 通过、`format --check .` 68 文件 all formatted。

### 3.6 踩坑记录（追加第 30 条）

30. **`reset_engine()` 不会重建表**——它只重置 global engine/session_factory，`:memory:` 单连接换 engine 后是**空库**，须再 `create_all_for_tests()`。conftest 的 `_fresh_db` 组合两者才算真正的"每测试隔离"。

### 3.7 待评审确认后继续

阶段 4：推荐引擎 `app/rec`（`recommend_scenes`/`recommend_shadow`，主查询 SQL + 扩档 + L4 复习席 + 曝光埋点 + Redis 缓存/主动失效 + 路由 `GET /api/v1/recommendations`）。前置于此：跑 `batch_calculate_difficulty --db` 把 8 场景先验写进 material_difficulty（推荐 SQL 靠它）。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统落地实现 · 阶段 2（素材难度专家规则）

> 阶段 1（update_user_level）已交付。本阶段落地**体系二**专家规则：三维度（词汇/句法/发音）+ CEFR 语义锚定 + 批量脚本。**可按评审后进入阶段 3（掌握度写入）。**

### 2.1 新增 `app/difficulty/rules.py`（纯函数，stdlib）

| 维度 | 公式 | 来源 |
|---|---|---|
| 词汇 vocab | `0.5·CEFR 语义锚定 + 0.3·生词率 + 0.2·文本统计(词长/长词比/音节)` | local/32 A-1.1/A-1.2 |
| 句法 syntax（**新补全**） | `0.5·平均句长 + 0.5·从属连词密度` | A-1.3 |
| 发音 pron | 难音素模式 + 词末辅音 + 音节数（中文母语者） | local/28 |
| 映射 | `M(k)=30+15(k−1)`（**不对称**，1→30/3→60/5→90，修 local/28 向心偏置） | A-1.2 |
| 聚合 | 逐句 → 逐维度 `mean+λ(max−mean)` → `0.4·M(vocab)+0.2·M(syntax)+0.4·M(pron)` | A-1.3 |

**CEFR 语义锚定**（A-1.1 标尺表写入 docstring：1=高中基础/2=初中高频/3=四级高频/4=六级职场/5=雅思学术）。无词频库 → 用"共同学习者白名单（COMMON_LEARNER）+ 学术后缀启发式"作代理（P2 可换真词表）。**这直接修了 cross-exam 的"长词=难词"误伤**（junior/student/majoring/communication/English 入白名单压实）。

`shadow_prior`：影子跟读三维（语速/停顿/连读，0.4/0.3/0.3）；**停顿方向反转**（≥表：越少越难）。

### 2.2 新增 `app/difficulty/batch.py`（批量标定 + CLI）

- `compute_scenario_features`：解析 target_corpus → 专家先验 + `pending_review`（|先验档−初评档|≥2）+ `owner_level` + features；
- `upsert_scenarios`：批量写 `material_difficulty`（source='expert'，features 落库）；**只写 Python 拥有的表**，不碰 scenarios.difficulty（Java）；
- CLI：`--json`（打印）/ `--db`（读 published 场景 upsert）。
- config.py：权重改 `difficulty_w_vocab=0.4 / difficulty_w_syntax=0.2(新增) / difficulty_w_pron=0.4`。

### 2.3 40 条语料实跑结果（`--json data/seed/scenarios.json`，已实跑）

| 场景 | 词汇 | 句法 | 发音 | 先验 | 档 | 初评 |
|---|---|---|---|---|---|---|
| 咖啡·点单 | 1.72 | 1.0 | 1.98 | 40.2 | L1 | L1 ✓ |
| 咖啡·订单沟通 | 3.02 | 1.4 | 3.33 | 57.3 | L2 | L3 (−1) |
| 机场·值机 | 2.42 | 1.4 | 2.7 | 49.92 | L1 | L1 ✓ |
| 机场·航班变动 | 3.16 | 1.35 | 3.35 | 58.11 | L2 | L3 (−1) |
| 面试·自我介绍 | 2.38 | 2.05 | 3.58 | 56.91 | L2 | L1 (+1) |
| 面试·深挖追问 | 3.68 | 1.8 | 4.05 | 66.78 | L2 | L3 (−1) |
| 图书馆·借阅 | 2.59 | 1.35 | 3.21 | 53.85 | L1 | L1 ✓ |
| 图书馆·学业交流 | 3.45 | 1.3 | 3.63 | 61.38 | L2 | L3 (−1) |

**关键**：`面试·自我介绍` 从 local/28 的 **+2 档高估 → 现在 +1 档**（CEFR 白名单把 junior/student/majoring/communication 压实）——cross-exam 的 A-1.2 修正落地成功。全部 8 场景落在 **±1 档内、0 个 pending_review**。入门全 L1、进阶全 L2（反映 corpus 实为 A1-A2，docs/19 事实，L3 偏宽）。

### 2.4 新增 `tests/difficulty/test_rules.py`（7 条，local/31 §6.2 B 组）

dim_to_100 / 词汇 CEFR 白名单修正（easy<3 且 hard>3）/ 句法嵌套 / 发音难音素 / 场景聚合 / 影子停顿方向 / 批量 upsert（SQLite 落库断言）。

### 2.5 验证

`ruff check .` 通过；`format --check .` 65 文件 all formatted；`pytest 72 passed`（+7）。`--json` 实跑结果如 §2.3。

### 2.6 待评审确认后继续

阶段 3：掌握度写入（`app/mastery`，user_mastery + user_corpus_mastery 会话收尾按 corpus_hit/attempts 聚合写入）。在此之前先补一个**演示前置**：`batch_calculate_difficulty --db` 要把 8 场景先验写进 material_difficulty（推荐 SQL 靠它，A-5.3）。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统落地实现 · 阶段 1（`update_user_level` 核心函数）

> 阶段 0（配置+5 表模型+迁移 0003）已交付并验证。本阶段落地**体系一核心** `app/skill/service.py`，含冷启动/滞回/低谷保护/难度归一化(符号修正)/幂等/事务。**可按评审后进入阶段 2（素材难度脚本）。**

### 1.1 新增 `app/skill/service.py`（Python 写方）

核心函数 `update_user_level(user_id, db=None)`，实现 local/31 §4.1 + local/32 修订：

| 模块 | 实现要点 |
|---|---|
| `_level_for` | 统一尺度纯分档 85/70/55 |
| `_level_hysteresis` | **滞回定档（local/32 A-3.1 修复三缺陷）**：三档界(85/70/55)全部套 `[thr−h, thr)`，升档即时、**降档只降一档**（禁 L4→L2 跨档）、滞回带内保持 |
| `_placement_score` | 定档分：`details.schema_version='2d'` → overall_score；否则 `level` → `BAND_MID`（兼容存量三维行） |
| `_window_samples` | 最近 N 个有效样本（pron/flu 非空），缺分轮自然排除（不按 0 计，local/32 A-3.3 Q14）；**难度归一化 `s += (diff−70)`** |
| `update_user_level` | 冷启动(n<5)/满窗(f 遗忘残余+floor)/**单次降幅钳制**/滞回+**低谷保护**/幂等写/事务 |

**冷启动**：`est = w·P + (1−w)·mean`，`w=max(0.3, 0.7−0.1n)`；完全冷启动(无定档无样本)=50/L1/conf0。
**满窗**：`est = f·P + (1−f)·mean`，`f=max(0.15·2^(−d/60), skill_placement_floor)`；confidence=`min(1, n/window)`（local/30 统一单调）。
**低谷保护(A-3.2)**：`downgrade_streak` 连续降级计数，达 `skill_slump_streak=2` → 冻结档位 `slump_guard_until=now+7d`；冻结期内档位不动。
**幂等三层**：attempts 不可变重算收敛 + `with_for_update` 行锁 + user_id 唯一约束；事务 try/except→rollback→raise。
`notify_java_level`：异步委托 Java 回写权威档（默认关，level_at 幂等 PUT，失败 Q-B07 兜底）。
`app/skill/__init__.py`：模块注释。

### 1.2 **发现并修正设计缺陷：难度归一化符号反了（重要）**

local/27 §4.1 公式写 `s = 0.6·pron + 0.4·flu − (diff_score − 70)`，符号**错误**：
- 易素材（diff<70）`−` 变 `+` → 用户易素材高分被再抬高 → 能力分**虚高**；
- 难素材（diff>70）`−` → 用户难素材低分被再压低 → 能力分**虚低**。
正确应为 `s += (diff_score − 70)`（越难素材越拉低实测分，须加回难度溢价）。本步已按正确符号实现。**登记：local/27 §4.1 待修订为 +。**

### 1.3 新增 `tests/skill/test_level.py`（核心单测，local/31 §6.1 A 组）

| 用例 | 断言 | 状态 |
|---|---|---|
| test_cold_start_no_placement_no_samples | 双缺→(50,L1,conf=0) | ✅ |
| test_placement_only_no_samples | 有定档无样本→est=62,L2,conf0 | ✅ |
| test_confidence_monotonic | n=4→0.4、n=5→0.5（local/30 修订回归） | ✅ |
| test_ji_journey_L2_to_L3 | 甲 P=62，窗口→74，est≈72.3→L3（local/30 §3 复算） | ✅ |
| test_hysteresis_keeps_L3_at_upper_edge | est 68.9(raw=L2) 且 ≥67 → 保持 L3（A5） | ✅ |
| test_difficulty_normalization_sign | diff=85 样本 raw60→归一 75 | ✅ |

### 1.4 验证

- `ruff check .` 全通过；`ruff format --check .` 61 文件 all formatted；
- `pytest 65 passed`（含新增 6 条 skill 单测）；
- 时间戳归一（SQLite naive→aware）已处理（docs/10 约定）。

### 1.5 踩坑记录（追加第 29 条）

29. **难度归一化方向易反**：`± (diff−70)` 是"能力估计"语境，越难素材（diff>70）用户实测分越低，要**加**回难度溢价；我初读设计（local/27 §4.1 写 `−`）差点照抄，实测后确认必须 `+`。**教训：涉及"估计/校正"的公式，落码前用极端值（diff=85 难/55 易）心算一遍方向。**

### 1.6 待评审确认后继续

阶段 2：素材难度专家规则脚本（`app/difficulty/rules.py` + `batch_calculate_difficulty`，含 CEFR 锚定表 + 句法维度补全 local/32 A-1.2/A-1.3）。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统落地实现 · 阶段 0（地基：配置 + 数据模型 + 迁移 0003）

> 依据 local/31 §2（5 表 DDL）+ local/32 六维拷问修订（config 零落地/滞回/低谷保护等）。**可按评审通过后进入阶段 1（update_user_level）。** 每步均已验证。

### 0.1 补齐配置项 `app/core/config.py`

拷问发现"参数全部进配置"是纸面承诺（`config.py` 原为 0 个推荐参数）。本步一次性写入 41 项，全部 env 前缀 `APP_`（`APP_SKILL_WINDOW_SIZE` 等）：
- **体系一（用户水平）**：`skill_window_size=10`/`skill_min_samples=5`/`skill_blend_placement=0.7`/`skill_blend_step=0.1`/`skill_placement_holdout=0.15`/`skill_placement_floor=0.10`（local/32 A-4.1 新增，防 f 无限衰减）/`skill_forgetting_halflife_days=60`/`skill_confidence_min=0.35`/`skill_band_hysteresis=3`（local/30 §7 滞回）/`skill_difficulty_normalize=True`/`skill_slump_streak=2`+`skill_slump_cooldown_days=7`（local/32 A-3.2 低谷保护）/`skill_trend_window=5`+`skill_trend_threshold=5`（A-4.3 趋势响应）/`skill_max_downgrade_per_update=5`（A-4.1 降幅钳制）/`skill_callback_enabled=False`（默认关=考试专属）+`skill_callback_retry_max=6`+`skill_callback_backoff_base_s=5`+`reconcile_schedule_s=30`（A-2.1 重试队列）。
- **体系二（素材难度）**：`material_difficulty_lambda=0.5`/`difficulty_w_vocab=0.5`/`difficulty_w_pron=0.5`/`shadow_w_wps=0.4`/`shadow_w_pause=0.3`/`shadow_w_link=0.3`/`calibration_min_n=30`/`calibration_min_users=5`/`calibration_max_user_share=0.3`/`calibration_kappa=10`/`calibration_cap=500`/`skill_anchor_score=75`/`skill_anchor_rate=0.75`（成对变更）。
- **体系三（匹配）**：`rec_cache_ttl_s=3600`（local/32 A-2.4 从 300s 改 1h）+`rec_limit_scenes=6`/`rec_limit_shadow=3`/`review_gap_days=7`/`review_ratio=0.33`/`review_mastery_threshold=0.8`（A-4.4）。
- 验证：ruff check 通过（修 5 处 E501 注释超长）。

### 0.2 枚举常量 `app/models/base.py`

`SessionKinds.SHADOW`、`AttemptKinds.SHADOW_SPEECH`、新增 `DifficultySources(EXPERT/BLEND/CALIBRATED)`、`MasteryStatus(NOT_MASTERED/IN_PROGRESS/MASTERED)`。

### 0.3 新增 4 个模型文件（Python 写方）

- `models/skill.py`：`UserSkillState`——est_score=0.6·pron+0.4·flu、est_level（滞回）、confidence、sample_count、`downgrade_streak`/`slump_guard_until`（低谷保护）、source_version；
- `models/difficulty.py`：`MaterialDifficulty`——diff_score/diff_level/difficulty_source 三态/prior_score/calibrated_score/calibration_count/distinct_users/last_calibrated_at/features/version；`(content_type,content_id)` 唯一，次生表无 FK；
- `models/mastery.py`：`UserMastery`（场景级快照）+`UserCorpusMastery`（句级明细，`(user_id,scenario_id,line_index)` 唯一）；
- `alembic/versions/0003_m_recommend.py`：5 张新表 + `sessions.kind` 扩 `'shadow'` + `sessions.shadow_material_id` FK SET NULL + `attempts.kind` 扩 `'shadow_speech'`。

### 0.4 内容库追加 + 模型注册

- `models/content.py`：追加 `ShadowMaterial`（Java 写内容库，Alembic 建表；level 初评 1-4、wpm、text_content、audit 见 local/32 A-3.3）；
- `models/__init__.py`：注册 `ShadowMaterial/UserSkillState/MaterialDifficulty/UserMastery/UserCorpusMastery` 到 `__all__`。

### 0.5 验证（全部通过）

| 项 | 结果 |
|---|---|
| 模型导入 / metadata 注册 | 25 张表（原 20 + 新 5）全部注册 |
| `create_all`（SQLite 单测路径） | OK，25 表，SQLite 兼容（bigint_pk with_variant） |
| alembic heads | 单头 = 0003 |
| alembic upgrade head --sql（PG 离线渲染） | 5 表 CREATE + sessions/attempts CHECK 扩展 + shadow_material_id FK 全部生成 |
| ruff check + format | 通过（修 6 处 E501） |
| pytest（models/health/seed） | 15 passed |

### 0.6 踩坑记录（追加第 28 条）

28. **本地 alembic upgrade 会连 PG 而非 SQLite**：`.env`/compose 设了 `APP_DATABASE_URL=postgresql+psycopg://...`，本地起 alembic upgrade 直接连 PG（未启动 → 挂 120s 超时）。**验证迁移用地**：显式 set `APP_DATABASE_URL=sqlite+pysqlite:///./_mig_test.db`，但 0002 的 `create_foreign_key` 在 SQLite 不支持（须 batch_alter_table），链条跑不动——**这是既有的**（项目 SQLite 测试用 `create_all_for_tests`，不走 alembic）。所以 SQLite 侧验证用 `create_all` + `alembic check` 不适用（需真 PG）；**PG 侧验证用离线 `alembic upgrade head --sql`**（无连接，纯渲染 PG 方言），已确认 5 表 + CHECK 扩展生成正确。

### 0.7 待评审确认后继续

阶段 1：`app/skill/service.py` 的 `update_user_level(user_id)`（含冷启动/滞回/低谷保护/事务/幂等）。请先审本阶段，**确认 OK 再开下一阶段**。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统六维火力拷问（算法侧交付物，归档 local/32）

派 6 个子代理对 local/26~31 推荐系统设计做对抗式拷问（20 问 × 6 维度：数据冷启动/算法严谨/工程集成/边缘降级/验收演示/排期资源），全部实读代码+文档，产出 `local/32-语音链路现状与风险清单·推荐系统六维拷问.md`（正文 20 问逐项答辩 + 附录 A 六维度证据级增补）。**未改代码、未动现有文档。**

最高优先级 3 条：① **config 参数零落地**（skill_*/material_difficulty_lambda 等全部不在 config.py；5 张新表/模型/路由/rec: 键全部零存在——"设计完备、代码空白"）；② **设计-代码脱节**（40303 门禁全仓零命中、complete_session 未调 update_user_level、InternalLevelController 无条件覆盖无 levelAt/source、demo 账号兴趣未映射+seed 无 difficulty=4 素材）；③ **2 个未入账块**（user_mastery+user_corpus_mastery 会话收尾写入；docs/06 §9.5 验收候选池"场景+歌曲+听力" vs 实现"场景+影子"的口径漂移——歌曲/新闻画像必挂）。

其余关键实锤：权重分支阶跃（n=5 处 0.3→0.15 无理由跳变，比 confidence 不连续更隐蔽）、diff_dist 二值化抹平档内难度、Q-B07 只覆盖考试通道是 skill 通道伪兜底、推荐缓存无主动失效、demo 账号缺 L2、用例数"40+"实为 30 条、无覆盖率目标、难度秒变链路断（md 优先致 Java 改 scenarios.difficulty 不生效）、排期"4.5~7 人日"出处实为 local/24、推荐实际 P1≈5~8/全量≈7.5~12 人日、无 M3 实施计划文档、wav2vec2 ADR 已排序（推荐>唱歌>wav2vec2）。

待拍板（汇总）：① 验收口径修订（docs/06 §9.5 换 scope 还是扩候选）；② 推荐做多深（保底规则版 1~1.5 人日 vs 全量 P1 5~8）；③ 影子跟读身份（二期扩展 vs 主玩法）；④ 难度秒变入口归属（Python internal 接口）；⑤ 复习席 mastery>80% 触发；⑥ 通用化滞回 + 低谷保护列。建议开工前补 docs/20-M3 实施计划。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统详细设计说明书（汇总定稿，归档 local/31）

整合 local/26~30 全部讨论为一份可交付设计说明书（`local/31-推荐系统详细设计说明书.md`），作为 M3 实现与答辩的统一依据。结构：设计目标与约束（技术栈/写方唯一性矩阵/统一尺度/四水平消歧）→ 三套评价体系（5 张新表 DDL：user_skill_state / material_difficulty / user_mastery / user_corpus_mastery / shadow_materials）→ 联动数据流图 + 端到端旅程（甲 t0~t3 复算表）→ 核心算法伪代码（update_user_level 含滞回与幂等、batch_calibrate 含触发阈值、recommend_scenes/shadow 主查询 SQL）→ 冷启动与降级 7 层 → 验收标准（6 组 40+ 单测用例含 I1~I5 不变量与 local/30 修订回归）。

**本文为准的三处修订**（相对 local/26~29）：① confidence 统一 `min(1, n/window)`（修 0.8→0.5 跳变）；② est_level 滞回带 [67,70)（skill_band_hysteresis=3，升即时/降滞后）；③ 空池兜底宁缺毋滥（限 L−1 档 + fallback 标记，<3 返回空态）。配置项汇总 18 项 + 待拍板 6 项集中到 §7.2。

—— 执行人：Faust-sudo
## 2026-09-02 三套体系联动端到端数值模拟（算法侧交付物，归档 local/30）

把 local/26/27/28/29 串成完整用户旅程并做数值验证（`local/30-三套体系联动·端到端数值模拟.md`），**全部数字脚本复算**（venv python）。

- 场景1（甲 L2→L3）：窗口均值 74 不直接定档，`est=0.142×62+0.858×74=72.30≥70→L3`；est 单调 62→66.4→68.5→72.3 无跳变；est_level=L3 与 cefr_level=L2 双档并存不循环（I5）。
- 场景2（推荐动态）：变档后 top-6 档位重心 3×L2+3×L3 → 3×L3+1×L4+2×L2（L4 占位演示），重叠 5/6 不震荡，L3 用户最低见 L2（I1）。
- 场景3（校准）：学业交流专家 3.5→74.38(L3)，100 用户实测 2.8→64.75(L2)，贝叶斯 (100×64.75+10×74.38)/110=65.62→L2 calibrated；降档后 L3 用户降位、L2 用户升位（I4）。
- **模拟发现 3 个逻辑漏洞**：① local/27 confidence 不连续（n=4→0.8、n=5→0.5，两分支公式不一）→ 统一 conf=min(1,n/window)；② 档位边界震荡无滞回（est 70±0.5 → 推荐窗口整窗翻转）→ 滞回带 [67,70)，升即时/降滞后，skill_band_hysteresis=3 进配置；③ 极端空池兜底会推 L1 给 L3 → 宁缺毋滥（兜底限 L−1 档 + fallback 标记，池<3 返回空态）。
- 不变量 I1~I5 全部成立（正常路径无"L3 用户被推 L1"）。待拍板 3 项：滞回设计、confidence 修订随 0003、宁缺毋滥兜底。

—— 执行人：Faust-sudo
## 2026-09-02 规则推荐引擎详细实现（算法侧交付物，归档 local/29）

承接 local/26~28，落地规则推荐引擎（`local/29-规则推荐引擎·详细实现.md`）。先实读核实：**user_corpus_mastery 不存在**（0001/0002 共 20 表），一并设计；user_mastery/user_skill_state/material_difficulty/shadow_materials 均为设计稿（迁移 0003+ 待落地）。

6 项决策：① `面试·自我介绍` +2 档高估 → **标定兜底**（P1 不引 CEFR 词表，登记 P2；影响面 1 场景且难度护栏 ±2 可容，标定是自适应修复 vs 词表一次性修复）；② 推荐 SQL = 一条 CTE 语句（动态定级→[L,L+1] 过滤→ROW_NUMBER 每 scene_type 限 2→未掌握/难度/兴趣/新鲜排序→LIMIT 6）；③ 校准频率 = 每日 UTC 03:00 定时 + 增量节流（难度是慢变量、reports 日聚合同窗口、n≥30 需攒数天）；④ 不足 3 个先上后下扩档（i+1 挑战优先），L1/L4 边界收敛；⑤ L4 复习席 = 1/3 席位给 L−1 已掌握且 ≥7 天未练（间隔复习+随机，防枯燥）；⑥ calibrated/blend 管理端三态展示、推荐侧不区分（source 是审计属性不进排序键）。

交付：`user_corpus_mastery` DDL（句级明细，与 user_mastery 场景级快照分工：推荐直读 user_mastery，句级喂聚合/报告/复习调度）；`recommend_scenes(user_id, limit=6)` + `recommend_shadow(user_id, limit=3)` 完整 SQLAlchemy 实现（主查询+扩档+复习席+曝光埋点，只写 events）。待拍板 3 项：复习席比例/间隔窗口进配置、scenario_id 归档语义、L1~L3 是否也开复习席。

—— 执行人：Faust-sudo
## 2026-09-02 素材难度评价分阶段实施策略（算法侧交付物，归档 local/28）

承接 local/26 §4 + local/27 §1/§3/§7，产出素材难度两阶段实施策略（`local/28-素材难度评价·分阶段实施策略.md`）。先核实依赖：numpy 是直接依赖（pyproject.toml L24），但脚本刻意用纯 Python stdlib（40 条量级阈值映射无向量化收益，CI/单测零额外依赖）。

- **阶段一专家规则**：场景两维（词汇复杂度/发音难点，1~5）加权 `0.5·M(vocab)+0.5·M(pron)`，M(k)=40+(k−1)·13.75 对齐档位起点；影子跟读三维（语速 wps/停顿密度/连读密度，1~5 阈值表，停顿方向反转）权重 0.4/0.3/0.3。
- **batch_calculate_difficulty() 已实跑验证**（`--json data/seed/scenarios.json`，venv python）：40 条语料全部打出初始分；8 场景中 3 个与内容方初评一致、4 个 ±1 档、1 个 +2 档（面试·自我介绍，学习者高频长词被"长词=难词"高估）→ 挂 pending_review。
- **阶段二校准**：分箱插值 D_emp（按 user_skill_state.est_score 分箱，线性插值穿越 0.75 锚点）+ 贝叶斯平滑 `D_cal=(n·D_emp+κ·D_prior)/(n+κ)`（κ=10，主推），移动平均为增量备选；触发阈值 **n≥30 且 distinct_users≥5 且单用户占比≤30%**（SE≈0.079→难度分误差≈1.2 分<1 档的推导）；n≥100 转 calibrated。
- **DB 字段**：material_difficulty 增 difficulty_source('expert'|'blend'|'calibrated')/prior_score/calibrated_score/calibration_count/distinct_users/last_calibrated_at，features JSONB 存维度明细。
- 待拍板 3 项：CEFR 词表白名单 vs 标定兜底、校准频率、source 三态展示口径。

—— 执行人：Faust-sudo
## 2026-09-02 用户水平动态评价实现细节深化（算法侧交付物，归档 local/27）

承接 local/26，深化动态水平体系为可落地实现（`local/27-用户水平动态评价·实现细节深化.md`）。先实读代码核实：练习轮 ISE 以 ASR 转写为参考（自参照评分，`orchestrator.py:161/454`）；`complete_session` 是会话收尾唯一咽喉（orchestrator 三处 + practice.py 路由）；回调先例 `placement.py::_callback_level`（httpx + service-token）；Java `InternalLevelController` 现为无条件覆盖（需扩 level_at 幂等 PUT，`user_profiles.cefr_level_at` 列已存在）。

8 项决策：① 场景难度聚合 λ=0.5 进配置（可标定）；② 滑动窗口=10 个有效样本（≈1.5~2 会话，SE≈σ/√10 远小于档距）；③ 锚点 0.75 = 同一配置块成对参数化（anchor_score+anchor_rate 同次变更，防统一尺度断裂）；④ 定档分 vs 窗口均值固定 0.6:0.4 不合理 → 冷启动 w=0.7 随样本量衰减 + 满窗按遗忘曲线（半衰期 60 天）留 0.15 残余（依据练习幂律 + 遗忘曲线 + 自参照刻度差）；⑤ 影子跟读必须进 sessions.kind（砍掉会污染指标口径/难度标定/掌握度取数，迁移成本极低）；⑥ 冷启动 min_samples=5 定档分主导 + confidence 阶梯；⑦ 难度缺行兜底 FALLBACK_LEVEL 采纳（零冷启动/确定性/守写权/防 NULL/标定平滑接管）；⑧ 更新时机=会话收尾批量更新，非 practice_complete 埋点、非每轮。

交付：完整 `update_user_level(user_id)`（SQLAlchemy，含冷启动分支、事务回滚、三层幂等：收敛重算/行锁/唯一约束）、`notify_java_level` httpx 回调（level_at 幂等 PUT，默认关、考试专属）、集成点 diff（complete_session 末尾 + placement finalize）、单测清单 7 条。事务回滚与幂等性已主动内建（预期追问项，未漏）。

—— 执行人：Faust-sudo
## 2026-09-02 推荐系统整体框架设计（算法侧交付物，归档 local/26）

算法负责人产出推荐系统整体框架设计稿，先实读代码核实约束再成稿：40 条场景语料 = `data/seed/scenarios.json` 8 场景 × 5 句（已逐条核对）；影子跟读素材尚无内容表。交付物（`local/26-推荐系统整体框架设计·三套评价体系与统一尺度映射.md`）：

- **三套评价体系三张表 DDL**（PG16/Alembic 对齐）：`user_skill_state`（动态水平，练习评分 EWMA，Python 写）/ `material_difficulty`（素材难度，特征先验 + 行为标定，Python 写）/ `user_mastery`（掌握度，匹配状态表，Python 写）；另附支撑表 `shadow_materials`（Java 写）及前置迁移项（`sessions.kind` 扩 'shadow'、`sessions.shadow_material_id`、`attempts.kind` 扩 'shadow_speech'）。
- **统一尺度映射（显式给全）**：0-100 共轴、85/70/55 档界两端共用，难度分锚定「达标率 0.75 的用户能力分」，行为标定闭环回流。
- **联动数据流图**（文字版）+ **`get_recommendations(user_id)` 伪代码**（Python/SQL 混合，严格分层优先级：未掌握 > 难度匹配 > 兴趣标签 > 新鲜度，含难度出界硬护栏与 top-3 互异）。
- 全程守写方唯一性：不写 `scenarios.difficulty` / `user_profiles.cefr_level`（只读映射兜底），动态档位只落 Python 表；推荐埋点复用既有 `events.recommend_impression/click`，CTR 口径复用 `reports`。

待组长拍板：§9.3 开放项 4 条（场景难度聚合系数、0.75 锚点参数化、影子跟读是否进 sessions.kind、难度缺行兜底）。
—— 执行人：Faust-sudo

## 2026-09-02 lieflat-charts 表盘美化（预览高保真）：按技能选型规则出图，不"接入"库

### 背景与产出

用 [lieflat-charts](https://github.com/larashero3-dotcom/lieflat-charts)（AI Agent 用的数据可视化 Skill：
`SKILL.md` 选型法典 + gallery 正本模板）为 VocalVerse 表盘数据做美化，示例数据口径与 docs/06 §9.1 一致，
先出 preview（docs/13 §8：静态高保真 → 视觉验收 → 集成真实 view）：

| 交付 | 文件 | 模式 / 体系 | 选型 |
|---|---|---|---|
| 管理端评价看板 | `apps/web/src/assets/lieflat/vv-admin-dashboard.html` | 图表模式 · Glance × PORCELAIN | 四指标 KPI 卡 + G8 / G3 / G4 / G13 / G14 |
| 用户端学习报表 | `apps/web/src/assets/lieflat/vv-learning-report.html` | 报告模式 · R09 骨架 × PORCELAIN | 雷达（SKILL §7 例外）+ F2 / F4 / L15 + KPI 栏 |

- 预览入口：dev 环境 `/preview/lieflat`（前端预览画廊，生产构建自动剔除）；渲染组件
  `src/components/LieflatChart.vue`（sandbox iframe + srcdoc + postMessage 高度桥）。
- 选型审计记录（含全部淘汰理由）与许可说明：`apps/web/src/assets/lieflat/README.md`。

### 关键点

1. **这是"用技能出图"，不是把库接进产品**：交付物是两份单文件 HTML，与前端渲染机制解耦；
   M3 真实接口落地后替换数据即可，届时再决策"iframe 渲染 vs 移植 Vue SFC"。
2. **选型按 SKILL.md 硬约束**：看板 = 用户明确要 dashboard → Glance 系入场（Lupi/Basics 不适配理由
   已记录）；报表 = 报告模式 R09（淘汰 R12 依赖最重 / R03 无 KPI 槽位 / R05 密度不足 / R11 定尺太窄）；
   页内图全部复用 gallery 正本结构（图脚标 REAL TEMPLATE），雷达按 §7 例外用 ECharts 原生换肤。
3. **许可 ⚠️**：上游为 PolyForm Noncommercial 1.0.0（仅限非商业用途）。本项目作实训项目使用没问题；
   **若未来商用，须向作者申请授权**，或在 M3 集成前重绘（ADR 决策点）。
4. **踩坑 28（SFC 字面 `</script>`）**：`LieflatChart.vue` 桥接脚本字符串里的关闭标签必须写
   `<\/script>`（反斜杠转义），且 **doc 注释里也不能出现字面 `</script>`**——@vue/compiler-sfc 按
   字面序列切脚本块，注释里的字面串把块切在 40 行，报"`*/` expected"。另一处踩坑：交付 HTML 的
   内联脚本按 SKILL 自检 7 用 `node --check` 抽检，抓到雷达 legend `fontFamily:'Inter','Noto Sans SC'`
   逗号语法错误（改 `'Inter, Noto Sans SC'`）。

---

## 2026-09-01 实训作业四件套 + 六路拷问：从"能不能跑"到"该不该这么做"的补课

### 背景与产出

今日要求：需求调研文档（含 2 份竞品分析）+ 项目计划 + 四件套（立项/计划/调研/SRS）在需求评审前交付。MVP（M1+M2）已于今日之前完成，因此本日核心工作量在**产品侧拷问**而非开发——派 6 个子代理对已实现系统火力全开拷问，产出归档于 `docs/19-*.md`，交付物在 `local/9月1日实训作业/交付物/`：

| 交付物 | 文件 | 说明 |
|---|---|---|
| 需求调研报告 | 01-需求调研报告.md | 用户画像 3 个、竞品深度分析 2 份（流利说/Speak，B/C 分工）、功能矩阵、P0~P2 决策 5 条 |
| 项目立项报告 | 02-项目立项报告.md | 按 Project Start Report 模板；工作量 62 人天（模块口径）/72.5 人天（全项目口径）；风险登记 15 条 |
| 项目计划（简版） | 03-项目计划（简版）.md | 按 SPP 模板；WBS 24 工作包 + 19 日甘特图；产能缺口 40% 四层应对 |
| 需求规格说明书 | 04-需求规格说明书.md | 全量功能需求 + 验收标准 + 可追溯矩阵 + 代码级缺陷清单 C-1~C-16 |
| 产品功能说明书 | 05-产品功能说明书.md | 万玄阁章法：19 章，功能 + 系统 + 算法 + 合规全量 |
| 项目组成员分工 | 06-项目组成员分工.md | 万玄阁体例：现状/目标/阶段/逐日任务；A/B/C 代号 |

### 拷问结论（六份报告的交叉印证）

- **产品**：选题成立但定位必须收敛（全年龄段 → 以有 deadline 的真实开口事件为锚点）；唯一真壁垒 = 评分与真人评委 r≥0.7；40 条语料 30 分钟打穿（已复核实）；唱歌转影子跟读、推荐降级规则、答辩导师泛化。
- **UX**：FTUE 8 步 90~120s（目标 ≤20s）；■ 假按钮等 9 项 P0，修复清单 ≤2 人日。
- **架构**：9 条 P0（进程内会话、同步 DB 连接、三处越权、裸接口无鉴权、首声 6~7.6s、跨服务字段名错断、默认密钥等），最小修复集 5~6 人天；结论「撑到交付、撑不到上线」。
- **商业**：单轮成本中位 ¥0.67（TTS 42% + ISE 27% + 审核 14% + LLM 仅 7%）；1 万 DAU 月烧 16.6~124.6 万；免费用户成本须压到 ≤¥1/月；B 端是唯一 LTV/CAC 成立的路径。

### 本轮顺带修复（代码级，全部亲验）

1. **PracticeView `NCard` 未注册**（UX 拷问 P0-9）：模板用 `<NCard>` 但 import 缺失，评分卡渲染残缺。全仓复扫仅此一处，1 行修复已推送 main（8a0dd0b）。
2. 六条代码级实锤亲自复核通过：报告越权（`get_report` 无归属校验）、跨服务字段名不匹配（`user_id` vs `userId`，定档回写 100% 断）、默认密钥入库、24h 清理未实现（仅惰性过期）、音频 sha1 明文平铺、前端零隐私组件。

### 踩坑记录（追加第 27 条）

27. **子代理结论必须抽查，不能直接采信**：6 份拷问报告共 400KB+，引用几十处「文件/行号」。本轮对其中 6 条高影响断言逐一回读代码验证——全部属实（含 P0-6 字段名这种"整链路坏掉但全仓测试绿"的案例），但过程说明：**引用行号的论断验证成本极低（一次 grep），不验证就直接写进交付文档是对评审负责的失职**。另一个坑：子代理写入的路径要复查（本次六份报告初次落盘在仓库根目录，后续方归档到 docs/；早先一次转换脚本曾把 0 字节文件写到仓库根，已清理）。

---


### 背景

PR #22（Faust-sudo，入学测试录音停止键）复审后发现补丁自身仍有三条破的边界路径，已整改（详见 `worklog/BUG实测/入学测试功能测试.md` BUG-001-R）。本条记录后续三项收尾。

### 1. 停止键修复推广到 Practice / Defense

BUG-001 踩坑记录 3 已标注这两页同模式。本轮统一：

- `DefenseView.startAnswer()` 与修复前的 Placement **逐行同构**（`if (recording.value) return` + 无 try/catch），两个 bug 全中；
- `PracticeView.startRecording()` 的守卫是 `phase !== 'ready'`，而 `phase` 在录音期间仍是 `'ready'`（只在 `sendTurn` 内才翻 `'busy'`），所以点 ■ 会重入 `startRecording()` 并被 `recorder.start()` 内部的 `state === 'recording'` 守卫吞掉 → 停止键同样失效。

两页改为与 Placement 一致的「录音中 `stop()` / 启动窗口 `cancel()`」二选一，并接上 `micErrorMessage` 与 `MIN_RECORD_MS`。

### 2. 服务端音频下界（40002）

前端停止键修好后，**误触第一次成为可能**：原先停不下来，录音时长恒等于 15s。新增 `app/audio/upload.py::validate_audio_bytes` 统一上下界：

- `placement.py`：**校验前置于限流扣减**——空录音不该消耗 ASR/ISE 配额，也不该推进题目；
- `practice.py`：带音频的回合先校验（空录音会推进 `current_turn` 且不可重来）；
- `/asr` `/score` 是无状态管线端点，保持 `min_bytes=0` 的历史行为，只共用上界实现。

> **残留（已知未修）**：`practice.py` 的限流是 FastAPI `Depends`，依赖先于函数体执行，故该路径上配额仍先于下界校验被扣。要修需把 `consume` 移进函数体，会牵动既有 429 用例，本轮未做。

### 3. ⚠️ `frontend-ci` 与 `python-ci` 从未真正执行过

排查 PR CI 状态时发现两条工作流 `conclusion=failure` 但 **`jobs.total_count = 0`**——启动即失败，一个 step 都没跑。根因是 YAML 语法错误：

```yaml
- name: Contract: OpenAPI snapshot in sync    # ← 未加引号的标量里出现 ": "，非法
```

用 `yaml.safe_load` 逐个解析五条工作流：**恰好只有这两条 INVALID，也恰好只有这两条 jobs=0**，其余三条（java-ci / secret-scan / docker-build）正常。加引号后五条全部解析通过（python-ci 9 steps、frontend-ci 10 steps）。

这意味着此前所有「门禁全绿」的结论（含上一条日志 2026-09-01 表格里的那一行）**都只是本地跑的**，GitHub 上这两条从来没验证过任何东西。顺带修掉门禁真正跑起来后立刻会红的一处存量问题：`alembic/versions/0002_m2_practice.py` 未过 `ruff format --check`。

已按 CI 的九/十个步骤在本地逐条复跑：ruff check / ruff format --check / uv lock --check / pytest 45 / OpenAPI 契约快照一致 / alembic 单头 / pnpm gen:api 无漂移 / lint / typecheck / vitest 18 / build —— 全绿。

### 踩坑记录（追加第 24~26 条）

24. **CI「红」和 CI「没跑」是两回事**：`conclusion=failure` + `jobs.total_count=0` = 工作流启动失败，一个 step 都没执行。只看 PR 页面的红叉会误判成「某个测试挂了」。**排查工作流问题第一步查 jobs 数量，而不是翻日志**（日志根本不存在，`gh run view --log-failed` 会报 log not found）。
25. **YAML 未加引号的标量里不能有 `": "`**：`name: Contract: OpenAPI snapshot in sync` 会被当成嵌套映射 → 整份工作流非法。这与踩坑 14（块标量里 `#` 不是注释）是同一家族：**YAML 的字符串比看上去更需要引号**。约定：step `name` 只要含 `:`、`#`、`{`、`[` 一律加引号，并在改动工作流后本地 `yaml.safe_load` 过一遍。
26. **修好一个限制会解锁新的输入域**：停止键不可用时录音恒为 15s，修好后 200ms 的误触第一次成为可能，而上传即推进题目/回合且不可重来。**新增能力要同时补上它放开的输入域约束**（前端 `MIN_RECORD_MS` + 服务端 40002 双侧）。

---


### 背景

- M2 全量合入后，按 README 方式 B 本机启动（三端 + PG/Redis 容器），浏览器实测登录/对话，一组**只在"经网关 + 浏览器"路径上才暴露**的坑连爆（同日）。排障方法论沉淀：**同一症状逐层二分（直连 8080 / 经 5173 网关 / 浏览器 DevTools Network），每层换一个变量再测**。

### 排障链（症状 → 根因 → 修复）

1. **登录 403 + 空响应** → ① Java 控制器误把路径写成 `/manage/auth`（网关 nginx/Vite 剥离 `/manage` 前缀后变成 `/auth/login`，无匹配）；② 更深一层：Spring Boot 3 默认把 `/error` 错误转发**也纳入安全过滤链**，控制器抛错（401/404）先跳 `/error` 而 `/error` 不在 permitAll → 任何异常都被织成 403 空响应。**修复**：控制器路径去掉 `/manage`（与 PingController `/api/v1` 同语义）+ `/error` permitAll；已在线验证：正确账密 200，错账密 401 带 JSON 体。
2. **登录后对话 401 missing bearer token** → ① SSE 回合走 `openSseFetch` 直连 fetch，**绕过了 `request()` 的自动 `Authorization` 注入**；② 更隐蔽：`bootstrapAuth()`（localStorage→全局 token 恢复）**从没接线到启动流程**——任何一次 F5 之后全局 token 为空，全部 API 401（"重新登录又好、刷新又挂"的元凶）。**修复**：`openSseFetch` 支持 headers + `streamTurn` 带 `authHeaders()`；`main.ts` 启动调用 `bootstrapAuth()`。
3. **连续对话报 stale turn 409** → 提示卡"继续对话"发出**无音频 hint 回合**：服务端早退分支**不推进 `current_turn`**，而前端**任何 `turn_end` 都 +1**——计数器双写不同步，下一轮 `expected_turn` 失配。**修复**：服务端 hint/demo 回合落库并推进轮次（兜底）；前端示范/提示卡改为**仅播音频 / 直接录音**（回合只在录音后发生），横幅按钮改「🎙 试试说 / 🔊 示范」。
4. **启动报错三连**：`uv run uvicorn` 报 WinError 10013（8000 被旧实例占用，非 bug）；`alembic` 命令不识别（Windows 下 `uv run` 不激活 venv，裸命令不在 PATH）；seed 报 `password authentication failed`（`.env.example` 的 DB 密码是占位符 `change-me-db-password`，与 compose 默认回退值 `vocalverse-dev` 失配）。**修复**：`.env.example`/根 `.env.example` 默认值对齐 compose 回退；README 命令加 `uv run` 前缀 + FAQ 三行。
5. **Java 日志中文乱码**（`婕旂ず璐`）→ 双重错位：pom 未声明 `project.build.sourceEncoding`（GBK 系统按平台码读源文件）+ 终端码页 cp936。**修复**：pom 钉 UTF-8 + `chcp 65001` / `-Dstdout.encoding=UTF-8`（README FAQ）。

### 踩坑记录（追加第 16~23 条，与前文 15 条连续编号）

16. **网关剥离前缀 vs 控制器路径**：Java 控制器若带 `/manage` 前缀，MockMvc/直连 curl 永远测不出（都能 200），**只有经 nginx/Vite 网关才暴露 403**。约定：Java 侧路径一律不带 `/manage`（网关剥离后命中），与 PingController 语义一致；改路径必同步：SecurityConfig 匹配器 / ServiceTokenFilter / Java 测试 / Python 回写 URL / 联调脚本。
17. **Spring Boot 3 的 `/error` 也在安全链里**：自定义 `SecurityFilterChain` 后，任何控制器异常 → `/error` 转发 → 不在 permitAll → 织成 **403 空 body**（前端 `JSON.parse` 报 "Unexpected end of JSON input"，症状与真 403 无法区分）。**处置**：`/error` permitAll；排障时看 DevTools 响应体是否为空是判别信号。
18. **直连 fetch 绕过公共客户端**：`openSseFetch` 这类专用请求路径必须显式携带 `authHeaders()`——**公共 `request()` 的鉴权不是全局中间件**；同理 `bootstrapAuth()` 必须接线（main.ts），否则刷新即丢全局 token。
19. **计数器双写不同步**：同一"轮次"概念在服务端（当前轮）与前端（已收 turn_end 数）各维护一份，任何分支（hint/demo/错误降级）少推/多推一侧都会产生 stale turn；**原则：turn_end 的发送方 = 轮次推进方**，前端按事件数累加。
20. **Vite 只绑 ::1**：`127.0.0.1:5173` 打不开但 `localhost:5173` 正常——不是错误，IPv6-only；排障时别把「localhost 通、127.0.0.1 不通」当异常。
21. **`.env.example` 占位符 vs compose 回退值**：`change-me-db-password` 与 `${POSTGRES_PASSWORD:-vocalverse-dev}` 失配 → 复制即用必炸；**默认值必须与 compose 回退一致，且改密码三处同步**（compose 环境变量 / services/python/.env / 根 .env）。
22. **Windows 裸命令不在 PATH**：`uv run` 不激活 venv——`alembic/uvicorn/pytest` 一律 `uv run` 前缀，README 已全部修正。
23. **Java「编译期 + 运行期」双重编码**：pom `sourceEncoding=UTF-8`（编译期）+ `chcp 65001`/`-Dstdout.encoding`（运行期）；缺一都会乱码。另：**jar 被运行进程锁定**时 `mvn package` 报 `Unable to rename ... .original`——先停 Java 再打包（Windows 文件锁）。

### 验证状态（本日结束时）

| 路径 | 结果 |
|---|---|
| 5173 网关登录（demoadult） | 200 + Token ✓ |
| 错账密/未知用户 | 401 带 JSON 体（不再是 403 空响应）✓ |
| 对话回合（含连续 5+ 轮） | SSE 事件完备，无 stale turn ✓ |
| 刷新页面后功能 | token 恢复接线，不再 401 ✓ |
| Python/FE/Java 门禁 | pytest 41 / ruff / typecheck / vitest 8 / build / mvn verify 全绿 ✓ |

### 提交管理（main 线，全部管理员直推）

```
7a6143f fix(practice): 无音频回合计数器同步 + 示范/提示卡只播不发送
90f6941 fix(web): SSE 携带 JWT + 启动恢复会话 token
218049a fix(auth): /error 加入 permitAll（401/404 不再被织成 403 空响应）
69b0bd4 fix(auth): Java 控制器去 /manage 前缀（网关剥离语义对齐）
1aa72e2 fix(java): 钉死 UTF-8 源码编码 + FAQ
5007caf fix(dev): 启动指引默认值对齐（DB 密码 / uv run 前缀 / FAQ）
9a0b3a6 docs: DoD 验收清单勾选
323c581 docs(worklog): M2 实施记录（踩坑 1~15）
（本条目 → 追加为最新）
```

每个修复 = 一个 commit（可回滚、可 review），无 squash 粘连；本条目单独成 commit。

---

## 2026-09-01 VocalVerse · M2 实施落地——双子拷问收敛 → 全链路实现 → 真环境联调（DoD 全绿）

### 背景

- 对组长 M2 场景对话草案（v1）派 **双子拷问官交叉拷问**（互不知晓、四层递进至穷尽）：需求/产品官 28 问（docs/15）+ 技术/架构官 37 问（docs/16），合流拍板记录 docs/17；规格修订为 docs/14 v2；实施计划 docs/18。
- 拍板关键项：答辩 M2 W3 极简版 / defense_profiles **软删+脱敏** / 回答质量改**等级标签**（避开 docs/06 §9.3 冲突）/ LLM **流式回复 + `[-META-]` 尾部标记**（修复"假流式"首声超预算）/ 覆盖度口径（5 条、命中双态、retry 作废）。

### 实施（按 docs/18 §3，3 人分工由组长一人代跑）

1. **W1 前置**：3 个 POC 脚本（scripts/poc/：edge_tts_latency / deepseek_meta / whisper_rtf）+ 8 套场景内容（data/seed/scenarios.json：4 场景×入门/进阶，每套 5 语料含中文释义）+ 幂等 seed.py（含入学测试题库 5+1）。
2. **Python**：迁移 `0002_m2_practice`（defense_profiles 新表、sessions.kind/attempts.kind/scenario_messages.action(+hint)/events.event_type(10 类)/reports.scope(+session) 五处 CHECK 扩展、sessions.profile_id SET NULL、**defense 题数复用 assigned_turns 快照**）；编排器 app/practice/（回合状态机、流式 text_delta + META 尾部拆解、评分并行、命中双态、2 级救场、会话锁、覆盖度）；答辩（异步知识包生成 6 条校验 + basis 提问依据 + `<untrusted_input>` 注入隔离 + 等级阶梯）；路由 10+（sessions/turns-SSE/reports/GET audio 鉴权+410 惰性过期/defense profiles/placement/events 幂等埋点/限流分桶）；真实客户端 DeepSeek/edge-tts/faster-whisper/讯飞 ISE（重依赖延迟导入，CI 零 Key 纪律不变）。
3. **Java**：Spring Security + jjwt 认证最小集（register/login/refresh rotation/me/service-token 内部回写）；DemoSeeder 3 画像账号（demoadult/demoteen/demosenior，密码 demo123456）；HS256 与 Python 手写验签对齐。
4. **前端**：sse.ts 重写（fetch 流解析器，6 单测）+ recorder 参数化 + 计时器 composable + auth store（pinia）+ 埋点封装；PracticeHub / PracticeView / ReportView / DefenseView / **PlacementView**（5 句+1 QA→综合分 S→水平档）；预览页平移后**删除+撤登记**（docs/13 §8 纪律）。
5. **基础设施**：compose 一键 migrate 服务（alembic+seed）、python `--workers 1` + mem_limit 2g、Dockerfile `--workers 1`。

### 验证（全部实测）

| 检查 | 结果 |
|---|---|
| Python pytest | **41 passed**（含 M2 核心 20+4 seed+10 类事件防漂移）；ruff check + format ✓ |
| Java `mvn verify` | BUILD SUCCESS（认证流程 3 用例 + 既有 5）；契约快照已重刷 |
| 前端 | typecheck / lint / vitest **8 passed** / **build ✓**（p5 独立懒加载 chunk） |
| 契约 | python/java 双快照已重生成，gen:api 零 diff 口径保持 |
| **真 PG** | alembic upgrade head（0001+0002）✓；**alembic check 零 diff**（首次启用） |
| **真环境联调**（scripts/poc/integration_check.py） | Java 登录→Python 验签互通 ✓ →场景 8 套/会话 ✓ →**真实 whisper 转写完整无误** ✓ →真实 edge-tts 4 段音频+回放鉴权（200/越权 401）✓ →报告 ✓ →埋点 SQL 核对（8 类非零）✓ |
| POC-1（edge-tts 延迟） | 单句 mean **1.34s** / 3 句串行 4.12s → **FAIL 判据**，回退方案生效：并发预热+预合成开场，首声口径 3~6s |
| POC-3（whisper RTF） | mean RTF **0.328**（短）/ **0.258**（长）→ **PASS**，演示话术「3~5s」成立 |

### 踩坑记录（本轮重点，务必留存）

1. 🚨 **alembic check 首次真 PG 即崩（上游不兼容，最大坑）**：SQLAlchemy 2.0.52 反射 PG16 **identity 列**为 `server_default=Identity()`，alembic `_user_compare_server_default` 对其 `cast(...).arg.text` → `AttributeError: 'Identity' object has no attribute 'arg'`（1.18.5/1.19.1 均复现，降级无解）。**处置**：env.py `compare_server_default=False` 规避 + docs/06 §10 登记；补偿门禁=offline PG 渲染测试 + 本轮真 PG 零 diff 实测；上游修复后恢复 docs/11 Q-A06 自定义比较器。**教训：迁移门禁必须真 PG 跑一次，离线渲染测试测不出运行时崩溃。**
2. 🚨 **`services/python/.env` 里的 `APP_JWT_SECRET` 与 Java 默认值不一致 → Python 401「invalid token」**：JWT 互通联调失败时，单进程 decode 正常、运行中服务 401——查半天是**本地 .env 覆盖了 pydantic 默认值**（secret=change-me，仅 9 字节）。**处置**：两端默认值统一为 `vocalverse-dev-jwt-secret-0123456789abcdef`（≥32 字节，JJWT 硬性要求 256bit，弱密钥会 WeakKeyException）；.env.example 同步。**教训：联调类问题先核对"默认值 vs 本地 .env 覆盖"，再怀疑代码。**
3. **edge-tts 逐句延迟超标**：单句 1.34s（网络往返+合成），3 句串行 4.12s——按句串行 TTS 会把回放拖垮。**处置**：逐句**并发合成** + 开场/常用句预合成 + 首句文本到达即启动。首声预算重估 3~6s（docs/06 §8 已登记实测值）。
4. **HF 模型下载 xet 通道 401**：`cas-server.xethub.hf.co` 返回 401。**处置**：`HF_HUB_DISABLE_XET=1` 强制经典 HTTP 下载。**教训：新 pipeline 的下载通道要标注可绕过变量。**
5. **SQLite vs PG 时区/事务差异**：① SQLite 返回 naive datetime 与 `now(UTC)` 相减 TypeError → started_at 归一化；② SQLite 单连接（StaticPool）下"外层 turn 事务未提交 + 嵌套 complete_session 新会话"→ 事务冲突 → 嵌套调用前先 `db.commit()`。**教训：跨方言/双会话路径，单测（sqlite）跑通 ≠ PG 无虞，两处都要在测试断言里覆盖。**
6. **seed 测试被同库污染**：共享 in-memory 引擎里其它用例插入的场景让 `count==8` 断言变 10。**处置**：seed 测试用独立引擎 fixture。**教训：测试间的共享 DB 状态要显式隔离。**
7. **测试命中 Redis 限流**：本地 Redis 在跑（容器），`_redis_consume` 的 incr 跨进程累计 → 单测 6 轮跑完 LLM 桶 429。**处置**：`get_redis()` 在 `APP_TESTING=true` 时直接返回 None（内存后端），测试 hermetic。
8. **ffmpeg 缺失挡真实 ASR**：WinError 2；winget 需管理员。**处置**：asr.py 支持 `FFMPEG_BIN` 环境变量，本机用 pip 包 imageio-ffmpeg 的二进制路径（免管理员）。
9. **JJWT 弱密钥**：`change-me` 仅 72 bit→`WeakKeyException`；统一 ≥256bit 长密钥（与坑 2 同源）。
10. **Spotless 挡 verify**：新增 Java 文件未格式化 → `mvn verify` 在 check 阶段挂；先 `mvn spotless:apply` 再 verify；契约快照须 `CONTRACT_SNAPSHOT_GENERATE=1`（**环境变量**而非 -D！）重生成。
11. **vitest include 只匹配 `*.test.ts`**：`sse.spec.ts` 不收集（一直"2 passed"骗了人）；改为 `.test.ts`。SSE 多 `data:` 行语义是按行+换行拼接为一条消息，JSON 内含未转义换行会解析失败——测试用"尾随空行"聚合场景。
12. **GBK 控制台打印 emoji 崩**：`UnicodeEncodeError 'gbk' codec can't encode '\u2705'`（脚本尾打印 ✅）。**处置**：脚本输出用 ASCII 或 `$env:PYTHONIOENCODING='utf-8'`。
13. **常量导出**：`app.models` 只再导出表（不导出 SessionKinds/EventTypes 等常量）→ 多处 `from app.models import ContentStatus` ImportError，统一从 `app.models.base` 导入。
14. **后知后觉的 schema 缺口**：`reports.scope CHECK` 原为 ('global','user','scene','song')，会话级报告无处落袋 → 0002 迁移一并扩 'session'；`scenario_messages.action` 需 +'hint'（v1 草案漏项，拷问官抓到）。
15. **abandon 早退分支不产报告**：调收尾前必须释放外层 DB 事务，且该分支自身不落任何消息——用户点"结束"要直接走 complete_session（冒烟脚本抓到）。

### 提交

- 分支 `feat/m2-implementation`（9 个 commit 已推送，最新 `118b507`）；文档链 docs/14(v2)/15/16/17/18 与 README 索引同步；按组长授权管理员直推 main（跳过 PR 评审）。

---

## 2026-08-31 VocalVerse · 同构 Monorepo 参照对比评审——双子拷问官交叉拷问 + 拍板（不照搬、补 .dockerignore、契约生成化）

### 背景

- 组员提问：「admin/frontend/server 三个服务能按某同构 monorepo 参照项目那样做吗，是否会更清晰？」（动机确认＝要架构清晰、维护少混乱）。
- 参照项目＝同构 pnpm monorepo：2 前端（frontend+admin）+ 1 后端（NestJS+Prisma）+ 共享包（types/sdk/ui/utils）+ 独立 nginx 网关 + 根 compose；**外部项目，名称不入库**（见 docs/12 头部注记）。
- 方法论：资深架构初评 → 双拷问官交叉拷问（技术官 × 语境官），各自多轮递进至**问询穷尽**，两官独立得出同一评级「基本支持但需修正」。

### 关键拍板（5 项）

1. **不照搬**：参照项目清晰度源于同构（单语言/单契约源/单后端）；本项目＝1 前端 + 2 后端（Python/Java 课程强约束），`pnpm -r` 编排不了 Python/Java。
2. **拒 workspace 的真实依据**＝docs/08 Q9（单前端不用 pnpm workspace）+ docs/06 §10.1（Prisma 先例：同构工具链收益无法迁移到异构栈）——**不是 AD-01**（AD-01 只拍板目录命名，为其引证即引错锚点）。
3. **网关已存在**：apps/web/nginx.conf 即唯一入口（/api/v1/→python、/manage/→java、/healthz、/readyz），前端全走同源相对路径，无 CORS 问题；**不新增独立网关容器**。
4. **管理端 UI ＝ apps/web 内 /admin 路由 + admin 角色**，不建独立 SPA（管理端最小集仅 3 能力；docs/04 无独立管理台里程碑）。
5. **契约痛点才对症**：跨语言改契约→手工同步前端类型是唯一真实痛点，workspace 解决不了，**只有 OpenAPI 构建期生成前端类型能解**（docs/06 §7 已改写，动作 C 当日落地）。

### 实施

- `docs/06`：§2.1 布局演进注记（5 条，不推翻 AD-01）+ §7 codegen 口径澄清（"不做运行时 codegen"≠"不做构建期生成"）+ §14 修订说明登记。
- `docs/12-同构Monorepo对比与裁决.md`：双拷问官完整交付物归档（对照表/问题清单/行动清单/答辩口径/穷尽声明；参照项目名称不亮明）。
- **补 3 个 `.dockerignore`**（P0，此前全库缺失）：`services/python`（.venv≈1.1GB）、`services/java`（target≈55MB）、`apps/web`（node_modules≈121MB）此前全部进 build context——per-service context 只是"分开污染"非"躲开体积"。
- `/manage` 两处一致性守护：nginx（proxy_pass 尾斜杠剥离）与 vite.config.ts（rewrite）互指注释。
- README 文档索引补齐 10/11/12。
- **动作 C（契约生成管线，当日落地）**：① Python 侧契约定型——`app/audio/base.py` 增 `TTSResult`/`ChatResult`，4 条 stub 路由返回注解从 `Envelope[Any]` 改为 `Envelope[ASRResult/ScoreResult/TTSResult/ChatResult]`（OpenAPI 随出真 schema）；② 前端管线——`pnpm gen:api`（openapi-typescript 7.13）从契约快照 `src/api/specs/python-openapi.json` 生成 `src/api/generated/python-api.d.ts`（均入库），`client.ts` 的 asr 数据改为消费生成类型；③ 后端改契约后 `pnpm gen:api` 重跑 + typecheck 立即暴露断点。**CI 双关卡**：python-ci 增「契约快照 vs 后端 `app.openapi()` 一致性」（本地实测 MATCH）；frontend-ci 增「`pnpm gen:api` 重跑后生成文件零 diff」；开发侧一步刷新 = 新增 `scripts/refresh-openapi.ps1`。
- **脱敏**：参照项目为企业项目，名称已全库清理（含 git 历史核查，历史无引用）；docs/12、docs/06 §2.1/§14、README、worklog 一律以「同构 monorepo 参照项目」指代。
- **trace 透传（可观测性，动作 F 落地）**：nginx（`$request_id` 兜底生成 + /api/v1 /manage /healthz /readyz 四 location 透传 + 响应头回写）→ Python（`app/core/trace.py` 纯 ASGI 中间件，兼容 SSE 流式；ContextVar + 日志 filter，每条日志带 request_id）→ Java（`RequestIdFilter` 写 MDC + logback 模式 `%X{requestId}`）；三端各配测试（py 2 条 / java 2 条）。docs/06 §11 承诺补齐为"已落地"，loguru/logback JSON 结构化列为 M2 待办。
- **Java 契约对账（契约三关卡闭环）**：`apps/web/src/api/specs/java-openapi.json` 快照（初始由 `CONTRACT_SNAPSHOT_GENERATE=1` 跑 `ContractSnapshotTest` 生成）+ 该测试在 `mvn verify` 内用 springdoc MockMvc 实时渲染对账（servers 归一化排除）；`gen:api` 增 `java-api.d.ts`；`refresh-openapi.ps1` 升级为 4 步（Python+Java 双快照导出 + 双类型生成）；java-ci 触发路径补快照/生成文件。
- **M1 遗留修复：Java 裸返回违规 envelope（2026-09-01 重点）**：`PingController` 原返回裸 `Map{status,service}`，前端 `request()` 强制 `code===0` 检查 → `body.code` 为 undefined → **演示页"Java 不可达"永远是假的（服务一直健康）**。修复：新增 `common/dto/Envelope<T>`（record + ok/error 工厂），ping 改为 `Envelope<PingData>`；契约快照/生成类型重刷（新增 `PingData`/`EnvelopePingData` schema）；`client.ts` 的 `PingData` 改由生成契约导入。**教训：Java 任何接口必须过 Envelope（docs/06 §7 实现欠账，M2 前补齐）；排查"不可达"先看响应体有无 envelope，再看网络层**。
- **前端设计系统定版（docs/13）**：拍板 naive-ui + UnoCSS + 设计 token（三层分工）、B 多邻国活力配色（绿主色/柠檬黄激励/橙评分，本期仅浅色）、可视化栈 ECharts（报表）+ P5（仅品牌动效）+ D3（仅唱歌细图）、**Three.js 不引入**（docs/06 §9.2 2D 数字人拍板）。落地：`styles/tokens.ts`（token 唯一来源）+ `styles/theme.ts`（naive themeOverrides）+ `uno.config.ts` + 路由全表（`router/index.ts`，M2/M3 页面用占位页收敛）+ `UserLayout`/`AdminLayout`（管理端单 SPA 内路由）+ `LoginView`（P5 声波动效，懒加载+降级）+ `DemoView`（原演示页迁移 `/demo`）+ vitest 换 happy-dom（docs/09 P1-#10）。**两个版本坑**：vue-router 5.x 要求 Vite 7 → 钉 ^4.6；p5 2.x 与 @types/p5 1.x 类型不匹配 → 钉 ^1.11。版本已登记 docs/06 §3。
- **预览机制底座（docs/13 §8）**：`/preview` 画廊（`router/preview.ts` 整个子树包在 `import.meta.env.DEV` 三元内——**生产构建验证零 chunk**）+ 画廊布局（分组菜单 + DEV ONLY 标注 + 流程说明）+ 注册表 `views/preview/registry.ts`（新增页两步：加路由 + 登记）+ 5 张高保真预览页（学习主页 / 场景对话★★ / 评分报告 / 评价看板·ECharts / 用户管理）+ `useECharts` 懒加载封装（core/charts/components/renderers 全动态 import、ResizeObserver、dispose）。**明天群流程即可直接开工：在画廊里新增预览页画图 → 验收 → 平移集成。

### 验证

- [x] docs/06 三处编辑落位（§2.1 / §7 / §14）；docs/12 创建；README 索引更新；**外部参照项目名称（中/英文）全库零匹配（含 git 历史）**。
- [x] Python：`pytest` 15 passed；`ruff check` + `format --check` 通过（契约响应模型改动）。
- [x] 前端：`typecheck / lint / test:run(2 passed) / build` 全绿；`pnpm install --frozen-lockfile` 通过（CI 同款）。
- [x] **Java `mvn verify` 全绿**（spotless + 测试：含 `ContractSnapshotTest` 快照对账、`RequestIdFilterTest` 2 用例）。**Python `pytest` 17 passed**（含 trace 2 用例）、ruff 全过。**前端 `gen:api` 双文件生成 + typecheck/lint 全绿**。
- [x] **前端设计系统骨架验证**：`pnpm typecheck / lint / test:run(2 passed) / build` 全绿；chunk 健康——p5（1MB）独立 chunk 仅登录页懒加载，naive-ui 主包 266KB（gzip 90KB），无首屏重依赖。
- [x] **契约比对本地实测**：快照 vs `app.openapi()` → MATCH（CI 双关卡口径已核）；`scripts/refresh-openapi.ps1` 语法/路径核过（未实跑——需后端在跑）。
- [x] `.dockerignore` 生效性：`docker compose build` 下一轮构建验证（本次未重建镜像）。
- [x] vite/nginx 注释为纯注释，不影响 `pnpm typecheck/build` 与 nginx 语法（`nginx -t` 下次容器构建验证）。
- [x] git 工作区仅新增/修改上述文件，无密钥类文件。
- ⚠️ 注意：`pnpm add -D openapi-typescript` 时 pnpm 将锁内 vite 6.0.x→6.4.x、vitest 3.0.x→3.2.x、vue-tsc 2.1.x→2.2.x 等解析为区间内最新（锁文件 v9.0，与 CI 的 pnpm 9.12.1 兼容；构建/测试已验证）。版本纪律：本次属于区间内自动刷新，非人为升级；下次按 docs/06 §3 季度纪律统一执行。

### 待办（M2 起）

- [x] 动作 C：`openapi-typescript` 构建期生成前端类型（生成文件入库 + CI typecheck 兜底）。
- [x] 动作 F：X-Request-Id 全链路透传（nginx 注入 + Java filter + Python middleware）——已落地，各端有测试。
- [ ] 动作 D：/manage 一致性 CI 冒烟断言。
- [ ] 动作 E：docs/04 为 `/admin` 管理台路由排期。

## 2026-08-31 VocalVerse · 数据库表设计落地（19 表）+ 双子代理拷问 42 问收敛

### 背景

- M2 前的前置性工作：数据库表结构设计（按 docs/06 §10 表清单 + docs/08 Q37~Q39 + docs/09 §4.3），用 **Alembic 作为管表结构演进的唯一工具**，并**按约定做好每张表的「写归属」（Single-Writer）**。
- 流程：先设计完成（未提交）→ 开**两个子代理火力拷问**（① schema-迁移工程官 ② 业务域-写归属官，合计 **42 问**）→ 按结论整改 → 全量验证 → 本日志记录后提交推送。

### 产出

- **19 张表**：docs/06 §10 清单 15 张 + 补充 4 张（`song_pitch_refs` 参考旋律、`listening_materials` 听力素材、`placement_questions` 入学题库、`post_likes` 社区点赞），补充依据均来自 docs/06 已拍板口径（§9.2/§9.4/§9.5/§9.6）。
- `services/python/app/models/`（SQLAlchemy 2.0 typed + naming_convention + `jsonb()` JSONB variant + `bigint_pk()` SQLite 变体）；`docs/10-数据库设计.md`（表清单 + **写归属矩阵** + 契约 + 开放项裁决）。
- `alembic/env.py`（metadata 挂载、compare_type、自定义 server_default 比较器）、`alembic.ini`（纯 ASCII 化）、`alembic/versions/0001_initial_schema.py`（19 表初始迁移，upgrade/downgrade 双向离线渲染可编译）。
- `tests/test_models.py` 15 用例（19 表 create_all / CHECK 与唯一索引探针 ×5 / 单头 / 升级+回滚离线渲染）；python-ci 单头断言收紧 `-le 1` → `-eq 1`；compose/测试/环境变量统一 `APP_DATABASE_URL`、`APP_REDIS_URL`。

### 拷问结论（42 问：A 官 19 + B 官 23，详见 docs/11）

- **三大疑点**（组长视角已拍板）：入学题库**必建表**（placement_questions，Java 写，exam_revision 版本化）；协同过滤模拟矩阵**不建表**（`data/seed/reco_demo.csv`，demo 验证产物）；社区最小版**只建 post_likes 一张**（点赞不可推导；打卡/动态流派生）。
- **B 官最重一击**：四指标口径「普遍悬空」——CTR 缺 impression→click 关联键、唱歌完成率缺判定存储、互动率分母缺字段。已补：`events.browse_session_id/recommend_group_id/page/target_type/target_id/server_offset_ms`、`sing_attempts.is_complete/expected_lines/lrc_id`、`sessions.user_turn_count/assigned_turns`、`origin` CHECK 收紧为「仅 user 行可带」。
- **A 官验收**：19 表模型 vs 迁移**逐字段核对完全一致**（唯一差异为刻意重映射的时间戳默认值书写）；FK 建表顺序与 downgrade 逆序满足依赖；单头线性。

### 踩坑记录（本日最有价值的部分）

1. **alembic.ini 中文注释在 GBK locale Windows 上崩**：`configparser` 用 locale 编码读 ini（`encoding="locale"`），GBK 机器读 UTF-8 注释 → 所有 alembic 命令本地直接炸；CI 是 Linux（UTF-8）所以 M1 全绿是「假绿」。**处置**：ini 保持纯 ASCII + `path_separator = os`；凡是 configparser 消费的配置文件一律 ASCII。
2. **纯 `BIGINT` 主键在 SQLite 不是 rowid 别名** → 单测 INSERT 报 `NOT NULL constraint failed: id`；`create_all` 不报错（DDL 层 OK）、插数据才暴露。**处置**：`BigInteger().with_variant(Integer, "sqlite") + Identity()`，PG 仍 `BIGINT IDENTITY`（探针验证）。**教训**：SQLite 兼容要测「建表 + 插入」两步，不能只测 create_all。
3. **`server_default` 裸字符串被当裸 SQL**：`server_default="normal"` 渲染成 `DEFAULT normal`（未加引号！），`DEFAULT []` 在 PG 直接非法。**处置**：一律 `text("'...'")` 显式引号。
4. **`.gitignore` 裸 `models/` 静默吞掉 schema 模型**：无 `/` 锚定的目录规则匹配任意层级 → `services/python/app/models/*.py` 整个不入库（`git status` 看不见！）。**处置**：改为 `/models/` 锚定；**教训**：`git check-ignore` 与 `git status --untracked-files=all` 是新目录入库前的必查动作。
5. **autogenerate 静默跳过表达式唯一索引**（`lower(username)`）：SQLite 方言无法反射表达式索引 → 生成的迁移**不含**用户名大小写不敏感唯一索引，直接提交=唯一性丢失。**处置**：人工补 `op.create_index(..., [sa.text("lower(...)")], unique=True)` 并在测试断言。
6. **`text("now()")` 在 SQLite 是运行时雷**：`DEFAULT now()` 建表能过、INSERT 时「no such function: now」才炸（SQLite 对默认值函数调用延迟求值）。**处置**：统一 `func.now()`（SQLite 编译 `CURRENT_TIMESTAMP`）。
7. **id 命名双轨（DATABASE_URL vs APP_DATABASE_URL）**：pydantic `APP_` 前缀 vs compose/env.py/测试用裸变量 → M2 一接真引擎，**Python 服务连 SQLite、迁移跑 PG**（schema 静默分裂）。同坑还有 `REDIS_URL`。**处置**：全链路统一 `APP_` 前缀变量。
8. **属性名遮蔽模块函数**：`Lrc.text`（列名 text）遮蔽 `sqlalchemy.text()`，同 class body 内后续 `server_default=text(...)` 全部解析成 MappedColumn 崩溃（`TypeError: 'MappedColumn' object is not callable`）。**处置**：属性改名 `line_text`（DB 列名不变）。
9. **Numeric 列注解 float vs 运行时 Decimal**：`Mapped[float]` + `Numeric(5,2)` → 运行时返回 Decimal，与阈值比较 TypeError、JSON 序列化口径混乱。**处置**：统一 `Decimal` 注解。
10. **IDENTITY 序列不与显式 ID 同步**：seed 写 id=1/2/3 后注册拿 id=1 → PK 冲突；`ON CONFLICT DO NOTHING` 不解决。**处置**：契约写入 docs/10 §7.3（seed 不写显式 ID 用 `lastval()`；必须写则 `setval(pg_get_serial_sequence(...))`）。
11. **CI 单头断言 `-le 1` 假绿**：0 头（脚本损坏/迁移缺失）也被判过。**处置**：`-eq 1`（项目必有初始迁移）。
12. **迁移 docstring 修订头重复 / downgrade 忘写**：离线渲染只出 upgrade，必须人工补降级与文档头。**处置**：组装脚本推导逆序 downgrade + 测试断言 DROP TABLE 数。

### 验证（全绿）

- pytest **15 passed**（19 表 create_all；CHECK/表达式唯一/幂等键/origin/channel 探针；alembic 单头；upgrade/downgrade 离线渲染）；ruff / mypy 干净；`alembic heads` = `0001 (head)`；PG 方言离线 SQL：upgrade 19 表 + JSONB + IDENTITY，downgrade 19 表逆序 + 32 DROP INDEX。

### 待拍板（不阻塞 M2）

- ① seed 单写豁免 vs 用户种子移 Java `CommandLineRunner`（严格单写）；② 容器内迁移执行方案三选一（compose 一次性 migrate 服务 / 启动前置迁移 / 手动文档化）——M2 联调前必须落地；③ M2 接 PG 首日 `alembic upgrade head && alembic check` 接入 CI（with_variant/表达式索引噪音 diff 验证预案放 docs/07 架构官报告 Q-A04/05）。

---

## 2026-08-31 VocalVerse · 框架评审（docs/09）审阅与整改落地

- 收到另会话产出的 `docs/09-技术框架评审.md`（总评 A-，不主张替换技术栈）；逐条核验证据后**大部分采纳**，3 处修正评审意见（P0-#2 延迟预算按场景分层而非一刀切；P1-#7 无 Redis 不拒绝启动、改为 degraded 模式；P2-#13 探针修复后已非空转）。
- 落地整改：nginx `client_max_body_size 20m`；python-ci 探针改**单头断言**（0 头=暂允、多头=红）+ 新增 `uv lock --check`；Dockerfile 移除 `|| uv sync --no-dev` 回退；新建 `infra/`（含 `.wslconfig` 示例）；docs/06 补「并发与线程模型 / 模型缓存卷+预热 / 分层延迟口径 / sklearn joblib 一次训练 / JSONB with_variant / Redis 降级行为 / 升级纪律」；docs/09 追加处置记录（采纳/修正/汇总）。
- 过程教训：自己写的 CI 断言差点引入「0 头迁移=失败」的误伤——**断言场景要考虑空态**（0 头允许、多头拒绝）。

---

## 2026-08-31 VocalVerse · 补录：docker-build CI 三连坑修复（cache 驱动 / ghcr 小写 / YAML 块标量注释）

### 背景

- PR #1（M1 骨架）合入 main 后，`docker-build`（push 到 main 触发）失败：web job 8s 失败，另两个 matrix job 被 fail-fast 级联取消（用户看到的「2 cancelled / 2 successful / 1 failing」）。
- 排查方法：`gh run view <id> --log-failed` 逐层定位，三层都是配置级错误，非代码问题。

### 坑 1 · GHA 缓存需要 buildx docker-container 驱动

- **症状**：`ERROR: failed to build: Cache export is not supported for the docker driver.`
- **根因**：`docker/build-push-action` 的 `cache-to: type=gha` 依赖 BuildKit 的 `docker-container` 驱动；runner 默认 buildx 的 `docker` 驱动不支持 GHA 缓存导出。
- **处置**：去掉 `cache-from/cache-to`（M1 镜像小、缓存收益低），注释说明；如以后要缓存，先 `docker buildx create --driver docker-container --use`。

### 坑 2 · ghcr tag 的 owner 必须小写

- **症状**：`invalid tag "ghcr.io/LHRCarrier/vocalverse-python-api:latest": repository name must be lowercase`
- **根因**：`github.repository_owner` = `LHRCarrier` 含大写；Docker 仓库名规范要求全小写。
- **处置**：tags 写死小写 owner `ghcr.io/lhrcarrier/...`（注释提醒仓库迁移时同步）。

### 坑 3 · YAML 块标量里的 `#` 不是注释（本日最典型，自己埋的）

- **症状**：`invalid tag "# 注意：Docker 仓库名必须小写；..." : invalid reference format` —— tag 直接变成了注释文本。
- **根因**：把 `#` 注释写进了 `tags: |` **块标量内部**；YAML 中块标量（`|`/`>`）内容是字面文本，`#` 不生效（缩进正确与否无关）。
- **处置**：注释移到块外；并建立校验动作——**改完 workflow YAML 必须解析验证其值**：`uv run --no-project -p 3.12 --with pyyaml python -c "import yaml; print(yaml.safe_load(open('.github/workflows/docker-build.yml', encoding='utf-8')))"`，只凭肉眼缩进是看不出来的。
- **纪律**：`with:` 下的多行字符串（`|`/`>`）除目标内容外不得含任何其他行；注释一律放块外；提交前解析校验 + 看实际日志确认。

### 验证

- 修复链：PR #15（去缓存）→ PR #16（owner 小写）→ PR #17（块标量注释外移），均管理员绕过合入；
- 最终 run `33370144948`（sha `27381ce`）**success**：python-api / java-api / web 三镜像全部构建并推送 GHCR；
- 附带发现：runner 警告 Node.js 20 弃用（checkout@v4 等被强制跑 24），记录待后续升级 action 版本时处理。

---

## 2026-08-31 VocalVerse · M1 框架从零搭建——双子代理拷问收敛 123 问 + 三端骨架落地 + 全链路验证通过

### 背景

- 项目从零开始（仓库只有 docs 规划层，无代码）；目标是先搭**成熟技术框架**再进功能开发。按案例 #7 原文（后端 Python+Java、前端 Vue、模型 PyTorch/TensorFlow、Scikit-learn 推荐）搭建，需求与选型矛盾多，先拷问后动手。
- 采用「需求拷问官 + 技术架构拷问官」双子代理火力拷问（合计 **123 问**），组长拍板 6 项关键分叉，随后落地 M1 骨架并逐端验证。

### 关键拍板（6 项）

1. **拓扑**：语音热路径直连 Python；Java 只做管理端 + JWT 签发（不进语音/SSE 热路径）；
2. **语法评分**：暂定 DeepSeek LLM 判定转写文本（0-100 + 错误类型）；不稳定则回退砍项、口径改「发音/流利度/完整度」；
3. **自研评分门禁化**：冻 wav2vec2 backbone 只训评分头（GPU 5~10h、约 ¥20~40）；门禁 = M3 的 P0/P1 全绿 + 验证集 r≥0.8 且 MAE 达标，检查点 M3 第 2 周周末；不达标回退讯飞基线；
4. **M3 取舍**：唱歌做深（音准/节奏/发音逐句评分），推荐/报表演示化（预置模拟行为矩阵验证「生效」）；
5. **社区最小版**：打卡 + 成绩卡片 + 只读动态流 + 点赞；不做双人实时对练（答辩口径「分享+激励」）；
6. **前端 TypeScript strict**。

### 实施

**1. 决策文档**：`docs/06-技术框架决策.md`（16 章：拓扑/目录/版本矩阵/质量链/CI/测试/契约/音频与流式/功能口径/DB/安全/Windows 对策/门禁/修订说明/风险回退/M1 清单）；并修正 `docs/01`「三项指标」→「四项指标」。
**2. 功能口径定稿**（写入 docs/06 第 9 章，团队照此开发）：四项检查点指标精确定义（CTR=推荐曝光 30min 内点击去重/曝光；完成=口语 5 轮或 2min、唱歌整首；跳出=进页 30s 无有效事件；互动率=主动发消息轮数/分配轮数）+ 9 类埋点事件；水平 4 档 L1~L4（综合分 S=0.4发音+0.3语法+0.3流利度，≥85/70~84/55~69/<55）；入学测试 = 5 固定朗读句 + 1 轮 QA（admin 题库）；场景 4~5 个、会话 5~8 轮/2~3min；唱歌映射表与综合 = 0.5音准+0.2节奏+0.3发音（发音复用口语引擎）。
**3. Monorepo 骨架**：`apps/web` + `services/python` + `services/java` + `infra` + `docs` + `scripts`；根配置 `.editorconfig`/`.tool-versions`/`.nvmrc`/`.env.example`/`.pre-commit-config.yaml`（纯 Python 钩子，Windows 可用，禁 *.sh）/`docker-compose.yml`（5 服务 + healthcheck + 依赖顺序，Web 映射 8088 避 80 端口权限）。
**4. CI/CD**：frontend-ci / python-ci / java-ci / secret-scan / docker-build 五件套 + PR 模板（敏感数据检查项）+ CODEOWNERS + dependabot；与 docs/05 分支保护（1 人 review、squash、dismiss stale）配合；**CI 零真实 API Key**（ASR/TTS/评分/LLM 全走 stub）。
**5. Python 服务**：Pydantic Settings（APP_ 前缀）、Envelope/错误码、`healthz/readyz`、音频 stub 路由（asr/score/tts/llm-chat，上传 20MB 上限 41301）、`app/audio/base.py` 四个抽象接口 + `stubs.py` Fake（M2 只改实现，不改签名）、Alembic 骨架（唯一 schema 真源）、Dockerfile（slim + ffmpeg）。
**6. Java 服务**：Spring Boot 3.3.5 / Java 21 / Maven + Spotless（google-java-format）；`ddl-auto=none`；H2 测试配置 + PingController + 2 测试；双阶段 Dockerfile。
**7. 前端**：Vue 3.5 + TS strict + Vite 6 + pnpm；`api/client.ts`（envelope 解析、`request<T>` 可切 Python/Java base）；`audio/recorder.ts`（MediaRecorder → WebM/opus，60s/20MB，录完再传）；`audio/sse.ts`（text_delta/audio_chunk/done 协议，音频为时间轴权威、文本为字幕）；`App.vue` 演示页（三服务连通 + 录音→stub 转写冒烟链）；nginx 容器（SPA + SSE 反代 buffering off）。
**8. 契约与脚本**：`docs/api/envelope.md` + `error-codes.md`（错误码表）；`scripts/dev.ps1`（幂等 + 端口检测）、`scripts/bootstrap.ps1`（工具链自检）；音频/模型延迟口径 = 7~10s 出第一声，演示话术「录音后 3~5 秒反馈」（不承诺实时）。

### 验证（全部实测）

| 检查 | 结果 |
|---|---|
| `docker compose config -q` | ✅（修 env_file 后通过） |
| Java `mvn -B -ntp verify`（含 Spotless） | ✅ BUILD SUCCESS |
| 前端 `pnpm lint / typecheck / test:run / build` | ✅ 全绿（vitest 2 passed；dist 66.7KB/gzip 26.9KB） |
| Python `ruff check` + `format --check` + `pytest` | ✅ 6 passed（ephemeral env，未装 torch） |
| `uv lock`（101 包）/ `pnpm-lock.yaml` | ✅ 已生成，CI `--frozen` 可复现 |
| `.gitignore` 豁免实测（`git check-ignore`） | ✅ 种子/夹具可提交，产物被忽略 |

### 实施中踩坑（务必留存）

1. 🚨 **`.gitignore` 裸后缀黑名单是第一天就埋的雷**：原文件用 `*.wav/*.lrc/*.csv` 与整目录 `data/` 黑名单，歌曲库 LRC 种子、埋点 CSV、音频测试夹具全被静默忽略，M1 提交卡死。**处置**：改按路径忽略（`data/audio/`、`models/`、`*.pth` 等）+ 显式豁免（`!data/seed/**`、`!**/*.lrc`、`!**/tests/fixtures/**`，豁免规则放忽略规则之后）。**纪律：改 .gitignore 必须用 `git check-ignore -v` 实测**。
2. 🚨 **vitest 2.x 与 Vite 6 类型冲突（前端踩坑，最耗时）**：vitest 2.1.9 内部绑定 vite@5 类型，`vite.config.ts` 从 `'vitest/config'` 引入 defineConfig 后与项目 vite@6 的 `PluginOption` 撞型；`pnpm typecheck --noEmit` 不爆、只有 `vue-tsc -b`（build）爆。**处置**：vitest 升 `^3.0.0`，build 立即通过。**纪律：升级 Vite 主版本必须同步升级 vitest；CI 以 build 为准**。
3. **FastAPI 响应校验按「返回注解」执行**：路由声明 `-> dict` 但返回 Envelope → `ResponseValidationError`（loc=response）。注解改为 `-> Envelope[Any]`。**教训：FastAPI 返回注解不是文档，是响应模型**。
4. **Stackless 细节**：`EventSource` 无 `onclose` 属性（收尾逻辑放 onerror/done）；`vite.config.ts` 需 `@types/node` + tsconfig.node.json `"types":["node"]`；Python `on_event("startup")` 已弃用 → 改 lifespan。
5. **Python 依赖**：`[tool.uv] package = true` 会让 uv 尝试打包应用（无 build-system 报错）→ **`package = false`**；torch 走 pytorch-cpu 显式 index（**只装 CPU 轮子**，训练在云 GPU 隔离环境）；**不引 crepe/TensorFlow**（pyin 基线，TF 是纯负担）；`uv.lock` 必须提交否则 CI `--frozen` 失败；python-ci 需 dev 组（pytest/ruff）→ `uv sync --frozen` 不要 `--no-dev`。
6. **双后端/schema 纪律**：Alembic 唯一 schema 真源，Java `ddl-auto=none` 只映射；CI 加 alembic heads 一致性探针。
7. **本机验证环境**：Windows 只有 Python 3.7 → 用 `uv python install 3.12` 托管解释器 + `uv run --no-project -p 3.12 --with …` 拉轻量依赖跑 pytest（回避 200MB torch）；`uvx ruff` 直接跑 lint/format。
8. **其余小坑**：`docker compose` 的 `env_file: .env` 不存在会 config 失败 → `- path: .env` + `required: false`；Spotless 首次必挂 → 先 `mvn spotless:apply`；CI 用 runner 预装 Maven（`mvn`），`mvnw` 本地 `mvn -N wrapper:wrapper` 生成一次；ESLint 模板换行风格规则过严 → 显式关闭纯风格项；proxy 需单独加 `/healthz`、`/readyz`（健康检查在根路径，不在 /api/v1 下）。

### 备注

- 双子代理完整拷问原文已归档：`docs/07-需求拷问报告.md`（63 问 + 38 条 ADR）、`docs/08-技术架构拷问报告.md`（60 问 + AD-01~40）；拍板结论见 docs/06，本日志为当日执行记录。
- 合规红线（docs/06 9.7）：录音默认不持久化（24h TTL）、demo 歌曲用公有领域/自创曲目、模型权重用 setup 脚本下载、密钥只进 .env。
- 变更尚未提交；按 docs/05 应走 `feat/m1-scaffold` 分支 + PR（建议分 2~3 个 PR：ci+根配置 / python / java+web）。

### 提交与推送

- 未提交。建议：`git checkout -b feat/m1-scaffold` → 3 个 PR → 1 人评审 → squash 合入 main（CI required checks 生效后合并即全绿）。
- ⚠️ 本文件为团队可见（已从 .gitignore 移除），内容已脱敏：无任何密钥/真实数据。
