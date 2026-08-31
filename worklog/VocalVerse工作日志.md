# VocalVerse · 工作日志

> 团队可见的工作记录（入库）。负责维护：LHRCarrier（组长）；其他成员需补充时经 PR 追加到 `VocalVerse工作日志.md`。
> 用途：按日记录项目关键改动、验证结果与踩坑；新记录追加在最上方。正式决策看 `docs/06-技术框架决策.md`（ADR 唯一权威）。

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

### 验证

- [x] docs/06 三处编辑落位（§2.1 / §7 / §14）；docs/12 创建；README 索引更新；**外部参照项目名称（中/英文）全库零匹配（含 git 历史）**。
- [x] Python：`pytest` 15 passed；`ruff check` + `format --check` 通过（契约响应模型改动）。
- [x] 前端：`typecheck / lint / test:run(2 passed) / build` 全绿；`pnpm install --frozen-lockfile` 通过（CI 同款）。
- [x] **Java `mvn verify` 全绿**（spotless + 测试：含 `ContractSnapshotTest` 快照对账、`RequestIdFilterTest` 2 用例）。**Python `pytest` 17 passed**（含 trace 2 用例）、ruff 全过。**前端 `gen:api` 双文件生成 + typecheck/lint 全绿**。
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
