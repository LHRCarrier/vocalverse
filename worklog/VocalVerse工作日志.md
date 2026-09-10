# VocalVerse · 工作日志

> 团队可见的工作记录（入库）。负责维护：LHRCarrier（组长）；其他成员需补充时经 PR 追加到 `VocalVerse工作日志.md`。
> 用途：按日记录项目关键改动、验证结果与踩坑；新记录追加在最上方。正式决策看 `docs/06-技术框架决策.md`（ADR 唯一权威）。

## 2026-09-10 修 main 上的 python-ci：Python 契约快照缺 21 条控制台路由

- **起因**：直推 main 后 CI 报 `Some checks were not successful`——`python-ci / lint · test · alembic` 1 分钟后失败，
  其余 4 项（docker-build ×3、secret-scan）成功。

- **定位**：用 `gh run view --json jobs` 看到**失败步骤是 `Contract: OpenAPI snapshot in sync`**
  （前面 11 步全绿，含 bench 预算门禁、单写方探针、开关三处对账）。本地复现该步骤的比对逻辑：

  | 项 | 结果 |
  |---|---|
  | 快照**缺失**的路径 | **21 条 `/api/v1/console/**`**（ops 的 overview/services/concurrency/metrics/alerts/traces + library 的 books/chapters/media） |
  | `components.schemas` | 48 → 50 |
  | `/readyz` | schema 有变化 |

  即 **Python 侧控制台路由从未进过契约快照**（历史 commit `813a934` 声称"控制台 37 op 接入"，
  实际只覆盖了 Java 侧 41 条 / Python 侧 0 条）——CI 直接用 `app.openapi()` 比对，所以一推上来就红。

- **修法**：按仓内官方路径 `scripts/refresh-openapi.ps1` 刷新，然后**刻意只留两个文件**：
  `apps/web/src/api/specs/python-openapi.json`（+21 路由）+ `apps/web/src/api/generated/python-api.d.ts`（重生成）。

- **刻意回退的 5924 行**：脚本对 Java 侧是 HTTP 原文落盘（紧凑单行），而 Java 的**规范生成器**
  `ContractSnapshotTest`（`CONTRACT_SNAPSHOT_GENERATE=1`）写的是 `writerWithDefaultPrettyPrinter()` 美化版。
  实测两者 JSON **语义完全相同**（68 路径 / 92 operation / 125 schema，零增删），
  直接落盘会把提交版 5924 行压成一行 —— 纯噪音，故 `git checkout` 回退。
  两者用 `JsonNode` 比对（格式无关），所以 java-ci 不受影响。
  ⚠️ **登记工具缺陷（未修）**：`refresh-openapi.ps1` 写紧凑格式与规范生成器不一致 ——
  任何人按文档跑该脚本都会得到这次 5924 行伪 diff；修它要让脚本改走 `CONTRACT_SNAPSHOT_GENERATE=1`
  （自己缩进对不上 Jackson 的 `" : "` 分隔符），属行为变更，另立。

- **验证（实跑）**：进程内 `app.openapi()` 与快照**逐字节一致**；`pnpm gen:api` **幂等**
  （再跑一次 `git status` 无新改动，满足 frontend-ci 的 `git diff --exit-code`）；
  推 main 后**手动 dispatch** `python-ci` → **success**。
  另发现 `frontend-ci` / `admin-ci` **只挂 `pull_request` + `workflow_dispatch`**（没有 push:main），
  即主线上平时根本不会跑 → 一并手动补跑：**frontend-ci success、admin-ci success**。
  最终 `7c2a958` 上 **5/5 全绿**：admin-ci / frontend-ci / python-ci / docker-build / secret-scan。

- **踩坑（我自己踩的，记下来）**：为验证"本地 `.env` 是否影响契约"，我用
  `Push-Location` + `cd` + **相对路径** 在 `finally` 里恢复文件，结果 Pop 回的是内层目录，
  恢复语句找不到目标 → **`services/python/.env` 一度被改名成 `.env.bak`**（若就此放着，
  后续进程会读不到 DeepSeek key 而**静默走 Fake**）。已即时用绝对路径修回并校验
  （2258 字节、`APP_DEEPSEEK_API_KEY`/`APP_CONSOLE_JWT_SECRET` 均在）。
  **教训：脚本里一律用绝对路径，`try/finally` 里不要依赖当前目录。**

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（联调入口）：README 登记控制台账号 + 功能分支推送

- **需求**：把管理端账号写进 `README.md` 方便组员测试；远端直推。

- **口径裁决（没有把随机口令写进公开库）**：我先前给本机生成的是**随机 48 位控制台密钥 + 随机管理员口令**——
  属密钥类，而本仓 `AGENTS.md` 安全节与 `.env.example` 开头都明写"公开仓库永远不出现真实密钥"，
  写进去还会被 `secret-scan.yml` 拦。改用本仓**已有先例**：README 第 52/151 行早就公开写着
  App 演示账号 `demoadult`/`demoteen`/`demosenior` + 口令 `demo123456`。
  于是控制台联调账号复用**同一个已公开的演示口令** —— 不引入任何新秘密，同时做到"组员拿来就能登"。

- **落地**：`README.md`「一键起停」小节内新增 🔑 段落（入口 / 账号口令 / 角色与权限数 /
  为什么它不算密钥 / 可复制的根 `.env` bootstrap 两行 / 一次性语义 / 两条改口令路径 /
  口令下限与弱口令规则 / 生产必须改掉）；根 `.env.example` 补上同样的可复制 bootstrap 值
  —— 那里原先只有一句"变量清单见 `services/java/.env.example`"，而**那正是方式 B 下没人加载的文件**
  （同类坑本轮已踩两次：控制台密钥、CORS 源）。

- **本机同步 + 验证**：用控制台自己的 API 重置口令（不是改库）
  `POST /api/v1/console/admins/1/password` → 200 `{reset:true,self:true}`；
  经 Vite 代理（浏览器真实路径）登录 **200 / role=super**；**旧口令已失效（404）**。

- **推送**：`feat/admin-console` → `origin`（45 个提交，已建立跟踪）。
  按需求方选择**只保留功能分支**，未建 PR、未动 main（远端 main 与本地一致，无分叉）。
  组员测试路径：`git fetch && git switch feat/admin-console` → 根 `.env` 配 `VOICEVERSE_CONSOLE_JWT_SECRET`
  与 `APP_CONSOLE_JWT_SECRET`（同值）→ `pwsh -File scripts/dev-up.ps1 start -WithConsole` → http://localhost:5174 用 `admin`/`demo123456`。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（"工作台没数据"）：真 PG 的可空参数类型推断 —— 同类第四次（I-18）

- **起因**：需求方反馈"点击工作台里面没数据，其他几个页面也是"，网络面板里有一条红色请求返回
  `{"code":50002,"message":"服务内部错误"}`。

- **先排除"是不是真没数据"**：
  - `uvicorn` 访问日志显示浏览器的 ops 请求**全是 200**（`overview`、`services`、`traces/stats` 都 200），
    后端返回的载荷里依赖探测**有 2 项**（database/redis 均 ok）、uptime 有值、self-monitoring 齐全；
  - `ops_metric_samples` 真库里有 **570 行**（15:43→16:14，每分钟一条）→ 采集器**是好的**
    （err 日志里的 `ops_metric_samples does not exist` 是**迁移前**的旧行，时间戳早于 15:42）；
  - 性能指标页 UI 自己写着"本次扫描 67 行样本"，只是 30 分钟数据 + step=1800s ⇒ 每个序列只有 1 个桶
    → "暂无足够数据点"。**这是诚实行为，不是 bug**。
  - ⇒ 真正坏的是 **Java 三个端点**（`publish-events` / `audit-logs` / `users`）。

- **根因（I-18）**：JPQL 里 `(:p is null or col = :p)` 与 `concat('%', :q, '%')` 两类写法，
  在 **PostgreSQL** 上让参数**没有类型线索** —— PG 在 **Parse 阶段**就要求确定每个 `$n` 的类型，
  而参数为 NULL 时 JDBC 驱动也不补类型 OID（非 NULL 会补）。于是出现极具误导性的表现：
  **带筛选正常、清空筛选必炸**。三个端点的真实报错：
  - `publish-events` → `could not determine data type of parameter $3`（$3 是 `from` 的空值判断）；
  - `audit-logs` → 同款 + `operator does not exist: character varying ~~ bytea`（`like (?||'%')`）；
  - `users` → `function lower(bytea) does not exist`（`'%'||?||'%'` 被 PG 解析成 bytea 版本）。

- **为什么测试一直绿**：Java 测试跑在 **H2**，对这两类写法一概接受 ——
  **H2 与 PG 的差异不在 SQL 方言，而在参数类型推断**。本仓同类已第四次（审核单 CAS 的 `coalesce`、
  审计 `from/to`、`users` 的 concat、以及本次全仓普查）。

- **修法**：全仓 **9 个文件 / 19 处**统一给"空值判断"与"拼接"里的参数加显式 cast
  （`cast(:p as string|long|short|timestamp)`），比较那一侧仍由列提供类型，**语义逐字不变**；
  并把 `TicketRepository` 里"该写法 PG 也能推断"的**错误注释**改成实测结论。
  `mvn -B clean verify` → **169 tests / 0 failures / 0 errors**，spotless `154 files clean`。

- **新增静态门禁 `scripts/check_pg_typed_params.py`**（这一类缺陷 H2 测不出，只能用门禁钉住）：
  扫描 `services/java/src/main` 的 117 个文件，命中裸空值判断或拼接裸参数即失败并给出修法。
  **正向 ok（exit 0）；反向**把 `SongRepository` 一处 cast 改回旧写法 → 精确报出
  `SongRepository.java:13` 且 **exit 1**。已接入 `java-ci.yml`（按 AGENTS 要求本地 `yaml.safe_load` 通过）。

- **真栈复验（修复后）**：清空筛选 10 条 + 带筛选 4 条端点**全部 HTTP 200**
  （`publish-events` / `audit-logs` / `users` / `songs` / `scenarios` / `listening-materials` /
  `questions` / `tickets` / `moderation/cases` / `moderation/reports`）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（浏览器登录 403）：CORS 用错源清单 + 覆盖项从未生效（I-17）

- **起因**：需求方截图 —— 控制台登录页报「**服务返回非标准响应（HTTP 403）**」，请求载荷正常
  （`{username:"admin", password:"…"}`）。403 + 非 Envelope ⇒ **过滤器层**拒的，不是业务层。

- **定位过程（记下来，因为第一直觉是错的）**：
  1. 直连 8080 不带 `Origin` → **200**；带上 `Origin: http://localhost:5174` → **403**。
     ⇒ 是 CORS。**注意**：控制台 dev 走 Vite 代理，直觉"同源、不涉及 CORS"是错的 ——
     代理 `changeOrigin: true` 把 Host 改写成 8080 后**原样转发 `Origin`**，Java 侧按跨源处理。
  2. 于是把 `http://localhost:5174` 加进 `ConsoleSecurityConfig.EXISTING_ORIGINS` → **仍然 403**
     （响应体解码后是 `Invalid CORS request`；此前看到代理响应里的 `Access-Control-Allow-Origin`
     是 **Vite 自己加的**，不是 Java）。
  3. 真因：两条控制台链都写 `.cors(Customizer.withDefaults())`，而 Spring Security 的 `CorsConfigurer`
     **按 bean 名遍历容器取第一个** `CorsConfigurationSource`，**不看 `@Primary`** ——
     所以控制台链用的是 `SecurityConfig` 那份（8 个源、不含 5174）。
  4. **连带发现**：本模块的 `VOICEVERSE_CONSOLE_CORS_ORIGINS` 挂在**没人用的那个 bean** 上，
     **从来没有生效过**（文档却把它当作"控制台源可配置"的能力）。

- **修法**：`consoleFilterChain` 显式按 bean 名注入 —— 
  `@Qualifier("consoleCorsConfigurationSource") CorsConfigurationSource` +
  `.cors(cors -> cors.configurationSource(consoleCors))`（两条链都改）；
  5174 / 127.0.0.1:5174 进默认清单（与既有 `apps/web` 的 5173 并列）；
  类注释里那句"用 `@Primary` 让它成为首选"是**错误认知**，已改写并说明原因
  （`@Primary` 只对按类型注入生效，而这里是按 bean 名遍历）。

- **验证（实跑）**：
  - 新增 `ConsoleCorsOriginTest`（3 例）。**先红后绿**：临时把 5174 从清单拿掉 → **2/3 失败**；恢复 → 3/3 绿。
  - **浏览器真实路径**（`POST http://localhost:5174/manage/api/v1/console/auth/login` + `Origin`）→ **HTTP 200 / code=0 / role=super**，
    且令牌 header = `{"alg":"HS256"}`（I-15 的修复同时在线）；同一令牌打 Python 侧 `/ops/overview`、`/ops/traces/stats` → **200**。
  - **覆盖项行为级验证**：带 `VOICEVERSE_CONSOLE_CORS_ORIGINS=http://10.9.9.9:5174` 重启 →
    启动日志的允许源清单里出现它，且该源 **200**、`evil.example.com` **403**、`localhost:5174` **200**
     —— 证明覆盖链路真的通了（修复前它是死的）。
  - Java `mvn -B clean verify` → **169 tests / 0 failures / 0 errors / BUILD SUCCESS**，spotless `154 files clean`。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（真启动）：Java 起不来 → 迁移缺失；修好后又暴露两个跨服务 P0（I-15/I-16）

- **起因**：需求方报"java 端启动失败，查看日志"。日志末尾是
  `org.postgresql.util.PSQLException: ERROR: relation "admin_permissions" does not exist`
  → `BUILD FAILURE`。

- **根因 1（环境，非代码）**：**本地 PG 停在迁移 0012，没有 0013 的 15 张控制台表**。
  Java 是 `ddl-auto: none`（Alembic 是 schema 唯一真源），而 `RbacBootstrap` 启动期就要查
  `admin_permissions` → 直接起不来。处置：先 `pg_dump` 备份（5.4 MB → `local/db-backup/`），
  再 `uv run alembic upgrade head`（0012 → 0013），真库复查 **15/15 表到位**、
  `alembic_version=0013`；重启后 `RbacBootstrap` 写入权限码 37 行、`ConsoleAdminBootstrap` 建出账号 `admin`。

- **根因 2（代码，P0）· I-15：JJWT 按密钥长度自动换算法，Python 固定 HS256**。
  登录成功了（Java 侧 200），但**同一枚令牌打 Python 侧控制台端点全部 46001 `bad signature`**。
  逐步取证：Java 日志无回退告警 → 令牌 claims 全对 → 用项目自己的验签实现验不过 →
  **按 HMAC 反推候选密钥，一个都不匹配** → 打印令牌 header 得 **`alg: HS384`**。
  机制：`Keys.hmacShaKeyFor(bytes)` 按密钥长度选算法（≥64B→HS512、≥48B→HS384、≥32B→HS256），
  而 `.signWith(key)`（不带参数）用的就是它；Python `app/core/auth.py` 是**手写验签**、只算 HMAC-SHA256。
  我生成的密钥是 **48 个 hex 字符 = 48 字节**，正好落进 384 位档 —— 而 `.env` 模板写的是
  "≥32 字节"，**最自然的选法「64 个 hex 字符」更是直接落进 512 位档**，也就是"照着模板配就会踩"。
  影响面不止控制台：App 学习者令牌走同一条 Python 验签路径。
  修：Java 两处签发**显式钉 `Jwts.SIG.HS256`** + 解析侧拒绝非 HS256（避免"Java 认、Python 不认"的半可用令牌）；
  Python `decode_jwt` 增加**显式 alg 检查并报出实际算法**（把"算法不一致"从"bad signature"里拆出来）。

- **根因 3（代码，P0）· I-16：`aud` 形态两端不一致**。alg 修好后报错变成
  `bad audience: ['vocalverse-console']` —— Java 用 JJWT `.audience().add(x).and()` 签发，产出的是**数组**
  （RFC 7519 允许），Python 却拿它跟裸字符串比。Python 自己的单测全用 `create_jwt` 产出的**字符串** aud，
  所以一直绿。修：Python 增加 `_audience_matches()`，字符串/数组两种形态都认（放行的是**形态**，
  不是放宽校验：数组里没有控制台 aud 仍拒），`is_console_token` 同步。

- **本轮最该记住的一条**：**「Java 签发、Python 验签」这句话在此之前从未被真正执行过一次。**
  两侧单测各测各的（Java 用 JJWT 自签自验、Python 自签字符串 aud），
  没有一条测试跨越进程边界，于是两个 100% 复现的缺陷同时藏了一整轮 —— 文档写"已就位"、实际"从未接通"。
  触发它的只是一次**本地真启动**。已登记缺口 **G-18**：缺"跨服务一跳"的冒烟门禁
  （Java CI / Python CI / admin-ci 结构上都不可能发现它）。

- **验证（实跑）**：
  - **修复前先红**：把两处 `.signWith(key, Jwts.SIG.HS256)` 临时改回 `.signWith(key)` 跑新测试 →
    **2/4 失败**（正是那两条"算法必须 HS256"的断言）；改回后 4/4 绿。
  - **Java**：`mvn -B clean verify` → **166 tests / 0 failures / 0 errors / BUILD SUCCESS**（162 → 166），spotless `153 files clean`。
  - **Python**：`ruff check` 通过、`format --check` 203 files、`pytest -m "not gpu"` → **491 passed / 0 skipped**
    （上一轮是 483 passed + 4 skipped：Docker 恢复后真 PG ×2、真 Redis ×2 **这次真的跑了**）。
  - **端到端（首次真跑通）**：Java 登录 → 同一令牌打 Python 侧
    `/ops/overview`、`/ops/metrics/catalog`、`/ops/traces`、`/ops/traces/stats`、`/ops/alerts/rules`、`/library/books`
    **全部 HTTP 200 / code=0**；App 侧 `POST /auth/login` → Python `/api/v1/reading/books` **200**
    （确认改签发算法没伤到学习者链路）。
  - `dev-up.ps1 start -WithConsole` 全流程也**首次真跑通**（四端健康检查全绿），
    上一轮"未跑全流程"的标注据此解除。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（配置）：本地 .env 补齐控制台密钥 + 修正上一轮的机制描述错误

- **背景**：需求方要求"帮我填一下 .env 里密钥"。范围按"让控制台真能跑起来"来定，**不动**任何第三方密钥。

- **做了三件事**（改的都是 **gitignored 的本地文件**，入库的只有文档与脚本措辞）：
  1. 根 `.env` 补 `VOICEVERSE_CONSOLE_JWT_SECRET` / `APP_CONSOLE_JWT_SECRET`（**同一个值**，48 hex 字符，
     与 `JWT_SECRET` 不同）；`services/python/.env` 同步补后者（不经 dev-up、直接跑 uvicorn 时也能验签）。
  2. 根 `.env` 补首个管理员的 bootstrap（`admin` + 随机强口令；`admin_users` 非空时不建号，属幂等）。
  3. 改前先备份两个 `.env` 到 `local/env-backup/<时间戳>/`（gitignored）。

- **实证（当前环境下能做的都做了）**：
  - Python 运行期：`get_settings().console_jwt_secret` **非空（48）、≠ App 密钥**，且**不再**出现
    "APP_CONSOLE_JWT_SECRET 未设置（development 档）：控制台端点将 46001" 的告警；
  - 取值一致性：根 `.env` 值的 `sha256` 前 12 位与 Python 读到的一致（证明就是写进去那个值）；
  - dev-up 的 `.env` 解析器：能取到该键且**非空**（非空才不会被脚本"空值键跳过"的语义丢掉）；
  - 跨服务常量：Java `ConsoleJwtService.AUDIENCE/ISSUER` = `vocalverse-console` / `vocalverse-java`，
    与 Python `console_jwt_audience/issuer` **逐字相同**；Java 侧读的是
    `application.yml` 里的**显式占位符** `${VOICEVERSE_CONSOLE_JWT_SECRET:}`（不依赖 Spring 松散绑定，
    故 `VOICEVERSE_` 而非 `VOCALVERSE_` 前缀这件事不会踩坑）。
  - ⚠️ **未做**：端到端登录验证 —— **Docker 引擎当前不可用**（`docker info` 连不上 npipe），
    5432/6379 均 down，Java/PG/Redis 都起不来。所以"填完密钥后能真正登录并访问运维页"这件事
    **没有证据**，只验证到"配置链路正确"这一层。

- **修正上一轮自己写错的地方（重要）**：我把"只配一个键"的后果描述成"Python 也会回退"，**这是错的**。
  逐行读 `app/core/config.py` 与 `app/console/api/deps.py` 的真实语义是**两侧不对称**：
  Java 侧留空 → **回退**用 `JWT_SECRET` 签发（登录看起来完全正常）；Python 侧留空 →
  **fail-closed**，控制台端点一律 46001（development 档只 warn 一行）。生产档才额外断言
  "控制台密钥 ≠ App 密钥"。已改对根 `.env.example` 与 `dev-up.ps1` 的自检文案
  （自检函数用 AST 取真实函数体重跑，确认新文案生效）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（补漏）：一键启动里没有管理端 + 控制台密钥的静默 401 陷阱

- **起因**：需求方问「README 里 `pwsh -File scripts/dev-up.ps1 start` 能起管理端吗」。**答案是：不能。**
  查证结论 —— `scripts/dev-up.ps1` 只起三端（python:8000 / java:8080 / vite:5173 = `apps/web`），
  `status` / `stop` 也各自硬编码 `8000, 8080, 5173`，全文没有 `apps\admin` 或 `5174` 任一字样。
  这是本次交付留下的**集成缺口**：我把 `apps/admin` 写进了 README 的目录树与文档索引，
  却没有写它怎么启动，也没接进一键脚本。

- **补法（按需求方选择的方案）**：
  1. `dev-up.ps1` 加**显式开关** `-WithConsole`（默认三端行为**一字不变**，不影响组员日常）：
     `start/status/stop` 三处都支持；并把受管端口收敛成**一处真源** `$Ports`
     —— 原先 status 与 stop 各写一遍端口列表，加第四端必然漏掉一处（漏 status 看不到、漏 stop 杀不干净）。
     控制台分支还包含"缺 `node_modules` 时先 `pnpm install`"与"健康等待把 5174 纳入"。
  2. 根 `README.md` 补 `-WithConsole` 用法 + 两个前置条件；`apps/admin/README.md` 补一句交叉引用。
  3. 根 `.env.example` 补 `VOICEVERSE_CONSOLE_JWT_SECRET` 与**同值警告**（见下）。

- **查证过程中发现的真陷阱（比"脚本漏一端"更要紧）**：根 `.env.example` 原先只登记了 Python 侧的
  `APP_CONSOLE_JWT_SECRET`，而 Java 读的是 `VOICEVERSE_CONSOLE_JWT_SECRET`（只写在
  `services/java/.env.example` 里）。关键在于：方式 B 只注入**根** `.env`，而
  **Spring Boot 根本不读 `.env` 文件**（`application.yml` 无 `spring.config.import`，
  也没有 dotenv 的 `EnvironmentPostProcessor`）—— 那个文件在方式 B 下没人加载。
  于是"照根 `.env.example` 抄"的开发者会得到：Java 拿不到控制台密钥 → **回退用 `JWT_SECRET` 签发**
  （`ConsoleJwtService:77-90` 有显式回退分支），Python 却用 `APP_CONSOLE_JWT_SECRET` 验签
  → **运维 / LLM trace / 书籍 / 媒体等 Python 侧控制台端点全量 401，且报错里不会提示"密钥不一致"**。
  这正是各文档反复警告的"生产脚枪"，**而警告原先只写在没人加载的那个文件里**。
  处置：两个键名与同值要求在根 `.env.example` 写清；`start -WithConsole` 时做一次**密钥自检**
  （只告警不中止 —— Java 侧留空的回退期本身是设计允许的中间状态）。

- **验证（实跑）**：脚本 `Parser::ParseFile` → **0 syntax errors**；`status` → 三端、
  `status -WithConsole` → 四端 + console 健康行；在 `apps/admin` 实跑 `pnpm dev` →
  **HTTP 200，标题「VocalVerse 控制台」**（Vite 1.33s ready，5174 监听），此时
  `status -WithConsole` 报 `5174: LISTENING` / `health: console=True`，不带开关只列三端（开关隔离成立）；
  `Test-ConsoleSecret` 用**从 AST 取出的真实函数体**跑五种环境组合，四个异常组合各自告警、同值安静。
  ⚠️ **未跑**：`start -WithConsole` 全流程（会拉起 Docker 容器 + 四个进程，属对开发机的实际启停）
  —— 每个部件单独验证过，但"一次跑通"没有证据。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（闭环）：G-17 内容创作 UI 四个域全部接通 + 题库零入口缺口（I-14）

- **这一段把 `docs/50 §15.2 G-17` 从"部分闭合"推到**✅ 闭合**，并且是在收尾自查里又抓到一个 P0 缺口**。

- **缺陷 I-14（P0）· 权限码"发不出去也测不到"**：题库的 `content:question:read/write` 从控制台模块第一天起就登记在 `PermissionCatalog`，后端 `POST/PUT/DELETE /content/questions` 也齐 —— 但**前端既没有题库列表页，也没有路由/导航**。后果比"少一个页面"重得多：① 运营拿不到入口，`QuestionUpsert`/`QuestionPatch` 的全部能力无人可用；② 这两个权限码**永远不可能被真实使用**，`PermissionCatalogTest` 只能证明"码存在"，证明不了"码有用"。这与 I-9 是同一个道理的两面：**只删旧入口不算完，还要逐个确认每个能力都有新入口**（退役清单必须配"能力迁到哪"那一列）。

- **落地**：四个内容域全部接上「内容维护」列（写权限 `content:{song,scenario,listening,question}:write`，与上下架的 `:publish` 分开——一个改字段、一个改状态，合成一列会让"这个按钮要不要填原因"变成看着按钮猜）：
  - **歌曲**：编辑 / 歌词 / 新建（LRC 编辑器整首重写，界面常驻三条服务端事实：保存歌词会让 `ready` 的参考旋律失效、提交前按 offsetMs 重排、结束毫秒留空 = 与起始同值）；
  - **场景**：编辑 / 新建（`targetCorpus` 按 `English phrase|中文释义` 逐行解析且上架要求 ≥3 条，故用多行输入并把权威格式写在提示里，而不是让运营提交后吃 46011 才知道格式）；
  - **听力素材**：编辑 / 新建（列表行只有 `hasTranscript` 布尔位，**必须**回读单条，否则保存会把已有转写清成空串）；
  - **题库**：**新增页面**（列表 + 筛选 + 新建/编辑/归档）。题库与其它三域的结构性差异如实落进 UI：没有 `content:question:publish` 权限码、`status` 只有 `published|archived` 两态（无 draft），所以页面**不挂**上下架按钮（挂上去会得到一个永远 46002 的按钮），归档走独立的确认框 + 必选原因；编辑态下 `examRevision`/`itemIndex` 禁用并写明原因（后端 `QuestionPatch` 不接受身份字段——改题号等于换一道题，会让历史作答对不上）。
  - 共用件：`authoringColumn.ts`（四个域共用"内容维护"列，避免某个域漏套 `PermissionGate` 变成越权入口）、`NavIcon` 补 `list-check` 登记（未登记的图标名会**静默渲染空位**，这个坑写在组件注释里）。

- **补上单测（此前这一层零覆盖）**：`authoring/__tests__/contentForm.test.ts` **24 例**，钉住三类最贵的字符串↔线格式转换：① 空的可选字段必须发 `null` 而不是 `""`（`""` 会被服务端当真实值写库）；② 必填的 `@NotNull` 字段不能发 null（吃 42201，且文案读起来像"不能为 null"，运营看不懂）；③ LRC 提交前按 `offsetMs` 升序重排（服务端按**数组下标**重排 `seq`，乱了会让整首歌的歌词与时间轴错位）。顺带覆盖了此前无人调用的 `*FromForm`（"只发改动字段"的补丁构造器）——它当前**未用于提交**（服务端 `applyXxx` 无条件覆盖，发补丁会把未提交字段写成 null，所以实际发全量 + 编辑前先回读），但口径必须在。

- **验证（实跑）**：`apps/admin` `pnpm typecheck` **0 error** / `pnpm lint` **0 error 0 warning** / `pnpm test:run` **68 passed（5 files，44 → 68）** / `pnpm build` 成功。产物取证：`QuestionsView-*.js` 等分包落盘。
  - **踩坑（记一条）**：`vitest` **不做类型检查**（只转译），所以"测试全绿"不代表类型通过 —— 本轮新增测试里一个 `status: null`（DTO 正确地把它标成非空，对应列 `NOT NULL`）就是被 `pnpm build` 里的 `vue-tsc -b` 抓到的，而不是被 `pnpm test:run`。**顺序必须是 typecheck 之后再 build，两者不可互相替代。**

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（收尾）：三处安全控制静默失效 + 参考旋律静默损坏 + 两道门禁自身的漏洞（Java 全绿）

- **这一段的价值不在"又写了一堆代码"，而在"把已经写完、且读起来完全正确的代码跑起来"**。三个 P0 全部满足同一个特征：**代码逐行看都对，只有跑起来才暴露**；而它们又都是**既有测试**抓到的（`ConsoleAuthApiTest` 三条 + 新增回归），说明"把设计里的承诺写成断言"是有回报的。

- **缺陷 1（P0）· 认证风控三处控制全是空的**：`ConsoleAuthApiTest` 此前 3 例红（5 次锁号、同 IP 20 次/5 分限流、refresh 重放吊销全族），表象像"功能没实现"，**实际代码里三条逻辑都写着**。根因一条：`ConsoleAuthService.login/refresh` 是 `@Transactional`，而它们**写完安全状态之后必然要抛 `ConsoleException`**（RuntimeException → Spring 回滚整个事务），把刚写的尝试流水、刚累加的失败计数、刚盖的锁定时间、刚吊销的会话**一起丢掉**。后果逐条：① 失败计数不落库 → **口令爆破不受任何限制**；② 尝试流水不落库 → **撞库不受限**；③ 会话族吊销被回滚 → 重放旧 refresh 虽回 46001，但轮换出的**新 refresh 照样可用**（"检测到泄漏就全族下线"= 空话），更糟的是旁边那行走独立事务的审计**如实写着"已吊销 N 条会话"，而实际一条都没吊销** —— 日志与事实相反。修：新增 `ConsoleAuthIndependentWriter`，把这三类"**已经发生的事实**"放进 `REQUIRES_NEW` 独立事务（与既有 `IndependentAuditWriter` 同源、同理由）；单独一个类而不是同类私有方法，因为 Spring 事务代理不拦自调用。判据写进类注释：**这个写入是"事实"还是"业务结果的一部分"？是事实就必须独立提交。**

- **缺陷 2（P0）· 改歌会静默损坏参考旋律**：`applySong` 把 `songs.pitch_ref_status` 按"缺省 = 回落默认值"写成 `b.pitchRefStatus() == null ? "missing" : …`，而该列**不是人填的**（由离线音高提取任务驱动，控制台四个内容弹窗里没有输入框），同时又是**上架前置条件**（`validateSong` 要求 `ready`）与逐句跟唱评分的参考旋律来源。于是**任何一次运营改歌（哪怕只改歌手名）都会把它打回 `missing`**：接口 200、无任何报错线索，但这首歌从此上不了架 —— 现象（上架被拦）与原因（某次无关编辑）离得极远。修：只在显式传值时覆盖，新建的初值移到 `createSong` 显式写入。**取证**：新增 `SongPitchRefPreservationTest`（3 例），把 `applySong` 临时改回旧写法后跑 → 用例 1 红在 `assertEquals("ready", …getPitchRefStatus())`；改回修复实现 → 3/3 绿。**先红后绿，不是我事后补的测试。**

- **缺陷 3（P0）· 控制台的 42201 被自己的兜底吃掉**：`ConsoleExceptionHandler` 是 `@Order(HIGHEST_PRECEDENCE)` + `basePackages=console`，却带一个兜底 `@ExceptionHandler(Exception.class)`。Spring 选 advice **只按 advice order 找第一个"有匹配方法"者，不比较异常类型精确度** —— 于是控制台路径上所有 `@Valid @RequestBody` 失败（运营域 4 个写入端点的入参校验**正是**靠 Bean Validation）由「400 + 42201 + 字段名」变成 **500 + 50002**；`HttpMessageNotReadable` 同理由 40001 变 50002。后果：前端 `serverFieldErrors` 里"把 42201 的字段名浮回输入框"那套映射**在生产上永远走不到**，运营只看到「服务内部错误」。修：删掉兜底 —— 当初加它的理由（"保证 500 有堆栈"）已不成立，因为 `GlobalExceptionHandler.handleFallback` 自 2026-09-10 起同样打完整堆栈。

- **缺陷 4（P0）· 两道门禁自身的漏洞**（这类最难发现，因为它让缺陷长期不可见）：
  1. **`apps/admin/src/env.d.ts` 的 `declare module '*.vue'` 通配声明**使"导入一个**不存在**的 .vue 文件"也能过类型检查（解析成 `DefineComponent<Record<string, unknown>, …>`）。实测：`SongFormModal.vue` 导入的 `LrcEditorModal.vue` **根本不存在**，而 `pnpm typecheck` 绿、`pnpm build` 也绿 —— 因为该弹窗当时没有任何页面引用它，**Rollup 根本不去解析这个 import**。两处门禁同时失效，只有真正接线的那一刻才炸。修：删掉通配声明（vue-tsc/Volar 自己就能解析 `.vue`），立刻报出 `TS2307` 且无其它误报 → 补齐 `LrcEditorModal.vue` 并把 authoring 模块真正接进歌曲库。
  2. **Java 的 `spotless:check` 绑在 `verify` 阶段、排在 `test` 之后** → Java 测试红了整整一轮期间，**格式门禁从未执行过**（构建在 test 阶段就停了）。等测试全绿它第一次跑起来，报出 **15 个文件**不合规。教训：**门禁的"阶段顺序"决定它是不是真门禁**。

- **顺带补上的活儿**：① 工单状态机 `TicketWorkflowService` 上一轮 commit 被 `git add` 漏掉、一直躺在工作区（本轮补提）；② `apps/admin` 的 lint 从 6 warning + 4 error 收到 **0/0**（补 prop 默认值、属性引号内层改 `&quot;`、把 665 行的 payload 单文件按**改动原因**拆成 `contentFormTypes/Model/Payload` 三个文件 —— 原单文件触发 ESLint `max-lines`）；③ `apps/admin` 上游基址改为按 `import.meta.env.PROD` 在代码里给默认值（原先只写在 gitignore 的 `.env.*` 里，新克隆的仓库构建出来会打到错误路径）。

- **验证（全部实跑；未跑的一律标注）**：
  - **Java**：`mvn -B clean verify` → **BUILD SUCCESS：162 tests / 0 failures / 0 errors**（同一命令内 `spotless:check` = **152 files clean, 0 needs changes**）。定向复跑：`ConsoleAuthApiTest` **11/11 绿**（此前 3 红）、`SongPitchRefPreservationTest` **3/3 绿**（修复前 1 红）。
  - **Python**：`ruff check` All checks passed / `ruff format --check` **203 files** / `pytest -m "not gpu" -q` **483 passed + 4 skipped** / `alembic heads` **0013 (head) 单头**。⚠️ **4 个 skip 的口径**：Docker 当前不可用 → `test_pg_integration.py` ×2（真 PG）与 `test_redis_state_store.py` ×2（真 Redis）跳过（`pytest -rs` 逐条打印原因）。**取证时点**：Docker 在本会话中途一度可用（`ServerVersion 29.4.0`），真 PG 迁移取证与 testcontainers 用例是在**那个窗口内**跑出来的；收尾复跑时 Docker 又不可用，故这 4 例**当前不可复现** —— 它们不是"已通过"，也不是"被忽略"。
  - **`apps/admin`**：`lint` **0 error / 0 warning**、`typecheck` **0 error**（**去掉通配声明之后仍然绿，这个绿才有意义**）、`test:run` **44 passed / 4 files**、`build` 成功。产物取证：`正在读取歌曲详情`/`整首保存`/`至少 1 行歌词` 三个串出现在 `dist/SongsView-*.js` → authoring 模块**真的被打进构建**（此前它零引用、Rollup 不解析）。
  - **`apps/web`**：`lint` 0 error、`test:run` **223 passed（40 files）**、`build` 成功、`node scripts/check-bundle.mjs` **exit 0**（四条断言：preview 树零体积 / manualChunks 专块齐 / 入口块无 p5 / echarts 零残留）。
  - **记录更正**：`docs/51 §7` 原先写 `pnpm check-bundle`，而该门禁**不是** package.json script，必须用 `node scripts/check-bundle.mjs` 调（照抄会得到 `Command "check-bundle" not found`）。**失实之处在命令写法，不在脚本缺失** —— 已在文档里改对并写明这一点。

- **仍未闭合（不得当成已完成）**：① **G-17 内容创作 UI 只接了歌曲域**（听力素材 / 场景 / 题库三个域的表单弹窗未做；值类型、预检、payload 映射在 `authoring/` 层已就绪，缺弹窗与列接线）——**在补齐前不得宣称"运营管理已闭环"**；② ADR 修订申请（`docs/06 §2.1-4` / `§9.6` / `§9.7` 受控例外 + 6 处同步性修订）**仍待组长签核**，批准前不改 `docs/06` 正文（本轮只把 `§17` 开关表里一处**悬空引用**（"见 §9.7 受控例外"指向尚不存在的例外）改为指向 `docs/50 §2.3 修订 3` 并标注"待签核"）；③ `apps/web` 的 `pnpm typecheck` **仍是空跑**（solution-style 根 tsconfig → 零文件受检，另立工单）；④ `-Pintegration` 真 PG Java 集成测试未跑；⑤ 控制台浏览器端冒烟未跑（无浏览器自动化）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 管理端后台（独立控制台）：三角色 RBAC + LLM trace + 四路拷问闭环

- **需求（用户口径）**：做**独立 web 端**管理端后台，参考万玄阁 `apps/admin` 的设计模式，**模块化隔离、不与既有业务代码耦合**；要有权限控制台，分**运维（服务器运行/预警/性能 + LLM trace 供调优）／运营（音乐/书籍/音频上下架）／审核（社区帖子/评论/视频）**三角色；要求自己跑闭环——分析→设计→**子代理拷问**（怎么做/如何做/该做什么、并发性能、日志记录、数据模型、业务逻辑联动、模块设计、前端 UI/UX 与布局统一）；图表参考 lieflat-charts skill。

- **交付物**：设计 `docs/50-管理端后台设计.md` + 拷问 `docs/51-管理端后台拷问报告.md`；前端 `apps/admin`（独立 SPA，独立 pnpm 项目/端口 5174/产物/nginx/Dockerfile，零 import `apps/web` 源码）；Java `com.vocalverse.console`（独立包，终端模块）；Python `app/console/**`（运维采集 + trace + 书籍/媒体）+ 迁移 `0013`（15 张表）；CI `admin-ci.yml`；compose `admin-console`（`console` profile）；联调桥接页 `apps/web/src/views/preview/AdminConsolePreview.vue`（含删除清单）。

- **关键设计裁决**：
  1. **独立身份** `admin_users`，**不复用 `users.role`**（既有 CHECK 只允许 `user/admin`，扩词表会把改动外溢到 App 登录/种子/16 个 Java 测试类）；控制台账号与 App 账号**互不能登**。
  2. **按数据归属方分服务**而非按界面：Java 管身份/RBAC/审计/审核/内容（`/manage/api/v1/console/**`），Python 管运维/trace/书籍/媒体（`/api/v1/console/**`，**子路径不重叠**，复用既有 nginx 路由 → 用户端 nginx 零改动）。避免 Java 读写 Python 的表（破坏 `docs/06 §10` 写方矩阵）。
  3. **单一审计流**：不建 `moderation_actions`，审核决定的前后状态写进 `admin_audit_logs.detail`；`@Audited` 必须显式 `@Order` 与业务写**同事务**（`@EnableTransactionManagement.order` 默认 `LOWEST_PRECEDENCE`，不显式设就有一半概率回滚后仍留痕）。
  4. **LLM trace 移植 DSH GenAI span 树**（`loongsuite/dsh-plugin`，Apache-2.0）：`ENTRY→AGENT→STEP→{LLM,TOOL}`，一次 turn 一个 trace、每次真实 LLM 尝试一个 span（重试可见）、异常路径也关 span；**结构元数据与内容分表**（`llm_span_contents` 独立表 + 独立 72h TTL + 独立权限码 + 读取写审计），**默认关**，并**硬排除 `kind='defense'`**（答辩论文文本）。
  5. **前端独立设计语言**：色彩**继承产品 `u-*` 纸墨**（`ink #1c1c1a` 与 lieflat Mono 的 `INK #1C1C1A` **完全相同**），圆角降级到控制台尺度（控件 8 / UI 卡 16），图表卡按 Mono 契约走**纸底 24px**；图标 Tabler only；naive-ui 单注入点，主色用现行 `#2f6bff`（**不用已退役的绿 `#16A34A`**）。
  6. **图表锁 Mono 单一色彩系统**，17 张图逐图审计（体系/编号/gallery 卡内标题/淘汰理由），1 张库外图（trace 瀑布）走 SKILL §6 翻译流程；含 **Mono 偏离清单**（5 条）。

- **四路拷问（子代理对抗，报告在 `local/`，不入库）**：并发性能+日志 / 数据模型+业务联动 / 架构模块+范围取舍 / 前端 UI-UX+图表，共报 **33 条 P0**，合流去重后 **30 项逐条裁决**（采纳 / 部分采纳 / 驳回附理由）。**8 条可当场复现的硬缺陷**，其中由拷问直接暴露、随后修复并取证的：
  1. **迁移 `0013` 在真 PG 上装不上**：`DROP CONSTRAINT ck_media_assets_status` 名不存在——`0011`/`0012` 用裸全名建约束，而 `base.py` 的 `ck` 约定含 `%(constraint_name)s` → 二次套用成 `ck_media_assets_ck_media_assets_status`。**离线渲染与 SQLite `create_all` 都抓不到**；真 PG 实测 0012 时点正好 6 条错名。修：4 条 `RENAME` + 2 条双名 `DROP IF EXISTS` + 按正确名 `NOT VALID`+`VALIDATE` 重建。
  2. **`aud` 跨令牌闸门根本不存在**：实现注释声称"App 侧会拒绝控制台令牌"，而 `JwtService`/`JwtAuthFilter` **既不签发也不校验 `aud`**，控制台又默认回退共享密钥 → **控制台令牌可被当成真实 App 用户身份**。修：App 侧**只拒绝携带外来 `aud`** 的令牌（既有无 `aud` 令牌零影响）；**严禁**给 App 令牌补 `aud`（`AuthController:224` 复用 access 作 refresh，补了会**全体在线用户强制登出**）；Python 侧补 `aud/typ/iss` 三闸 + `get_current_user_id` 拒控制台令牌。
  3. **隐藏生效清单是 18 处不是 8 处**，漏的含**通知中心**（`PostInteractionRepository` 3 处 native SQL + `DirectMessageRepository` 6 处）→ 只改 `PostRepository` 时 hidden 帖仍经通知露出标题/评论正文，而 v1 用例不覆盖通知 → **自测会通过**。
  4. **指标分位数无处可存**：DDL 只有 `avg/max/min` 却要 p50/p95/p99；跨桶取平均得到的是"平均的分位数"，v1 自己的验收用例必红。修：加 `buckets jsonb` 直方图，跨桶**求和后插值**；可加型/分布型分列且不得混用。
  5. **内容捕获推翻已写红线**（`docs/06 §9.7`「只存评分/转写/元数据」「不 log 论文/转写/请求体」）→ 补 §9.7 受控例外 ADR 申请 + 答辩域硬排除。
  6. **依赖方向规则与埋点位置自相矛盾**（§3.1 断言"领域模块不得 import console"vs §7.3 把埋点放进领域模块）→ 规则精确化 + 白名单 `app.console.trace`。
  7. **`TraceWaterfall` 脚注在说谎**（脚注"未截断"，代码有 `MIN_BAR=1.5px`）→ 保留下限但**在界面写明当前比例尺与最小宽度对应毫秒数**（SKILL §7 第 ③ 条"撕柱不撕轴"）。
  8. **仓库 `pnpm typecheck` 从未检查过任何代码**：`apps/web` 根 `tsconfig.json` 是 solution-style（`files: []`），`vue-tsc --noEmit` 零文件可查。**实测：故意写入类型错误，退出码 0**。→ `apps/admin` 改为显式 `-p tsconfig.app.json` 并用探针验证会报错；**`apps/web` 的同类修正另立工单**（会一次性暴露大量历史类型错误）。
  - 其他采纳项：`ops_alert_events.rule_id` CASCADE→**RESTRICT**（原写法删规则会删光预警历史）、举报建单并发 `ON CONFLICT DO NOTHING` + `46015`、Java `Semaphore(4)` **删掉**（限不住连接，连接由事务持有到 commit）、sink 跨线程提交改 `call_soon_threadsafe`、nginx 每个 location 单独写 `X-Request-Id`（漏写会让浏览器/Java 审计/Python 日志是三个 uuid）、Tomcat access log **不认 MDC**（`%{x}r` 是 RequestAttributeElement）→ 改 `request.setAttribute` + `%{adminUserId}r`、对比度实测修正（焦点环 `#e8edff` 在白底 **1.17:1 等于隐形**）。
  - **驳回项（附理由）**：砍运维整域（与需求冲突，改为限定覆盖范围并登记 Java 进程指标缺口）、砍 trace 内容捕获（需求要"调优参考"，改为默认关 + 多层隐私闸）、砍 `admin_login_attempts`（状态与事件流语义不同，风控排查要后者）、砍 13 张图（图表是三角色的实际决策依据，改为每页 ≤6 张 + 只做被消费的图）。

- **ADR 修订申请（待组长拍板，批准前不改 `docs/06` 正文）**：① `§2.1-4` 管理端 UI 改为独立 SPA（**维持**不建根 workspace/共享包、不新增网关容器）；② `§9.6` Java 管理端权限由"简单 admin/user 角色"改为四角色 RBAC + 全量审计；③ **`§9.7` 新增 LLM trace 内容捕获的受控例外**；④ 同步修订 `docs/12`/`docs/04`/`docs/13`/`docs/20`/`docs/21`/`docs/06 §2+§14`；⑤ 15 张表按 §18/§19 体例**新开 §20 登记**（非修订）。

- **登记**：`docs/50`、`docs/51`（README 文档索引已登记）；`docs/api/error-codes.md` 新增 **`46xxx` 管理端段 15 码**；`docs/api/envelope.md` 新增「错误 data 的结构化例外」（46002/46003/46008/46011/46015 的 data 形状）+ 控制台端点前缀 + **控制台鉴权专节**；`docs/06 §17` 登记 5 个新开关（`APP_LLM_TRACE_ENABLED` / `APP_LLM_TRACE_CONTENT_CAPTURE` / `APP_OPS_TELEMETRY_ENABLED` / `VOICEVERSE_CONSOLE_ENABLED` / `VOICEVERSE_CONSOLE_LLM_CONTENT_CAPTURE`）；`VOICEVERSE_CONSOLE_JWT_SECRET` 是**密钥**不入功能位表并标注"只配一处会让 Python 侧控制台端点全量 401"的生产脚枪。

- **验证（真跑过的，未跑的一律标注）**：
  - **迁移**：`alembic heads` → `0013 (head)` 单头；离线 `upgrade 0012:head --sql` 18,204 字节，逐条核对 4 处 P0（约束名/RESTRICT/部分索引 WHERE/`buckets`）；**真 PG16 取证**（Docker 会话中途转为可用）：0012 时点实测 6 条双前缀错名 → 0013 后全部正名、`alembic check` **零 diff**、**19 张表模型↔真库零漂移**、行为探针（CHECK 拒 `bogus` 收 `hidden`、部分唯一索引幂等、RESTRICT 拦下删规则、既有章节读 `published`）、有 `hidden` 行时 downgrade **按设计失败**、归一化后回退→重放零 diff；SQLite `create_all` 56 张表 + `sqlite_master` 原文含 `WHERE` 谓词；`check_single_writer.py` → 25 张表受守护无越权。
  - **Python**：`pytest -m "not gpu" -q` → **392 passed**（含 2 个真 PG testcontainers 用例，非 skip）。
  - **前端 `apps/admin`**：`lint` **0 error**（6 条 `vue/require-default-prop` warning，均在共享组件）；`typecheck` **0 error**（显式 `-p tsconfig.app.json`，非空跑）；`test:run` **28 passed**（`mono.test.ts` 15 例 + 12 张图渲染烟测 13 例）；`build` **成功**（入口 46.8 kB / `vendor-naive` 787.9 kB，按路由分包）。
  - **前端 `apps/web`（含新增的 preview 桥接页）**：`lint` 0 error、`test:run` **223 passed**、`build` 成功、`node scripts/check-bundle.mjs` **exit 0**（桥接页被生产构建整枝剔除，证明零体积零路由）。⚠️ `pnpm typecheck` 仍是**空跑**（见上 §8 条）。
  - **图表接线自查（一个不好看但必须写的数字）**：14 个图型组件里**只有 6 个被页面消费**（`docs/50 §12.7` 逐个交代）。4 个建议删除（F3 与 F2 冗余 / F11 选型已被拷问证伪 / L4 消费者已在审计中合并掉 / L17 要一整年数据而保留期只有 30 天），3 个缺聚合端点（F9 净变化 / F15 五数概括 / F10 星期×小时），1 个与"不做实时推送"冲突（G17）。**得到的教训**：组件完成 ≠ 能力交付；凡"做了一组组件"的交付必须附"谁在消费"的清单，否则交付的是库不是功能。
  - **集成期反向发现的 4 处契约不一致**（前端按 `docs/50 §10.2` 实装后与 Java 实装对账出来的，已回派实现方）：①②`/moderation/reports/{id}/handle` 字段名（`decision` vs `@NotNull action`）与 `CaseAssign.assigneeId` 不可空 → **举报处理必然 400、取消认领服务端失败**；③`/moderation/stats` 缺 `approvedToday/rejectedToday/trend/decisions` → **审核工作台首屏空白**（界面如实降级显示 `—`，不编造数字）；④`/moderation/cases/{id}` 与列表不同形。**这类问题只有真正接线才暴露**——正是闭环要求的价值。
  - **安全闸门代码级复核（我独立看的，不是听报告）**：`JwtAuthFilter` 已实现「**任何携带外来 `aud` 的令牌一律拒绝**」并明确论证**不给 App 令牌补 `aud`** 的理由（`AuthController:224` 复用 access 作 refresh，补了会让**全体在线用户强制登出**）；`ConsoleSecurityConfig` 用 `@Order(1)` + `securityMatcher("/api/v1/console/**")`，并给出**两条独立证据**说明既有 `JwtAuthFilter` 不会跑在控制台路径上（它不是 `@Component`，而是 `new` 出来只加进既有链 → 既不在匹配到的链里，也不在 Servlet 容器注册表里）；`ConsoleCrossTokenTest` 用 `@SpringBootTest` 真实上下文断言双向拒绝。
  - **YAML 门禁（AGENTS 硬要求）**：6 份 workflow + `docker-compose.yml` 全部 `yaml.safe_load` 通过（`admin-ci.yml` jobs=`['admin']`；compose services 含 `admin-console`，profiles=`['console']`）。

- **未做 / 已登记缺口**：① 保留期清理（trace 30d / 内容 72h / 指标 7d / 审计 365d / 登录尝试 90d）**只有索引、无调度器**（本仓确实没有后台清理先例，24h 音频是"读时惰性删"）；② Java 进程级指标（JVM/线程池/Hikari）未采集，本期只覆盖 Python 进程 + Java `/actuator/health` 探活；③ `shadow_materials` 无管理端点；④ 作者可见性/审核原因下发通道需扩 C 端 DTO + `docs/21` + 契约快照，本期不做半成品；⑤ 图表候选审计深度仍有 8 行不达标（已如实标注，未假装审完）；⑥ `apps/web` 的 `typecheck` 空跑修正另立工单；⑦ 媒体存储占用/孤儿清理只读视图；⑧ ~~双轨管理面（既有 `/api/v1/admin/**` 与新的控制台）需评估既有面下线~~ → **已决议：旧管理端整体退役**（见下）。

- **需求方澄清与随之的范围变更（2026-09-10 追加）**：澄清"**之前写的旧管理端是废弃的，不需要重复用**"。据此把原"旧壳保留为兼容壳、后端双轨共存"的保守处置**升级为旧管理端整体退役**：
  - **前端（已完成并复跑门禁）**：删除 `apps/web` 的 `/admin` 路由子树（`AdminLayout` + 5 个 `PlaceholderView` 子路由，从未实现过）、`layouts/AdminLayout.vue`、`views/preview/AdminDashboardPreview.vue`、`views/preview/AdminUsersPreview.vue`，并把预览画廊的布局枚举由 `'user'|'admin'|'gallery'` 收窄为 `'user'|'gallery'`（独立控制台不共享用户端布局，无可模拟）。复跑：`lint` 0 error、`test:run` **223 passed**、`build` 成功、`check-bundle` **exit 0**。保留 `/preview/admin-console` 桥接页（新控制台的联调入口）与 `LieflatPreview` 资产（图表风格参考，服务的不是旧管理端）。
  - **后端（已回派，随本 PR 执行）**：删 `AdminUserController`/`ContentAdminController`/`QuestionAdminController`/`AdminTicketController`（27 op）+ 只测它们的测试 + `SecurityConfig` 的 `hasRole("ADMIN")` matcher + 契约快照重生成；**保留**其 Repository/Service（`com.vocalverse.console` 复用的是数据层，只删 HTTP 面）；**不动** `users.role` 的 CHECK（用户域资产，改它属另一件事，仅记录 `ROLE_ADMIN` 失去消费者）。
  - **退役后必须复核**：① 没有控制台功能因此回退（尤其工单——控制台 `/content/tickets/**` 成为唯一工单面）；② 没有别的调用方指向 `/api/v1/admin/**`（Python 内部调用走 `/internal/**`，应不受影响，但要**验证而非假设**）；③ `/admin` 旧书签若需平滑，应在**网关层** 302 到 `/console/`（不写进 `apps/web` 路由表）。
  - **这次澄清简化了设计**：少一套权限语义（`ROLE_ADMIN` vs 控制台权限码）、少一处"同一份数据两个改法"的双写面，`docs/50 §15.2` 的 G-1/G-10 两条缺口**闭合**；代价是本 PR 删除面变大，故删除清单（`docs/50 §15.5`）明确区分"删 HTTP 面"与"留数据层"。

- **退役复核期发现并修复的真缺陷（2026-09-10 追加二）** —— 这一段是"闭环"真正起作用的地方，逐条都值得记：
  1. **工单零 UI（我自查抓到）**：控制台只有工单 **API**（`listTickets`/`setTicketStatus`）**却没有工单页面**；旧 `AdminTicketController` 一删，用户在 App 提交的反馈/报错/纠误就**没人能处理**。已补 `views/content/TicketsView.vue` + `content/ticketFlow.ts`（状态机可达性 + 处置弹窗含**回复用户**）+ 导航项 + 路由；并把 `TicketRow` 从**臆造字段**（后端根本没有 `subject`）改为与 Java `TicketView` 逐字对齐，接口从 `POST /{id}/status` 改为 `PATCH /{id}` + `adminReply`。
  2. **内容域连 API 都没有（实现方发现，比我那条更严重）**：控制台内容面只有"读 + 上下架"，**没有增删改**。照 v1 的 §10.2 退役旧 `ContentAdminController`/`QuestionAdminController`，会让**全系统没有任何 HTTP 面能新建/编辑歌曲·LRC·场景·听力素材·题目**——运营失去写入路径，`PublishService` 也成半个废功能。**裁决：不删能力，迁到 `/api/v1/console/content/**`**（控制台权限码 + 审计），再删 `/api/v1/admin/**` 原版。**退役原则修正为一句话：「删的是入口与第二套权限，不是产品的写入能力」**（`docs/51 §1.7`）。
  3. **实现方自查抓到 4 个"整条功能静默失效"级缺陷**（`docs/51 §1.6`）：`AuditFieldAllowlist` 的 `Set.of` 重复元素 → `ExceptionInInitializerError` → **每一次审计写入都失败**（而所有不碰审计的测试照样全绿）；`super` 的 `*` 通配在 `admin_permissions` 里无对应行 → **引导出来的超管权限为零**；控制台 CORS bean 名与 `SecurityConfig` 冲突 → `BeanDefinitionOverrideException` → **整个应用起不来**；独立审计路径 `REQUIRES_NEW`/`MANDATORY` 互斥。要求每个都补**在旧代码上会失败**的回归测试。
  4. **前端 DTO 系统性失真（我自查抓到）**：控制台 DTO 是**照设计文档写、在实现之前写的**，于是大面积与真实接口不符——`OpsOverview` 用 camelCase 而 Python 返回 snake_case（运维页运行时全是空值）；`CaseView` 的认领人/决定人是**标量 id** 而 DTO 写成 `{id,displayName}` 对象；`ContentRow` 用**一个形状套四个内容域**而真实是四套不同字段（导致"元数据"列恒空）。已派两路对齐（Python 侧 / Java 侧），并**清理掉 `as unknown as` 兜底**——那种写法是掩盖不是修复。
  5. **权限码数量三处互相打脸**：文档先写 35、又写 36，而 §4.2 表格逐条数是 36、删掉无端点的 `moderation:word:*` 后是 **34**。处置：**数字不在散文里写死，由 `PermissionCatalog` 常量表 + 单测钉死**（`docs/50 §4.2` 已改）。

- **本轮教训（值得写进 SOP）**：① **"设计通过评审"≠"能跑"**——4 个 P0 全是实现期才暴露的；② **凡"退役/删除"清单，每一行都必须配一列"能力迁到哪"**，没有这一列就不算清单（我在 `docs/50 §15.5` 亲手写下"必须复核无功能回退"，然后在同一份文档里**自己违反了它**）；③ **凡能被代码推导的事实，不要在文档里重复声明**（权限码数量是最好的例子）；④ **DTO 必须在实现之后对着源码核一遍**，照文档写的 DTO 会"看起来合理、运行时全空"。

- **DTO 系统性失真：两路对齐完成（2026-09-10 追加三）** —— 这是本轮最贵也最有价值的一段。
  - **根因**：控制台的 DTO 是**照 `docs/50` 写、在实现之前写**的。于是成批出现"看着合理、后端没有"的字段，以及**根本不存在的端点**。危害形态是**静默空白**而不是报错——比崩溃更难发现。
  - **发现量**（两路对齐各自独立发现，完整清单见 `docs/51 §7.3`）：**不存在的端点 3 个**（`PATCH /auth/me`、`POST /auth/password`、`GET /admins/{id}/sessions`）；**请求体字段名错 1 个**（`{newPassword}` vs `{password}` → 恒 46007）；**形状/字段不符 12 处**（`ContentRow` 一个形状套四个内容域且 `meta` 不存在 → 元数据列恒空；`OpsOverview` 全 camelCase 而 Python 全 snake_case；`Violation` 写 `reason` 实际是 `message` → 渲染成 `· lrc：undefined`；`MediaKind` 写了后端 CHECK 根本没有的 `audio`；上架流水是 `operator` 不是 `adminUsername`，`publishedAt` 不存在；会话的 `current` 标记不存在……）。
  - **结构性修复（比逐个改更重要）**：新增 **16 例契约测试**（`api/__tests__/console.contract.test.ts` 8 + `ops.contract.test.ts` 8）。它们**桩掉 `fetch`、捕获真实的 URL/method/body 再断言**（如「metrics 用重复 `metric` + `labels_key` 而不是 `labelsKey`」「`ack` 不带请求体」「overview 键原样 snake_case」），**修复前必红**。审计从 28 → **44 passed**。**纪律在这个问题上已被证明无效**（同类错误连续出现四次都没被拦住），只有会红的测试能拦住第五次。
  - **写进设计文档的契约纪律**（`docs/50 §10.1.1`）：① 端点清单**只承诺路径/方法/权限码，字段形状以实现为准**；② 每个域必须由契约测试钉住；③ 后端不提供的字段**不许在前端编**——要么删显示项并写明"后端未提供"，要么**回头扩后端**。
  - **一个我拒绝的处置**：对齐过程中，控制台的两张运维图（调用量/错误率趋势、按模型调用量）因 `/ops/traces/stats` 不返回 `trend`/`by_model` 而被**删除**，改成"后端未提供"说明卡。技术上诚实，但需求里运维的本职就是"看运行情况/性能 + trace 用于调优参考"，没有趋势、没有按模型拆分的 trace 页答不了"这几天在恶化吗""哪个模型扛的活最多"。**已回派 Python 侧扩接口**（dense 按天分桶 + 按模型聚合 + 直方图重算 p95，禁止平均分位数）。**原则写进文档：「删掉一个功能」与「加一个后端聚合」是两种完全不同的处置——前者要登记为缺口，后者才叫闭环。**

- **顺带修掉一个 CI 阻断（验证时发现）**：Java 契约快照重新生成后，`apps/web/src/api/generated/java-api.d.ts` **没有跟着重新生成** → `frontend-ci.yml:47` 的 `pnpm gen:api && git diff --exit-code -- src/api/generated/` **必红**。已重新生成并验证**幂等**（二次运行文件 hash 不变）。教训：**快照与生成物是一对，改一个必须跑另一个**。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 社区 S2 收口（一）：J-03 通知分页改 DB 层 keyset + SQL 聚合（去 50 条内存窗口）

- **背景**：J-03（docs/41 §1 登记「未实施」）——通知原为「近 50 条互动/评论 → 内存聚合 → 窗口内按游标重筛」：第 51 条及更早**永不可见**（翻页是窗口内反复重筛，与「游标分页可翻页」契约不符）+ 每页 O(窗口) 重算；
- **修复（code 独立提交 `439f5a0`）**：互动组在 SQL 层 `GROUP BY post_id|action|当日UTC` + keyset `(latest_at DESC, merge_key ASC)` + LIMIT 下推；「最新互动者」用 `ROW_NUMBER() OVER (PARTITION BY merge_key …)` 取组内第一行；评论流改原生 keyset `(created_at DESC, id DESC)`（保留 J-04 的 `c.status='visible'` 与排除自身动作）；游标语义不变（`base64(micro(ts)|mergeKey)`）→ **契约零变更**；删掉无调用方的两条旧窗口查询（`findMine`）；
- **测试（`e130d97`）**：`CommunitySocialTest` 跨窗口 2 例（**改前必红**：60 组翻页 seen=10 / 评论 50 封顶）+ PG 集成 EXPLAIN 断言（命中 `ix_post_interactions_post_action` / `ix_post_comments_status_post`）；
- **踩坑**：① H2 的 GROUP BY 校验不接受「SELECT 里 CAST 出来的 merge_key 不参与 GROUP BY」→ 改子查询先算 merge_key、外层按 merge_key 分组；② 接口投影 `Instant getLatestAt()` 在 H2 抛 `Cannot project OffsetDateTime to Instant`（方言差异，见下条统一修复）；
- **门禁**：`mvn verify` 72→**79** 绿、`-Pintegration` PG 集成 7→**8** 绿；契约快照零 diff（`@Hidden` 不计）。

## 2026-09-10 社区 S2 收口（二）：私信 IM 真实化（4 端点 + SSE 长连 + 移动端接真 + 演示种子）

- **背景与拍板（组长 2026-09-10）**：翻 `docs/41`/`docs/02`/`docs/42` 三处「私信不做/演示帧」口径，**私信真实化**、要「和常用社交平台一样的 IM 体感」、只做移动端；联调测试页**不新增**（登记豁免）；模块组织**维持现行规范**（不引入新目录形态）。设计先行：`docs/49-私信（IM）实施设计.md`（定稿）+ 两路子代理拷问（实时通道 / 未读口径，报告在 `local/`，不入库）；
- **设计裁决**：实时通道 = **A · Java SSE 长连（`SseEmitter`）+ 进程内广播 + 轮询兜底**（否决 Redis pub/sub、WebSocket、纯轮询——写方在 Java、写与推同进程零跨服务通道；依据：100 长连内存 <10MB、空闲 0 DB 查询，而轮询 1320 请求/小时/人）；未读 = **会话级水位（`last_read_id`，非时间戳**——时间戳水位在并发提交下会跨过未渲染消息造成永久漏未读）；可见面 = 会话列表未读数字 + 私信 tab 提示（**不碰全局底栏**；底栏红点登记下轮，前置=全局未读聚合 + 实时通道定稿 + bell 语义）；
- **后端（Java 社区主服务）**：迁移 **0012**（`direct_messages` + `dm_read_state`，Python 侧只读映射）→ 4 端点（会话列表 / 未读合计 / 会话消息 keyset / 发送 / 已读，自聊 42203、对端不存在 40402、1~1000 字）+ **SSE** `GET /messages/stream?since`（`@Hidden` 不进契约；连接注册表单用户 ≤3 流、全局 ≤500，超限 429 + `event:error`；心跳 25s；`since` 游标回放断线来信；`@EnableScheduling` 首次启用）；演示种子 `DirectMessageSeeder`（demoadult ↔ demoteen/demosenior，按会话对幂等）；
- **ADR 限定修订（阻断项）**：`docs/06 §1/§8`、`docs/20`、`docs/21 §1.1 例外⑤`、`docs/api/envelope.md` —— 「Java 严禁进 语音/SSE/LLM 热路径」按原意收窄为**语音/LLM 热路径（含其 SSE）；社区域单向 SSE 归 Java**；
- **前端（移动端 only）**：`api/community.ts` 5 函数 + 独立 `openMessageStream`（`audio/sse.ts` 硬绑 PYTHON_BASE/丢弃 `id:` 行 → 本函数 GET+Bearer+`since`）；`stores/messages.ts`（服务端水位真源、乐观发送回滚、SSE 优先→失败降级轮询、双通道按 id 去重）；通知中心私信 tab 与 `/m/messages`、`/m/messages/:id` 接真；删 `data/messages-demo.ts`；搜索页「用户」改真实源；
- **门禁**：Java **79** 绿（私信 7 例）+ PG 集成 **8** 绿；前端 lint/typecheck/**test 223**/build/check-bundle 全绿；pytest **392** 绿；`alembic check` 零漂移；契约快照 55→**60 op** + `gen:api`；
- **三端实测（dev 真栈）**：私信冒烟全绿——会话列表/发送/**未读 +1 → 已读归零**/自聊 42203/对端 40402/空正文 42203/**SSE `event:open` + 实时 `event:message` 帧**；J-03 冒烟——通知 9 条无重复翻页 + `EXPLAIN` 命中两条索引（脚本留 `local/smoke_im.ps1` / `local/smoke_j03.ps1`，gitignored）；
- **真 PG 才暴露的三处方言坑（已修复 + 补集成回归 `399a197`）**：
  1. **未类型化 NULL 游标**：`(:cursorTs IS NULL OR … :cursorKey)` → PG `could not determine data type of parameter $4`（H2 放过）→ 首页改传**哨兵值**（9999-12-31 + 空串 / `Long.MAX_VALUE`）；
  2. **哨兵不能用 `Instant.MAX`**：驱动渲染 `169104627-12-11 … BC` → PG `timestamp out of range`；
  3. **原生投影的时间列类型随方言而变**：同一条查询 PG 给 `Instant`、H2 给 `OffsetDateTime`，写死任一端都抛 `Cannot project …`（本轮两端各撞一次）→ 新增 `NativeProjections.toInstant(Object)` 归一，投影列声明 `Object`；
  - 教训：**H2 绿 ≠ 真机绿**；凡新增原生 SQL（含游标/NULL 参数/时间列投影）必须过 `-Pintegration` 真 PG。
- **登记**：`docs/49`（新，README 索引）、`docs/21`（Java 60 op + 私信行 + 例外⑤）、`docs/10`（待补表清单 38→40 与写方矩阵行）、`docs/13 §8`（联调页豁免）、`README`（能测段/私信 IM）、UI 与交互记录见 `worklog/安卓开发日志.md`；
- **未做/登记**：群聊、消息撤回编辑、图片/语音消息、已读回执给对方看、推送、底栏红点、多副本广播（单实例内存广播；升级走 Redis pub/sub）、消息级已读、发布开关（`VOICEVERSE_COMMUNITY_POST_ENABLED` 默认关，私信不受其影响）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-09 联调发现并修复：读书进度「第二次保存起 500」（ORM 过期属性跨会话访问）

- **怎么发现的**：S3 验收时翻 `local/dev-logs/python-8000.err.log`，看到一串 `DetachedInstanceError`；随后用 live PG 复现：PUT 进度第 1 次 200、第 2 次起 500。
- **根因**：`app/api/routes/reading.py` 的 `put_progress` 在 `_db()` 退出（session 已 close）后访问 `row.updated_at`。该列是 `onupdate=func.now()` 服务端生成列，**UPDATE 路径** commit 后被标记过期 → detached 实例触发刷新 → `DetachedInstanceError` → 500。INSERT 路径（第 1 次）走 RETURNING 已取值，所以既有单测（只 PUT 一次）永远绿。
- **影响**：阅读器每次滚动都保存进度 → **只有每本书的第一次保存生效**，后续静默失败（前端 fire-and-forget 不报错）。
- **修复**：改为**会话内序列化**（`return _progress_dict(row)` 移进 `_q()`，与 `list_annotations`/`create_annotation` 同式）；`get_progress` 一并统一（它此前只是「碰巧没 commit」）。
- **验证**：新增 `TestProgress::test_put_twice_update_path`（连续 3 次 PUT + `updated_at` 非空 + GET 末值，修复前必红）；live PG 三次 PUT 全部 `code=0` 且 GET 返回 300；ruff + 全量 pytest 绿。归档 `BUG实测/读书进度-二次保存500.md`。
- **教训**：ORM 实例不要跨会话边界返回；用例必须覆盖**第二条**写入。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）
## 2026-09-09 社区内容 S3 闭环落地：媒体上传（图/视频/头像）+ 帖子详情 + 划词查义（六路拷问后实施）

- **需求**：社区从「只读流 + 纯文本发帖」补成闭环——发帖（图文/视频）、点帖子有查看方式、用户头像、社区正文划词查义。
- **设计先行**：`docs/47-社区内容闭环（S3）实施设计.md`（v1）→ **六路子代理拷问**（并发性能 / 日志可观测 / 数据模型 / 业务联动 / 模块设计 / 前端 UI-UX，各写报告到 `local/拷问-*.md`，共 128 条）→ `docs/48-社区内容S3拷问报告.md` 合流裁定 **23 条阻断级** → `docs/47` v2 定稿。拷问抓到三处「照稿实现即坏产物」：① `sha256` 全局唯一 + 软删会让「传→删→再传」永久失败；② 暴露 `bigserial` 的 URL 与「不可猜」的匿名读理由自相矛盾（逐号 curl 可枚举全站媒体）；③ 64MB 视频上限被 `nginx.conf` 的 `client_max_body_size 20m` 挡在网关。
- **Python（媒体服务，新域）**：迁移 **0011**（`media_assets`：随机 `public_id` 对外 / 行级去重键 `(owner_id, sha256) WHERE status='ready'` / 物理文件按 sha256 内容寻址共享 / 软删不动物理文件）+ `user_profiles` 补 `lower(handle)` 唯一索引（迁移内先去重）；`app/media/{sniff,storage,service}.py` + `app/api/routes/media.py`（POST 上传 / GET 裸流 **Range 由 Starlette FileResponse 提供** / DELETE 软删 / GET 我的上传）；魔数嗅探白名单（图 jpeg/png/webp/gif、视频 mp4/webm）、分块写盘 + uuid 临时名 + `os.replace`、新限流桶 `media` 60/时；生词本 `POST /reading/vocab` 补 `scene` 入参（`community` 划词来源）并把 check-then-act 改唯一键兜底。
- **日志可观测（阻断修复）**：新增 `app/core/logging.py` 的 `dictConfig` —— 此前全仓无 `basicConfig/dictConfig`，`vocalverse` logger **无 handler，所有 `logger.info` 零输出**（`APP_LOG_LEVEL` 也是死配置）；现在格式含 `%(request_id)s`，媒体域按「上传成功/被拒/404/软删」分级别记录。
- **Java**：`AuthorView` 末尾增 `avatarUrl`（feed/详情/评论/关注一次带回，零额外请求；通知不带，登记 S4）；发帖 `CreatePostRequest` 增 `media` + 新 `MediaRefValidator`（形状/条数/URL 前缀白名单，**拒绝外链**；不强制 kind 与 media 一致，保住既有 `kind=video` 无 media 的契约）；新增 `PATCH /api/v1/users/me`（昵称/@handle/tint/头像；handle 撞唯一键 40904），`GET /auth/me` 扩 `avatarUrl/handle`（**不新增重复 GET**）；`CommunitySeeder` 的 media 时长键改 camelCase（种子视频时长角标此前一直是坏的）。
- **前端**：`api/media.ts`（XHR 上传带进度 + `mediaUrl()` 拼 `PYTHON_BASE`，修复「打包壳里相对路径打到 https://localhost」）+ `api/users.ts`；`types/community.ts` 增 `normalizeMedia()` 兼容三种历史形状；新组件 `MobileAvatar`（收敛 8 套头像实现）/`MobileMediaGrid`/`MobileMediaLightbox`/`MobileVideoPlayer`/`MobileMediaPicker`；新页面 `/m/post/:postId`（详情：作者头像 + 多图 + 视频 + 互动 + 内联评论 + 删自己的帖）与 `/m/me/profile`（头像上传 + 资料编辑）；发帖接媒体选择器；**社区划词**：`useCommunityWordLookup` 复用读书域查词卡/生词本/朗读，来源 `scene=community`；灯箱/播放器/词卡全注册进 `useBackLayers`（否则安卓返回直接退页）。
- **门禁与验证**：Python `ruff check`/`format --check`/**pytest 388 passed**（含 18 条媒体用例：嗅探/超限/元数据/越权/软删/去重与再传/匿名读 + Range 206/416）；Java **mvn verify 65+ 用例**（`CommunityMediaApiTest` 10 条 + `UserMeApiTest` 6 条）；前端 `lint`/`typecheck`/**test:run 202 passed**/`build`/`check-bundle.mjs`（preview 树零体积）全绿；契约快照双端刷新 + `pnpm gen:api`，Python 快照与 `app.openapi()` 对账一致、Java `ContractSnapshotTest` 绿；`check_feature_flags.py` / `check_single_writer.py` 均 ok（本域**不新增功能位**：媒体是真实功能，边界=鉴权+限流+白名单，与音频上传同口径）。
- **基础设施**：`nginx.conf` `client_max_body_size 20m → 64m`（与 `APP_MEDIA_MAX_VIDEO_BYTES` 双写项）、`docker-compose.yml` 补 `./data/media` 卷、`.env.example` 补 `APP_MEDIA_DIR`/`APP_MEDIA_MAX_VIDEO_BYTES`。
- **登记**：`docs/21`（Python 48 ops / Java 端点表 + 限流桶 + 裸流例外第 4 条）、`docs/api/error-codes.md`（新增 40403/41501/42205，拓宽 41301）、`docs/06 §19`（媒体存储/读取口径/上限三处同步/日志/跨服务边界）、`docs/13`（3 个新 token）、`docs/35`（沉浸页例外）、`README` 文档索引；联调测试页 `/preview/community-s3`（含可删清单）。
- **登记的不做项**：媒体物理文件 GC（三条件设计见 docs/48 B19）、签名 URL、作者主页、通知带头像、列表页划词、社区批注（无服务端权威 char offset）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 阅读器批注四连修复（组长实测 BUG记录 → 归档 BUG实测，后端零改动）

- **来源**：`worklog/BUG记录/读书域系列BUG9-09/`（组长手机实测 4 条），修复后**该目录已删除**，逐条归档到 `worklog/BUG实测/读书域批注-*.md`（4 份）。
- **缺陷与修法**（详见归档；UI 细节另见 `worklog/安卓开发日志.md`）：
  1. **暗黑模式批注不可读**：批注色裸写 `background` + night 浅灰墨色 → 对比度 1.05~1.23；改 `--ur-ann-color` + 按主题 `color-mix`（night 24%）+ 文字统一 `--ur-theme-ink`（修复后 5.59~5.95）。
  2. **只能删除、改不了色/笔记**：批注卡改「查看即编辑」→ 走既有 `PATCH /api/v1/reading/annotations/{id}`（`patchAnnotation` 此前全仓零调用，**后端无需改动**）。
  3. **查看批注只能点空格（命中区 4.6px）**：新增句首批注角标（任何 kind 都有；单条直开、多条开本句列表）+ 选中句动作条「看批注」大热区入口。
  4. **点「高亮这句」不等选色**：不传色 → 先开选色面板（未选色禁用保存）；动作条色点仍直出。
- **附带修复**：`createFromSelection` 用 `range.startOffset`（相对选区容器）当句内偏移 → 句内嵌套词块时批注错位，改 Range 前缀长度法；色板收成单一真源 + `safeAnnColor` 白名单（封 CSS 注入/非法值使声明失效）。
- **门禁**：新增「解析 CSS 源文件算 WCAG 对比度」门禁（三主题 × 色板全色 + 最坏色兜底）；**修复前必红证据**：HEAD `63fcaee` worktree + 新测试文件 → 14 条红；修复后前端 lint/typecheck/test:run（178 passed）/build 全绿；`MobileReaderView` 抽 3 个 composable 回到 350 行门禁内。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-10 自由对话「internal」复发：手动起 python 漏 APP_ASR_MODEL（ASR 模型脱绑）

- **复现**：手机自由对话（语音）提示 internal；python `err.log` 见 `LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder ... outgoing traffic disabled`（HF 离线 + 按 repo_id 找模型）。
- **根因**（归档类与 `方式B-Python-ASR-HF缓存失配` 同源）：python 进程环境缺 `APP_ASR_MODEL`（dev-up.ps1 会把其指向 `%USERPROFILE%\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\<rev>` 本地快照；手动 `uvicorn` 启动会漏注入）→ `settings.asr_model=""` → `WhisperModel(repo_id)` → 离线下载失败。
- **修复/验证**：以 `scripts/dev-up.ps1 start` 重启 python（自动注入 APP_ASR_MODEL/HF_HUB_OFFLINE/根 .env）→ `readyz` 的 `asr` 字段已绑定本地快照；机器侧文本回合冒烟 SSE `text_delta` 正常。
- **教训**：**起 python 一律用 dev-up.ps1**（或至少带 APP_ASR_MODEL + HF_HUB_OFFLINE=1）；漏注入的表现是「启动成功、ASR 调用时失败」（预热失败只警告不阻塞）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 后端联调可观测性：java Tomcat accesslog + python 绑 0.0.0.0（手机联调支撑）

- **java**：`application.yml` 开启 `server.tomcat.accesslog`（pattern `%h %t "%r" %s %b %Dms`）。
  踩坑：embedded Tomcat 的 accesslog 相对目录基于 `catalina.base`（TEMP 下随机目录）
  → 用 `${user.dir}/logs` 显式固定到进程工作目录（dev-up 方式 B 即 `services/java/logs/`）。
- **python**：`scripts/dev-up.ps1` 的 uvicorn 补 `--host 0.0.0.0`——打包壳 Web 直调 `http://<局域网IP>:8000`，
  只绑 127.0.0.1 时手机连不到（health 检查仍走 127.0.0.1，不受影响）。
- **背景**：2026-09-10 手机联调「Failed to fetch」排查需要「请求是否到达后端」的确定性证据，
  这条链路（accesslog + python 访问日志）后续所有联调通用（详见 `docs/30` §2 排查顺序）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 打包壳跨域（CORS）补齐：Python + Java 允许 https://localhost 来源（方案 B 直连后端必有）

- **背景**：方案 B 打包壳（页面源 `https://localhost`）直接调本机后端 `http://192.168.0.104:8000/8080`（跨域）。开发时靠 Vite 代理同源、容器靠 nginx 同源，故此前从不需要 CORS——打包壳直连后，浏览器对 `Origin: https://localhost` 发 CORS 预检（OPTIONS），两个后端均无 CORS 处理 → python 405 / java 被安全链拦截（手机端实测日志现 `OPTIONS /api/v1/events → 405`）。
- **修复**：python `app/main.py` 加 `CORSMiddleware`（精确 origins 列表含 `https://localhost`，`allow_credentials=True`——凭据不允许 `*`）；java `SecurityConfig` 加 `.cors(Customizer.withDefaults())` + `CorsConfigurationSource` bean（同名单）。
- **验证**：预检 `OPTIONS /api/v1/events`、`OPTIONS /auth/login`（Origin=https://localhost）→ 均 200 + `Access-Control-Allow-Origin: https://localhost` + `Allow-Credentials: true`；python `uv run pytest -q` **370 passed** + ruff/format 全绿；java 编译运行正常（mvn spring-boot:run 重编译生效）。
- **踩坑**：① CORS 与「安全上下文」是两回事——打包壳解决了 getUserMedia，但跨域请求仍需后端 CORS；② `allow_credentials=True` 时 `allow_origins` 禁止 `["*"]`，必须精确列来源（含 `https://localhost`）；③ 干净重启后端用 `scripts/dev-up.ps1 stop` + `start`（按端口杀进程树；之前手动杀 uvicorn --reload 的父进程留下孤儿 worker 占端口 8000，netstat 显示已死 PID 的僵尸 LISTENING——需按端口 taskkill /T /F 并核实真释放）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 读书域合入 main（组长手机验收后直合 · 15 提交 · 分支 feat/novel-reading-main）

- 组长手机端验收（Web 5173 → APK 壳均已跑通）后授权直合：`git merge --no-ff` → `main 5c10d19..15f774b` 推送成功（CI 三套门禁由 push 触发）。
- 内容：读书域 12 功能提交（模型/迁移/种子/20 端点/听书/前端 4 页/契约/docs45-46）+ 2 组热修复 3 提交（0010 迁移 `_bigint_pk` PK 缺失、登录 40904 refresh token 唯一性）——两组热修复均为组长实跑复现 → 修复 + 回归守卫 + BUG 实测归档。
- 后续排期登记：听书词级时间轴/跨句批注/章节内 TOC/crossfade 见 docs/45 §11（P2 后置）；本地 KittenTTS 启用方式见 README（`uv sync --extra local-tts` + `APP_VOICE_MODELS_DIR`）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 登录偶发 40904 热修复：refresh token 加 UUID 随机因子（组长手机端实测复现 → 修复 + 回归测试 + 真机链路验证）· 3 op

- **复现**：手机（WebView → 5173）登录 `xiaoqing` 报红字「数据冲突：唯一键或约束（重复提交/并发写入）」（Java 40904）。
- **根因**（既有并发竞态，非读书域引入）：`AuthController.issue()` 的 refresh = `jwt.generateAccessToken(...) + "-" + System.currentTimeMillis()`；而 JwtService 令牌 payload 仅 {sub, role, iat, exp}（秒级精度、无随机字段）→ **同一毫秒**双登录/双刷新（双击/WebView 双请求）产出相同 refresh 串 → SHA-256 相同 → 撞 `uq_refresh_tokens_token_hash` → DataIntegrityViolation → 40904。报错发生在密码校验之后，说明 xiaoqing 密码本身正确。
- **修复（code 独立提交）**：`AuthController.buildRefreshToken(jwtToken, nowMillis)` 追加 `UUID.randomUUID()`（refresh 为不透明串、服务端只存哈希，格式变更零兼容影响）；抽 package-private 纯静态便于确定性测试。
- **测试（test 独立提交）**：`RefreshTokenUniquenessTest`（同输入两次构造 → 断言不同；修复前同输入必同串 → 红）；`mvn -Dtest=RefreshTokenUniquenessTest,AuthFlowTest test` 6 passed + `spotless:check` 通过。
- **验证**：重建并重启本机 Java（8080；从根 .env 注入 JWT_SECRET/SERVICE_TOKEN——Maven 子进程不读 .env，手动起服务易漏 P0-9 fail-fast）→ 连续两次 POST /auth/login（demoadult）均 code=0 且 refreshToken 互异、含 `-\d+-<uuid>` 后缀 → 手机端可重试登录。
- **踩坑**（已归档 `worklog/BUG实测/登录-并发refresh-token撞唯一键.md`）：①去重键必须随机源，不可用「无随机令牌+时间戳」拼串；②40904 映射面宽（任何 DataIntegrityViolation），排查看 Java 栈；③本地起 Java 记得 root .env 的 JWT_SECRET/SERVICE_TOKEN。
- **门禁**：Java 子集 6 passed + spotless 绿；Python/前端零改动。未 push（分支 feat/novel-reading-main）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 读书域迁移 0010 热修复：`_bigint_pk()` 补 `primary_key=True`（组长实跑复现 → 修复 + 真 PG 验证）· 3 op

- **复现**：组长本机 `uv run alembic upgrade head` → `psycopg.errors.InvalidForeignKey: no unique constraint matching given keys for referenced table "books"`（建 book_chapters 时 FK 引用 books(id) 被拒；迁移事务回滚后 seed 报 `relation "books" does not exist` 为连锁）。
- **根因**：`alembic/versions/0010_reading.py::_bigint_pk()` 漏 `primary_key=True` → books.id 为普通 BIGINT；PG 对 FK 引用列要求 UNIQUE/PK。模型侧 `base.py::bigint_pk()` 有主键，故 **SQLite 单测（create_all）与离线 SQL 渲染（test_alembic_offline_pg_render 只拼串）都不暴露 → CI 绿真库红**。
- **修复（code 独立提交）**：辅助函数补 `primary_key=True`（8 表共享一处修复）；**回归守卫**（test 独立提交）：`test_models.py` 的离线渲染断言后追加逐表检查——抽取每张读书域表的 CREATE 块断言含 `PRIMARY KEY`（修复前必失败；`READING_TABLES` 常量 8 表）。
- **验证（真 PG16 容器）**：`upgrade head` ✅（原错消除）→ `alembic check` ✅ 零漂移 → `downgrade 0009` + `upgrade head` 往返 ✅ → `seed_reading` ✅（books 3 / dictionary 10,612 / forms 11,501）→ `pg_tables` 8 表齐 → pytest 全量 **366 passed / 4 skipped**。
- **踩坑（已归档 `worklog/BUG实测/读书域迁移0010-PK缺失.md`）**：①离线渲染 ≠ 可执行验证——新建表迁移合入前必须在真 PG 跑 upgrade+downgrade 往返；②迁移辅助函数与模型辅助函数必须同构（base.py::bigint_pk 即为范本）；③seed 报「表不存在」先查 `alembic current`，别先改 seed。
- **门禁**：ruff/format 全绿、pytest 366 passed；前端零改动。未 push（分支 feat/novel-reading-main）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-10 读书域（英文小说阅读）· 后端 + 契约 + 文档（组长午间委托 AI 全自动闭环：需求→四官拷问→实现→测试→文档，分支 feat/novel-reading-main，未 push）· 多 op

- **背景与需求（组长口述 + 截图）**：加「书籍」功能——纯文本阅读、听书（参考 https://github.com/debpalash/VoiceStudio；语音模型可选用 `F:\WorkingL\VoiceStudio\OmniVoiceStudio-Data\data\models`）、点击选词看释义（截图形态：音标+释义+加入生词本+外链）、笔记/生词/划词/批注；**前端只做移动端**；全自动闭环（需求→设计→子代理拷问[数据模型/业务逻辑联动/模块设计/UI-UX]→实现）；新分支不 push。
- **侦察**：VoiceStudio 0.5.1 本机源码复核（`F:\WorkingL\VoiceStudio\OmniVoiceStudio-Data\env\project`——**AGPL-3.0-only**，只借思路：jobs 状态机/进度事件/内容寻址缓存/句级对齐；`/v1/audio/speech` :3900 无鉴权仅 loopback）；本地模型能力清单（**KittenTTS mini 0.8**＝78MB ONNX/CPU 实时/8 英文音色/Apache-2.0 → 本地引擎选型；OmniVoice **CC-BY-NC 禁商用**；CosyVoice3/VoxCPM2 需 GPU；GPT-SoVITS 中文优先）。既有基建：`textproc/sentence_splitter`（分句）、`tts_cache_key/tts_synthesize_cached`（缓存）、SSE helper（practice/events.py + 前端 openSseFetch）、`loadAudioBlob/useBlobAudio`（音频管道）、Agent Lab 式联调页范式。
- **四官拷问（6 子代理并行，docs/46 C-1…C-10 裁决）**：数据模型 V-1…V-20（**P0：content_version 版本守卫**——文本修订后批注/进度不静默错位；events.event_type 硬编码 CHECK 需扩值；tts_tasks.error 用 jsonb 对齐惯例；+ dictionary_forms 词形反向索引——"inventions"→"invention"）；业务逻辑 B-1…B-22（**只扣真实合成**·命中缓存 0 扣·prepare 按章扣 1；按 provider 分缓存目录防 wav/mp3 混标；埋点四处同步；SSE 独立协议 task_start→sentence_progress*→task_done + 快照兜底）；模块工程 M-1…M-18（reading/ 三件套；迁移 0010 一次 8 表；契约 21→41 ops；**联调页 A 落法**＝ReadingPreview 直调真路由，CommunityPreview 前例，无 test-only 端点；前端 fe-08 行数门禁——阅读器拆 5 composables + 3 弹层组件，不进灰名单）；UI-UX U-1…U-22（**设计语言定 u-*（当前 14 页实况）**，新类 u-rd-*/u-bs-*/u-bd-*/u-vb-* 前缀；词卡＝底部 sheet；生词本 /m/vocab 唯一入口；TabBar group 增补；正文衬线豁免）。
- **实现（code）**：`app/models/reading.py` 8 表（books/book_chapters/dictionary_entries/dictionary_forms/user_reading_progress/user_vocabulary/reading_annotations/tts_tasks）+ 迁移 `0010_reading.py`（0007 双方言风格 + events CHECK 扩 5 值，0006 NOT VALID 姿势）；`app/reading/`（split 纯函数[服务端权威句切分+offset 坐标系]/normalize[词归一化]/service[DB 函数组]/tts_cache[provider 分目录]/tts_client[DI·auto=edge|kitten]/orchestrator[asyncio 后台任务+进度+取消+启动扫孤儿]/events[SSE 模型]）；`app/audio/tts_local.py`（KittenTTSClient：lazy import、三要素探测、24kHz wav 输出）；`routes/reading.py` + `routes/reading_tts.py`（20 op；音频端点裸流 audio/mpeg|wav；prepare SSE 经 heartbeat_stream）；`seed_reading.py`（公版书 3 本：Alice 12 章/傲慢与偏见 49 章/绿野仙踪 24 章，`data/seed/reading_books.json` 916KB；ECDICT 子集 10,612 行 2.4MB `data/seed/ecdict_subset.csv`）；config 增 reading_tts_provider/rate 600/voice_models_dir；pyproject optional `local-tts`（kittentts）。
- **测试（test）**：新 45 例（split/normalize 纯函数·service 词形/幂等/越界/归属·routes 四件套·tts 缓存命中 0 扣/SSE 序列/快照/取消/sweep）；修复前必失败（全新实现全红→绿）；基线用例同步（事件 15→20 类断言、EXPECTED_TABLES +8）；全量 **366 passed / 5 skipped**（基线 318+7）；契约快照 `app.openapi()` 离线导出 + `pnpm gen:api`（零手改）；冒烟 `services/python/data/smoke_reading.py`（建表+种子+全端点：lookup 词形解析/vocab 幂等/批注 45004/进度/segment 缓存命中/voices 全通）。
- **踩坑（供复盘）**：① `body.get('start_offset') or -1` 把 0 变 -1（falsy 短路）→ 45004 假阳性；② orchestrator `_update_task` 签名缺 `total` 参数 → SSE 卡死（**任务级异常被通用 except 兜住但事件未发**——测试要断言「终态必达」；另修复「消费方在任务瞬时完成后按 id 取队列拿空队列」竞态：`start_task` 返回队列引用）；③ 测试 `iter_lines(decode_unicode=True)` 与 httpx 版本不兼容；④ `:memory:` StaticPool 下 Session 跨线程（loop↔to_thread）在既有 practice 语义内可用（创建/关闭在 loop、查询在 worker，勿在 loop 线程操作查询结果）；⑤ **日志更新教训：工作日志必须「先读全量 + edit 置顶插入」，禁止整文件 write 覆盖**（本批曾误用 write 覆盖两条日志，已 `git checkout` 无损恢复并按正确姿势重写）。
- **文档（docs）**：docs/45 设计定稿 + docs/46 四官合流 + docs/10（写方矩阵 +8 表 + 30→38 口径更正）+ docs/21（ops 21→41、限流表 reading_tts、§1.1 例外）+ docs/api/error-codes.md（45001~45007 先登记）+ docs/06 §18 登记（provider 链/桶/事件/合规）+ README（功能行/演进方向①落地标注/文档索引 45-46/仓库结构/能测清单）；UI 部分记录见 `worklog/安卓开发日志.md`（2026-09-10 读书域前端）。
- **门禁**：Python ruff+format 全绿、pytest **366 passed**；前端 lint/typecheck/test **129 passed**/build 全绿、check-bundle ✓（preview 树零体积含 ReadingPreview 剔除断言）；单写探针/功能位对账零改动。**未 push**（组长验收后推）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-10）

## 2026-09-09 fe-09：vite 构建拆分（manualChunks）+ 包体积门禁（组长继续遗留项）· 2 op

- **背景**：fe-09（治理 P2 遗留，组长继续）——vite manualChunks + CI 断言产物不含 preview/p5/echarts 模块；此前无任何包体积门禁（preview 树生产剔除/懒加载拆分全靠约定无人验证）。
- **实现（code 独立提交）**：① vite.config.ts `build.manifest=true` + `manualChunks`（naive-ui / p5 / echarts / vue-vendor / vendor 专块——p5/echarts 保持动态 import 独立块防合流，vue 栈快照块提高缓存命中）；② `apps/web/scripts/check-bundle.mjs` 门禁——**按 rollup manifest 源模块路径判定**（初版用正文字符串 `createCanvas`/`preview` 命中我方代码误报 2 处：`p.createCanvas()` 是业务调用、DemoView 注释含「preview」词——改 manifest 图判定消除猜测）；断言：preview 树零体积（docs/13 §8 dev-only 剔除承诺的机器验证版）／专块齐（naive-ui/vue-vendor/vendor/p5 落盘）／p5 禁入入口塔（仅录音声波页面块触发加载）／echarts 零残留（仅 preview 树使用）；③ frontend-ci.yml Build 后追加步骤（本地 yaml.safe_load ✓）。
- **关键结论（实测，诚实口径）**：naive-ui **不能**从入口移除——App.vue 根 Provider（NConfigProvider/NDialogProvider/NMessageProvider）架构必需首屏加载；manualChunks 的实质价值 = ①独立可缓存块（业务发布不重拉 naive-ui/vue 栈；应用代码 entry 30.86kB vs 此前 296.91kB 一体块）②p5/echarts 懒加载保持（防合流入主块）③**门禁固化**（preview 剔除/p5 拆分/echarts 零残留从此机器可验证，防回潮）；移动端 WebView 每页面只拉自身 1~16kB 块 + 共享专块。
- **门禁（改后基线）**：前端 lint（新 mjs 纳入扫描，顺手抓出一处 unused 变量已修）/typecheck/build 全绿、`test:run` **115 passed**（基线保持）；`node scripts/check-bundle.mjs` ✓；frontend-ci 新增步骤 yaml.safe_load ✓；Python 零改动。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 TTS 预合成预热（docs/06 §8「开场/常用句预合成」兑现 · 组长拍板）· 3 op

- **背景**：组长注意到 docs/audit「预合成/预热零落地」，问询确认价值——开场白/示范句首次合成 ~1.3s（edge-tts 网络往返，POC-1）→ 预热后 0ms 命中缓存；「3~5s 反馈」口径里 TTS 的 1~2s → ≈0s（首声 P50 下降的答辩证据加强项）。勘察澄清：**懒加载缓存实际已落地**（`tts_synthesize_cached`，docs/44 P1-B：/tts 与热路径共用，TTL 1d/512MB/原子写/容量裁剪），差额只在「预热」环节。
- **实现（code 独立提交）**：`tts.py` 增 `warm_tts_cache(tts, texts, voice, rate)`——只补缓存（命中即跳过）+ 并发限速 4 + 文本去重 + 单句失败仅日志（预热不阻塞/不上抛）；`app/audio/warmup.py`——`collect_warm_texts`（保序去重）／`scenario_warm_texts`（开场白 + target_corpus 短语）／`schedule_startup_warmup`（main.py lifespan 后台异步，不阻塞启动；testing 跳过）／`schedule_texts_warm`（create_session 后 fire-and-forget）；service.py `_create_session_sync` 顺带产出 warm_texts 三元组。已知文本 = published 场景开场白 + 语料短语 + 影子逐句示范；**LLM 流式回复正文不可预知**——仍走 P0-5 边生成边合成（已是最优）。
- **测试（test 独立提交）**：`test_tts_cache.py` +3（去重/空白跳过/二次命中零触引擎、键维度、失败容忍）；`test_warmup.py` +4（collect 保序去重、scenario 文本集、空场景零成本、testing 静默跳过）。
- **文档（docs 独立提交）**：docs/06 §8 首声预算行补「2026-09-09 落地 开头/常用句预合成」；docs/audit V2.0 预合成行更新（懒缓存已落地 + 预热已落地 + 死代码清理登记）。
- **门禁**：Python ruff+format 全绿、`pytest -q` **325 passed**（318+7）；前端零改动（预热纯服务端）。
- **收益口径**：开场白（点播放 1.3s → 0ms）/ 示范提示句（8s 救援窗口内 0ms）/ 重听（热路径已缓存）——首声 P50 下降；RTF 不变；CI 零外部依赖（Fake）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 治理 P2：eslint 行数/语句门禁 + 功能位三处对账 + 语音链路杂项 · 7 op

- **fe-08（eslint max-lines/max-statements）**：`eslint.config.js` 启用 `max-lines: error {350, skip 空行/注释}` + `max-statements: error {60}`；生成物 `src/api/generated/**` 加入 ignores（gen:api 再生成，不设行为准则）；**灰名单** = 存量超限 8 文件（MobileSpeakingView 753 / LoginView 522 / UicHome 478 / FluencyPreview 434 / PracticeView 432 / UicSinging 402 / MobileFreeChatView 357 / UicSpeaking 354 → max-lines off）+ 5 文件函数体语句超限（max-statements off）；`--print-config` 验证灰名单=0(off)、常检文件=2(error)；lint 全绿——**新代码不豁免，重构时摘名单**。
- **arch-04（功能位/配置开关三处对账）**：docs/06 新增 **§17 功能位/配置开关登记表**（7 项：APP_META_LLM_HITS / APP_SKILL_CALLBACK / APP_LEARNER_INJECTION / APP_AGENT_LAB / APP_FLUENCY_PREVIEW / APP_SHADOW_PREVIEW / VOICEVERSE_COMMUNITY_POST——默认值/位置/README 登记要求）；`scripts/check_feature_flags.py`（纯函数 parse_registry/check_rows：Python config.py **词边界**字段 / Java application.yml 环境变量 / README 对外演示登记，退出码 1=漂移）+ **python-ci 门禁步骤**（本地 yaml.safe_load 通过）+ 单测 4 例（解析 / 缺字段红 / 词边界冒充红 / README 漏登记红）。实测 7/7 ✓。
- **杂项**：① `app/audio/tts.py` 删除 `synthesize_concurrent`——全仓零生产调用（docs/19 评审早已举证「定义后全仓无人调用」）；py-08 对应用例一并移除（10→9 例），docs/audit 预合成行注明清理；② docs/audit V2.0:143 edge-tts 许可 **GPL-3.0 → LGPLv3** 更正（+ 微软服务条款标注保留）。
- **⑤ 纯渲染核心（TODO 登记）**：textproc 已有 splitter+normalize；抽 render core（注入 synth 闭包，M3 唱歌/听读共用）——**折期**：仅当 B4 词级时间轴视图消费完成（移动端已落地）+ 排期允许再做；当前登记 P2，听读/跟唱批次设计时评估。
- **fe-09 暂缓（组长指正 2026-09-09：优化以移动端为准）**：vite manualChunks + CI 产物断言属 Web 端构建治理，暂缓登记（重构 Web 构建时一并做，避免无效投入）。
- **门禁（改后基线）**：Python ruff+format 全绿、`pytest -q` **318 passed**（315−1 死代码用例 +4 对账用例）；前端 lint（新规则生效）/typecheck/build 全绿、`test:run` **115 passed**；功能位对账脚本实测 7/7 ✓。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 B4 后端补强：词时间轴持久化（用户消息 meta.words）+ 恢复端点回带 · 1 op

- **背景**：B4 前批 turn_end.words 仅 SSE 流内快照（未落库）——断线/刷新后词级对轴素材丢失；移动端点播自己录音需要「消息 → 词时间轴 + 录音 URL」成对可查。
- **实现（code 独立提交）**：三类回合用户消息 meta 附 `words`（dialog `_persist_dialog_turn` 增参 / defense / shadow 落库处）；`GET /sessions/{id}` 恢复响应 messages 增 `words`（meta 读取，无词缺省）——回合外（恢复/回放）仍可按词对轴。
- **测试（test 独立提交）**：`test_session_restore.py` +1——meta 持久化词时间戳 + audio_url 随恢复端点回带（修复前：响应无 words 字段，红）。
- **门禁**：Python `ruff + format --check .` 全绿、`pytest -q` **315 passed**（314+1）；契约快照**零 diff**（响应体无 OpenAPI schema 绑定，committed==live 断言通过）；前端侧见安卓日志（移动端断线重连 + 词级高亮，115 passed）。
- **组长指正登记（2026-09-09）**：优化系列以**移动端为准**，网页端暂缓——桌面端已落地功能保留，新投入优先手机端。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 B4：词级时间轴（SSE turn_end 附 words 快照 + golden 双端 + 前端逐词高亮纯函数）· 4 op

- **背景**：任务 B4（词级时间轴，M）——fluency.py 已产 ASR 词级时间戳（whisper word_timestamps），但 SSE turn_end 不回带，前端无法逐词高亮/回放对轴。
- **后端（code 独立提交）**：`TurnEnd` 增 `words: list[dict] | None = None`（exclude_none 兼容：无词时字段缺省，旧端安全忽略）；三类回合（dialog/defense/shadow）ASR 结果处捕获 `res.words`，normal/retry 回合 turn_end 回带快照（ASR 失败/轻回合零词 → 缺省）。
- **契约（golden 双端，test 独立提交）**：`sse_event_cases.json` 增 `turn_end_with_words` 用例（payload 由事件模型生成、字节级）；后端 golden `_build` 映射 + exclude_none 语义补 words 缺省断言；前端 golden 测试同语料自动覆盖（parseSseBuffer 逐样例断言）。
- **前端（code + test 分提交）**：`sse-types.ts` TurnEndEvent 增 `words`；`audio/word-timeline.ts` 纯函数（`normalizeTimeline` 过滤坏条目按 start 升序 / `startedWordIndex` 逐词高亮下标 / `timelineProgress` 回放进度 0..1，容忍口径同后端 fluency.py）+ vitest 3 例（归一化/下标边界/进度 clamp）。
- **门禁（改后基线）**：Python ruff+format 全绿、`pytest -q` **314 passed**（基线保持，golden 用例并入既有测试）；前端 lint/typecheck/build 全绿、`test:run` **112 passed**（基线 109+3）。
- **遗留登记**：① 逐词高亮**组件**消费（用户声泡回放对轴）未接入视图——纯函数层本批交付，组件层随 D（听读/跟读）批次接入；② `turn_end.words` 仅回合 SSE 流内快照，未落库（scenario_messages.meta 现只存流利度特征），恢复端点不回带词时间轴——按词回放需持久化（P2）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 R-13：会话恢复端点（GET /sessions/{id}）+ 前端断线重连 · 6 op

- **背景**：docs/21 §5 R-13（docs/19 P2-4）——无会话恢复端点，双端轮次状态机无恢复路径，一次断线即永久错位（40903 stale turn）；`turn_end` 权威 `expected_turn` 已于 2026-09-08 落地（前端已采纳），本批补恢复端点 + 断线重连。
- **后端（code + test 分提交）**：`GET /api/v1/sessions/{id}`——归属校验（P0-3，不拥有 → 40401）；返回运行态 state/current_turn/next_seq + `next_expected_turn` + 最近 12 条消息快照；**StateStore 优先**（运行态真源），**缺失时按 scenario_messages 权威历史重建**（state.py 注释口径「权威历史永远在 scenario_messages」：current_turn=user 消息数、next_seq=max(seq)+1；status 映射 active→awaiting_user / completed→completed / abandoned→concluded）；已完成会话回带 report_id（前端直接跳报告页，P0-8 短路语义复用）。测试 `tests/test_session_restore.py` 5 例：live 初始态 / 运行态优先于消息 / 状态缺失重建（current_turn=1、next_seq=4）/ 已完成回带 report_id / 越权 40401。
- **前端（code + test 分提交）**：`practice.ts` 增 `fetchSessionRestore` + `SessionRestore` 类型；PracticeView `boot()` 检测 `?session=<id>` → `resume()`：重建气泡与轮次（`next_expected_turn` 权威修正「第 N 轮」），status=completed 直接 `router.push('/report/{id}')`；无 query 保持原新建路径。测试 `PracticeView.test.ts` 3 例（**修复前失败证据**：还原旧视图跑新测试 **2 红 1 绿**——无恢复逻辑时 fetchSessionRestore 零调用、不跳报告页；修复后 3 绿）。
- **契约**：快照单行 compact 刷新（21 ops）+ `pnpm gen:api`（python-api.d.ts +58 行）→ 本地 committed==live 断言通过；docs/21 §2.1（新增 row 9 + 操作数 20→21）/ §3.1（turn_start/turn_end 事件表字段校正 + 目标态改「已落地」口径）/ §5 R-13 行状态更新。
- **门禁（改后基线）**：Python ruff+format 全绿、`pytest -q` **314 passed**（基线 309+5）；前端 lint/typecheck/build 全绿、`test:run` **109 passed**（基线 106+3）；契约快照零 diff（已同步）。
- **遗留登记**：移动端 MobileSpeakingView 断线重连未接（本轮覆盖桌面端练习页，移动端 P2）；turn_start 未回带 next_expected_turn（docs/21 已按实现口径校正为仅 turn_end 权威回带）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 py-08：非 testing 真实路径矩阵（mock 外部依赖直测真客户端 + /turns 真编排）· 2 op

- **背景**：任务 py-08（M）——`tests/` 非 testing 真实路径矩阵；模板 `tests/rec/test_recommend_redis_cache.py`（fakeredis）：依赖注入 + monkeypatch，测真实实现而非 Fake 打桩。
- **实现（test 独立提交 33683ce）**：`tests/test_client_realpath.py` 10 例，三部分：
  1. **EdgeTTSClient 真实路径 4 例**：`monkeypatch.setitem(sys.modules, "edge_tts", …)` 替换模块，直测 `_stream_audio`——只收集 audio 块、忽略 WordBoundary 元数据；voice/rate 透传（空值回退构造参数 or 链）；无 audio 块明确 `RuntimeError`（不静默返回空）；`synthesize_concurrent` 多句并发全部成功且无丢句。
  2. **DeepSeekLLMClient 真实路径 5 例**：`httpx.MockTransport` 注入 `c._client`，直测 `chat_with_usage`（内容+usage 解析、prompt 含 json 时 `response_format={"type":"json_object"}` 断言）与 `stream_rich`（delta 拼接、usage 提取、`asyncio.gather` 并发双流结果一致、`data: not-json` 畸形行跳过容错）。
  3. **/turns 编排真实路径 1 例**：MockASR/MockLLM/MockTTS/MockScorer 构造 `PracticeOrchestrator`，`monkeypatch app.api.routes.practice.get_orchestrator` 注入，真编排 `run_turn`（真 DB 建 Scenario、真 state/SSE/corpus 规则命中/TTS/turn_end）——断言事件序列 user_transcript/turn_start/text_delta/audio_chunk/meta_block/turn_end、`meta_block.coach_note`、`corpus_hits` 命中、`turn_end.expected_turn==1`。
- **门禁（改后基线）**：`uv run pytest -q` **309 passed**（基线 299 + 10）；`ruff check .` + `ruff format --check .` 全绿（提交前文件级 4 个 ruff 错：I001 / SIM905 / 2×E501，已修）。
- **触发路径**：`pytest tests/test_client_realpath.py`——真实客户端代码、仅 mock 外部依赖（edge_tts 模块 / httpx transport），零网络零密钥零 GPU。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-09 va-09 批：语音链路分阶段基准脚本 + CI 操作数/时延预算门禁（本记录为补录）· 4 op

- **背景**：任务 va-09（M）——基准脚本产出「录音后 3~5s 反馈」答辩证据；分阶段计时与真实 /turns 热路径同源。
- **产出（feat/ci/docs 三提交已在本地 main：e27fec4 / 28f3de5 / 6bb2257）**：
  - `scripts/bench/pipeline_bench.py`（389 行）：分阶段 upload → ffmpeg → ASR(words) → LLM ttfa → TTS 首声 → 排播（全链路），输出每阶段 mean/p50/p95/RTF + tracemalloc 峰值内存 + STAGE_BUDGETS 操作数预算 PASS/FAIL；`--speech`（faster-whisper small + DeepSeek + edge-tts，需 .env 密钥与本地模型）/ `--audio <file>` / `--fake`（零模型零 Key；ffmpeg 用 stdlib 生成 1s 静音 wav 走真实二进制）；`--check-budget` 超预算退出码 1。
  - 判定口径（docs/06 §8 延迟表 + POC-1）：RTF ≤0.6 → 演示话术「3~5s 反馈」；0.6~0.8 → 「5~8s」。
  - `python-ci.yml` 增 `--fake --runs 3 --check-budget` 步骤（CI 门禁，本地 yaml.safe_load 通过）；`services/python/README.md` 增「基准脚本」节（用法 + 判定口径）。
- **验证（本次复测）**：`uv run python ../../scripts/bench/pipeline_bench.py --fake --runs 3 --check-budget` → 各阶段均在预算内，结果「通过」，峰值内存 1.3 MiB；python-ci.yml `yaml.safe_load` OK。
- **备注**：本段批次提交时缺 worklog 置顶记录（协作纪律「每段工作主线 worklog 置顶 + 署名」），现补录对齐。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-09）

## 2026-09-08 前端 P1 批（Web/埋点部分：fe-02 / fe-05 / fe-06 + fe-07 Web 侧）· 8 op

- **fe-02（S）答辩页 SSE 取消**：DefenseView 两处 streamTurn（sendServe / answer）补第 5 参 `abort.signal`（此前缺省 → openSseFetch 不传 signal，组件卸载后连接最长挂 90s idle 超时，占用服务端流式推理资源）；`onUnmounted` 补 `abort.abort()`；`startSession` 重建 controller（「重新生成」语义）。与同仓 MobileSpeakingView/PracticeView 取消行为对齐。
- **fe-07（S，Web 侧）报告跳转定时器清理**：DefenseView `session_end` 的 1200ms `setTimeout` 存入 `reportTimer`，`onUnmounted` 清理——用户收尾窗口内返回/切页不再被拽回 `/report/{id}`。
- **fe-05（XS）埋点不阻塞关键链路**：PlacementView `upload()` 的 `await track('recording_complete')` 与 `finish()` 的 `await track('practice_complete')` 改 fire-and-forget（`void ... .catch(() => undefined)`）——此前埋点往返拖住 `uploading` 按钮，事件服务不可达时「下一题」被卡到 fetch 超时；与 recording_start 既有口径统一（注释同步为「埋点一律 fire-and-forget，不阻塞关键链路」）。
- **fe-06（M）埋点可靠性**：① events.ts 注释「10 类事件」修正为「13 类」（union 实际 13 成员）；② `router/index.ts` afterEach 补 `page_view` 上报（fire-and-forget；此前 page_view 声明零调用，核心页面曝光指标恒无数据）；③ 关键转化事件（`scene_start` / `practice_complete` 全部调用点）加 `beacon: true`——实现为 `keepalive: true` fetch（**sendBeacon 无法携带 Authorization header，本接口经 get_current_user_id 鉴权，故改用 keepalive**；页面卸载/刷新/路由切换边界事件不再静默丢失）。free_chat_switch/free_chat_rate 仍为「声明未接线」（docs/14 规划事件、当前 UI 无接线点，按评审「或删除」暂保留在 union 供后续功能使用）。
- **测试（test 独立提交）**：`api/__tests__/events.test.ts` 4 例（beacon→keepalive 断言 / 默认无 keepalive / 失败静默）；`views/__tests__/DefenseView.test.ts` 2 例（卸载 abort 断言 + session_end 卸载不跳转）。
- **修复前失败证据**：stash 源码（保留新测试）后跑新测试——**8 例红**（events 1 / community 4 / DefenseView 2 / MobileSpeakingView 1），逐一对应缺陷：events `beacon keepalive` 断言失败；community「旧请求覆盖新 domain：expected [1] to deeply equal [2]」；DefenseView「expected null to be truthy」= streamTurn 无 signal、session_end 卸载后 push 仍被调（`expected "push" to not be called at all`）。
- **门禁（改后基线）**：`pnpm test:run` **106 passed**（基线 95 + 11）；`pnpm lint` / `pnpm typecheck` / `pnpm build` 全绿；契约零 diff（纯前端，无后端/契约改动）。
- **遗留登记**：fe-04 虚拟化登记 P2（本轮做上限裁剪 + 懒加载确认，详见安卓日志）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 收尾：**双端门禁 + 全量 48+299+95 绿**（踩坑：共享 H2 上下文污染）· 12 op

- **全量门禁（改后基线）**：Java `mvn verify` **48 tests 绿**（基线 36 + 新增 12：J-01 并发 2 / J-02 禁用 1 / J-04 软删通知 1 / J-05 往返恒定 1 / J-06 limit+往返 1 / J-08 错误体 6）+ spotless 绿；`mvn verify -Pintegration -Dtest=CommunityPgIntegrationTest` **6/6 绿**（真 PG）；Python `ruff + format + pytest -q` **299 passed**（基线保持，本批 Java 侧不动 Python）；前端 `pnpm lint/typecheck/test:run/build` 全绿（**95 tests**，基线保持）；`ContractSnapshotTest` 对账通过（J-06 契约变更已同步快照+gen:api，python 快照零 diff）；java-ci.yml 本地 yaml.safe_load 校验通过；
- **踩坑（全量门禁抓手）**：① **共享 H2 上下文污染**——所有 @SpringBootTest 用同一 `jdbc:h2:mem:vocalverse;DB_CLOSE_DELAY=-1`，新测试类若提交真实数据（J-01 并发测试必须提交；J-08 错误体测试当时未挂事务）会在类间残留帖子 → CommunityApiTest「初始 feed 空」断言红（单跑绿、全量红，典型的顺序依赖 flaky 形态）。处置：ErrorEnvelopeTest 挂类级 @Transactional（无跨请求提交需求）；LikeConcurrencyTest（无法回滚）@AfterEach 按 FK 安全顺序清理 j01_* 行（likes/interactions→posts→profiles/tokens→users）——**回归教训：新增提交型测试必须自带清理或挂事务**（已写进两个测试类注释）；② J-01/J-05 等批次提交时未跑 spotless（`mvn test` 不触发 spotless:check——它绑 verify 阶段），CI 的 verify 会红 → 已用 `spotless:apply` 补齐（style 独立提交），最终 verify 全绿；
- **批次结论**：J-01/J-02/J-04/J-05+J-11/J-06/J-07/J-08 七项全部落地（J-03 按 L 级口径登记不实施，后续项见 docs/41 §1），每项 code/test/docs 三分提交 + chore(contract) + style 补齐 + 本记录；本地 main 领先 origin/main **24 commits**（推送待组长授权）；
- **遗留提醒**：`docs/42-App功能说明书.md`（他人产出）仍未入库，请组长确认归属后自行提交。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ⑦：J-07 Testcontainers 真 PG 集成（6 例 · 抓出 timestamptz 舍入口径差）· 25 op

- **背景**：review-java.json（java-07，确认）——pom 无 testcontainers、无 @Tag("integration")、H2 create-drop 从头至尾；**部分唯一索引 uq_posts_checkin / JSONB / timestamptz(6) 微秒 / GREATEST / ON CONFLICT 从未在真 PG 验证**（H2 MODE=PostgreSQL 近似；42P18 未类型化 NULL 是「H2 全绿掩盖真机 500」前车之鉴）；
- **实现**：pom 加 `org.testcontainers:postgresql + junit-jupiter`（test scope）+ surefire `<excludedGroups>${surefire.excludedGroups}</excludedGroups>`（默认 integration，`-Pintegration` 覆盖为空→全跑）；`CommunityPgIntegrationTest`（@Tag("integration")）——Testcontainers 起 postgres:16-alpine → **Alembic `uv run alembic upgrade head` 建真 schema**（dp: APP_DATABASE_URL 指向容器；schema 真源=迁移，杜绝「Hibernate create-drop 假绿」）→ 裸 JDBC 断言 6 例：① uq_posts_checkin 部分唯一索引（每日一卡×同日 article 豁免×异作者豁免）；② GREATEST 减到 0 护底；③ ON CONFLICT DO NOTHING 幂等（J-01 依赖语义）；④ JSONB 写入往返 + jsonb 相等（键序无关）；⑤ **timestamptz(6) 微秒**；⑥ **EXPLAIN**（enable_seqscan=off）feed 混排/领域查询反向扫描命中 ix_posts_feed_time / ix_posts_domain_time + Backward（J-11 证据落地）；
- **重大发现（⑤，集成测试的价值兑现）**：PG timestamptz(6) 对纳秒输入**四舍五入**（.123456789 → .123457），而 `CommunityService.micro()` 是 **%1000 截断**——口径差真实存在；核实读路径（实体值均从 DB 读回、已 6 位）无碰撞，keyset 游标安全，仅「以写入期 9 位 Instant 做游标」的未来场景会差 1µs → 登记 docs/37 §9（断言改为「舍入后的微秒键相等」+ 上/下舍入双边界）；
- **踩坑（环境级）**：① 本机 Docker Desktop 4.69（Engine 29.4.0）下 testcontainers 1.19.8/1.21.3 的 docker-java 命名管道协商全败（ping 400 BadRequest，`docker_cli` pipe 在 4.69 已非完整 API——CLI/Python testcontainers 都正常，唯 docker-java 挂）；**官方 issue #11422 处置 = 1.21.4**（维护者 eddumelendez 指定），升后即通；② Docker Desktop 开机未启动时集成测试自动 skip（assumption，不破坏默认门禁）；③ surefire 版本属性覆盖 BOM 用 `<testcontainers.version>`；
- **验证**：`mvn verify -Pintegration -Dtest=CommunityPgIntegrationTest` **6/6 绿**（含 alembic 迁移跑通）；CI 默认档（`mvn verify`，排除 integration）不受影响；契约快照零 diff（本次 Advice 不涉接口）——J-06 的 limit 参数另走 chore(contract) 提交；
- **登记**：pom/README/github java-ci（注释登记 -Pintegration 用法与前置 Docker+uv）/docs/37 §9（PG-only 用例落地 + micro 舍入口径）/工作日志。yaml.safe_load 校验 java-ci.yml 通过。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ⑥：J-06 收敛（推荐关注 3N+1 + 巨型 IN → 批量 + EXISTS；J-03 登记口径）· 14 op

- **背景**：review-java.json（java-06，确认）——recommendations() users.findAll() 全表 + 每用户 2 次 loadAuthors + 1 次 follows 判定（3N+1）；followingFeed 把全部 followeeIds 塞 IN（数万级列表索引失效）。二者均为用户可见端点、演示期简化注释在案；
- **修复（code）**：① recommendations 改**候选分页**（`?limit` 默认 50/上限 100，服务端 clamp；users 分页不再全表）+ **批量作者一次 loadAuthors + 批量关注 `findByFollowerIdAndFolloweeIdIn` 一次判定**（3 查询恒定）；② followingFeed 改**相关 EXISTS 子查询**（follower=:me AND followee=p.author_id，命中 ix_follows_followee）+ `countByFollowerId` 空关注快检——不再拼巨型 IN；
- **测试（test）**：`CommunitySocialTest` 增 `recommendations_limit_and_constant_roundtrips`：limit=3 只回 3 条（改前：全表 10 条）、Hibernate Statistics 往返 ≤8（改前：1+7×3=22+）。**改前失败证据**：stash 后实跑 → `expected 3 but was 10`（全表返回）；改后 7 例全绿；
- **J-03 登记（L 级 · 按任务口径登记不实施）**：notifications 的 50+50 内存窗口 + 窗口内重筛是**有意的演示期简化**（代码注释 + docs/41 §1 登记）；第 51 条起数据丢失（正确性）+ O(窗口) 每页重算（性能）为真问题——**后续项**：DB 层 keyset 分页 + SQL 层 mergeKey 聚合（或物化通知表）+ EXPLAIN 验证（posts 侧证据链已在 J-07 完成）；当前演示量级无法感知，随规模升级验收；
- **登记**：docs/41 §1/§2/§3（J-06 收敛口径 + J-03 后续项清单 + 契约 limit 行）；docs/37 §9。**契约变更**：/follows/recommendations 加 `limit` 参数 → 快照 + gen:api 已刷新（chore(contract) 提交）。
- **门禁**：子集 7 例绿；全量在批次收尾统一跑。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ⑤：J-05+J-11 读路径批量聚合（评论 N+1 消除 + readOnly 事务）· 12 op

- **背景**：review-java.json（java-05 确认：comments() :180 逐条 map(toCommentView)，每条 loadAuthors=2 查询（users+profiles），20 条页≈41 次往返且无事务（open-in-view=false 每调用一 session）；java-11 确认：feed/comments/followingFeed 等 7 个读方法均无 @Transactional + J-05 同根因（整体读放大，反向扫描待 EXPLAIN 证据——正式考证放 J-07 集成）；
- **修复（code）**：① `comments()` 改**批量聚合作者**——先收页内全部 authorId → 一次 loadAuthors → 逐条组装（与 buildViews 同构）；抽出 `toCommentViews(List)` 复用，addComment 单条路径收敛委托；② 7 个读方法（feed/detail/comments/followingList/recommendations/followingFeed/notifications）加 `@Transactional(readOnly=true)`——同页多条查询收进单事务/连接；
- **测试（test）**：`CommunityApiTest` 增 `comments_page_constant_roundtrips_after_batch`：20 位不同评论者 × 1 评论 → 一页 20 条，Hibernate Statistics（`hibernate.generate_statistics=true`，注意键必须是 `spring.jpa.properties.hibernate.*`，写 `spring.jpa.hibernate.*` 不生效——踩坑）计 JDBC 语句 **改前 43 / 改后 ≤8（实际 4：帖 1+评论页 1+users 1+profiles 1）**；断言 ≤8 防 N+1 回潮；
- **登记**：docs/37 §9 测试清单补两条（SQL 往返恒定 + readOnly 事务；EXPLAIN 断言落地于 J-07 集成）；工作日志。
- **门禁**：子集 11 例绿；全量在批次收尾统一跑。EXPLAIN/索引反扫验证 = J-07 Testcontainers 项内完成。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ④：J-08 错误体统一（全局 @RestControllerAdvice → Envelope）· 15 op

- **背景**：review-java.json（java-08，确认）——全仓唯一 @RestControllerAdvice 限定 basePackages=community（:13），Auth/Admin/Ticket/Content/Internal 域直接 throw ResponseStatusException → Spring 默认错误体 {timestamp,status,error,path}，与社区 Envelope{code,message,data} 双形态并存；前端 java-api.d.ts 全部建模为 Envelope*，非社区错误体统一解包时 data=null、message 读不到。另：docs/api/error-codes.md 登记 40904 但代码从未抛出（登记未接线）；
- **修复（code）**：新增 `common/GlobalExceptionHandler`（全局 @RestControllerAdvice）：ResponseStatusException 按 HTTP 映射（400→40001/401→40101/403→40301/404→40401/405→40501/409→**40904**（接线已登记码）/422→42201，其余 50002）；DataIntegrityViolationException→409/40904；NoResourceFoundException→404/40401；HttpRequestMethodNotSupportedException→405/40501；HttpMessageNotReadableException→400/40001；HandlerMethodValidationException→400/40001；兜底 Exception→500/50002（不再吐默认错误体，非社区校验异常经兜底转 42201）。**CommunityExceptionHandler 加 @Order(HIGHEST_PRECEDENCE)**——踩坑：全局兜底 `@ExceptionHandler(Exception.class)` 会先于社区 Advice 命中 CommunityException（Advice 咨询顺序按 Order/注册序），必须显式排位才能保住社区 42203/4xxxx 语义；
- **测试（test）**：新 `common/ErrorEnvelopeTest` 6 例：登录 401→40101 / 重复用户名注册 409→40904 / 无效 refresh 401→40101；admin 404→40401；请求体校验 400→42201（非社区）且社区仍 42203（双码并存锁）；坏 JSON→400/40001；DELETE /coins→405/40501（既有 coin 用例的 405 断言不回归）；未知路径→404/40401。**改前失败证据**：stash 后实跑 → **6/6 红**（「非 Envelope 错误体」——正是双形态缺陷）；改后 6 例绿；
- **错误码登记**：40501（方法不允许）、50002（服务内部错误兜底）先登记后用；40904 行修订为「资源/唯一键冲突」通用语义（唯一键兜底 + 注册撞名等）；
- **登记**：docs/api/envelope.md（错误体统一 + 映射表 + 过滤器层边界）、docs/api/error-codes.md、工作日志。契约快照零 diff（Advice 不改变 springdoc 渲染的接口签名）。
- **门禁**：子集 6 例绿；全量在批次收尾统一跑。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ③：J-04 软删评论通知复活（findMine 补 c.status='visible'）· 6 op

- **背景**：review-java.json（java-04，确认）——`PostCommentRepository.findMine`（:41-45）WHERE 只过滤父帖 status，**未过滤评论自身 c.status**；schema 定义 post_comments.status 三态（visible/hidden/deleted，0007_community_s1.py:186）→ 软删/隐藏评论仍进入通知聚合并推给作者，点击无法定位，软删约束被绕过。对照 comments() 展示路径 page() 已过滤 `c.status='visible'`（口径不一致）；
- **修复（code）**：findMine JPQL 补 `c.status = 'visible'`（展示/通知两路状态口径对齐）；互动无 status 字段（物理删行），PostInteractionRepository.findMine 无需改（核查过）；
- **测试（test）**：`CommunitySocialTest` 增 `notifications_exclude_softdeleted_comments`：发评论 → 通知含 1 条 → 评论置 deleted → 通知 0 条；再发第二条置 hidden → 同样 0 条。**改前失败证据**：stash 修复后实跑 → 断言红（软删评论仍在通知，:303）；改后 CommunitySocialTest 6 例全绿；
- **登记**：docs/41 §1（互动通知数据源补「评论仅可见态」+ J-04 注）+ §3（测试清单 5→6 例）+ 工作日志。
- **门禁**：子集 6 例绿；全量在批次收尾统一跑。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ②：J-02 禁用即时生效（JwtAuthFilter 查 users.status → 401）· 9 op

- **背景**：review-java.json（java-02，确认）——JwtAuthFilter 只验签不查 users.status（application.yml access-ttl=3600），管理端禁用（AdminUserController.updateStatus 只落 users.status）后，已签发 token **最长 1 小时仍可访问全部受保护端点**；Java 侧与 Python 侧同缺口（docs/19 P1-10 登记）。无告警/无黑名单/无二次鉴权；
- **修复（code）**：`JwtAuthFilter` 注入 UserRepository + ObjectMapper：验签解析出 userId 后 `findById`（PK 命中）查 status，`users.status != 'active'` 或用户不存在 → clearContext + **显式 401 Envelope{40101}**（过滤器层无法走 @RestControllerAdvice，直接写 JSON 响应）+ 终止链路；`SecurityConfig` 构造注入仓库并传给过滤器。**取舍**：每请求一次 PK 查库（薄管理端 QPS 低可承受）换取**即时生效**——无 TTL 缓存窗口、无「禁用后仍可用 N 秒」；短 TTL 缓存 + 变更失效登记为后续项（docs/18 修订注），匿名访问仍 403（既有 unauth_403 用例锁定，未改）；
- **测试（test）**：新 `DisabledUserAccessTest`（无类级事务，禁用必须提交后由过滤器独立事务读到）1 例：注册→禁用→同 token 立即 401（/auth/me 与社区 feed 均 40101）→重新启用→同 token 恢复 200。**改前失败证据**：stash 修复后实跑 → `expected: <401> but was: <200>`（正是「disabled 用户 1h 窗口仍可用」）；改后 1 例通过；
- **登记**：docs/18 §J1 已知边界修订（① 的「仍有效」仅指主动登出；禁用已即时生效 + Python 侧跨端遗留）；工作日志。
- **门禁**：J-02 子集 1 例绿；全量在批次收尾统一跑。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-08 Java P1 批 ①：J-01 点赞并发幂等（like 500 / unlike 计数漂移）· 10 op

- **背景**：local/review-java.json（java-01，确认）——like()「先查后插」无唯一键兜底（对比 :577-592 的 insertInteractionIdempotent 写法），PG READ COMMITTED 下并发双击 → 第二个 INSERT 撞 `uq_post_likes_post_liker` → 未捕获 DataIntegrityViolationException → **500**；unlike() 无条件删除+递减 → 并发双击取消双减 → like_count 与事实行漂移（GREATEST 只兜底到 0）。既有单测仅类级 @Transactional 单线程幂等，H2 不暴露并发缺陷；
- **修复（code）**：① `PostLikeRepository` 新增 **DB 层原子语句**——`insertIgnoreConflict`（`INSERT ... ON CONFLICT DO NOTHING`，返回 1/0）与 `deleteOneByPostIdAndLikerId`（原生 DELETE 返回实际删行数 0/1）；② `PostInteractionRepository.insertIgnoreConflict` 同构（替代「先查后插 + catch」：catch 即便捕获冲突，Hibernate 已把事务标 rollback-only，提交期仍抛 UnexpectedRollbackException，真并发下 500 依旧——此隐藏坑一并消除）；③ `CommunityService.like()`：like 以「本次是否真实插入」为唯一递增依据；unlike 先判删除行数、仅 >0 才递减计数与删 interaction；`insertInteractionIdempotent` 收敛为一行 ON CONFLICT。**H2 MODE=PostgreSQL 实测支持无目标 `ON CONFLICT DO NOTHING`；带冲突目标的写法不支持（语法错，踩坑），故统一无目标写法**；
- **测试（test）**：新 `LikeConcurrencyTest`（不挂类级事务 + 多线程栅栏对齐放行，最大化 check-then-act 窗口命中）2 例：并发 like×6 幂等返回且 like_count==1、事实行唯一；并发 unlike×6（预置 2 赞）仅减一次、计数与事实行一致。**改前失败证据**：stash 修复后实跑 → 2 例全红，`DataIntegrityViolationException: Unique index or primary key violation: UQ_POST_LIKES_POST_LIKER`（正是真机 500 的服务端根因）+ unlike 漂移断言失败；改后 17 tests 全绿（社区相关 10+5+2）；
- **登记**：docs/37 §3.2 补第 4 条（J-01 并发幂等口径）+ §9 测试清单补 LikeConcurrencyTest。
- **门禁**：`mvn -B -ntp verify -DskipITs` 全量 36→38 tests 绿 + spotless 绿（本轮记录时点：J-01 后跑过社区子集 17 绿；全量在批次收尾统一跑）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-08）

## 2026-09-07 音频回放 403 根因修复：TTS 输出独立 tts/ 前缀（免归属校验）· 21 op

- **现象链**（用户网络面板逐步实锤）：401（原生 `<audio>` 不带 Bearer → `loadAudioBlob` 修复）→ **403 Forbidden**（归属校验 `Attempt/ScenarioMessage.audio_url` 引用；流式多句音频只有 `emitted_urls[0]` 落库，其余 chunk 无引用 → 40301）；
- **修复**：① `save_tts_audio_bytes`（orchestrator）——AI TTS 输出改存 `data/audio/tts/{sha}.mp3`、URL 前缀 `/api/v1/audio/tts/`；② 新增独立路由 `GET /api/v1/audio/tts/{name}`（登录+未过期即放行，**免归属**——TTS 为会话内生成物非隐私录音；用户录音 `/audio/{name}` 归属校验保持）；③ **踩坑（404）**：`/audio/tts/{name}` 是双段路径，`/audio/{name}` 单段参数不匹配 → 路由独立（第一次改法合并进 get_audio 校验后 404：FastAPI path 参数不含 `/`）；
- **前端**：`loadAudioBlob`（上一条）带 Bearer 拉 blob 播放——401/403 双根因闭环（docs/21 R-5 目标态「签名 URL 或 Blob」，本轮落地 Blob 方案）；
- **验证**：`tests/test_audio_chunk_duration.py` 增 2 例（tts/ 前缀放行 200 / 普通名无归属 403 保持）+ 全量 `pytest -q` **299 passed** + ruff 全绿；docs/14 §6.2 登记新端点；
- **登记**：本文档 + 安卓日志（根因更正：401→403 链，竞态为次因）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 真链路体验修复：假「已使用」批注 / 幻觉转写 / 后续音频不自动播 · 33 op

- **用户实测三连**：① 没说过的短语被标「已使用」；② 转写 "Uh, I heard, uh, Juicy, uh, or…"（whisper 幻觉）；③ 口语页只有开场白自动播、后续回合音频不自动播 + 需求改为「听完语音再显示重播按钮」；
- **① 假批注（根因：LLM 兜底无条件追加）**：`MetaExecutor.apply_hits` = 规则通道（词序包含，权威） + **LLM `meta.corpus_hits` 无校验追加**——真实 DeepSeek 上线后宽松判定（读着转写+台词就标命中）→ 用户没说的话也「已使用」。修复：**默认关闭 LLM 兜底**（`config.meta_llm_hits_enabled=False`，`apply_hits(llm_hits_enabled=…)`），命中 = 纯规则（宁漏勿误）；语义级命中需显式开启。测试同步收紧（test_meta_executor 默认 1 条/开启 2 条、compensate 用例断言兜底不混入）；
- **② 幻觉抑制**：`transcribe` 增 `condition_on_previous_text=False`（默认 True 会顺着上文幻觉延续）+ VAD 已接线；测试断言两参数；
- **③ 播放器重构（MobileSpeakingView）**：旧「每 chunk 一个 Audio + loadedmetadata 定时器」存在竞态（同内容 mp3 缓存复用同 URL → metadata 提前就绪 → 定时器先于 onended 抢跑 shift → 后续句子不自动播/叠音）；重写为**单元素 speaker + 串行 pump 队列**（ended 驱动严格有序；元素在点「开始」手势链中解锁后，后续回合 play() 复用同一元素，顺带规避移动端 autoplay 对新元素的收紧）——playTts/replay/playChunk 全部收敛到 speaker；**解锁语义按用户需求改为「本回合有 audio_chunk → 播完才显示重播按钮（+8s 兜底）；无音频块 → turn_end 立即解锁」**（MVP 测试锁定无音频语义不变）；
- **验证**：后端全量 `pytest -q` **297 passed** + ruff 全绿；前端 lint/typecheck/**vitest 全绿（MobileSpeakingView 3 例：回合结束解锁/重听命中文本/空文本不解锁）**/build 全绿；uvicorn --reload 已热加载（无需重启）；
- **评分真实性说明（用户怀疑）**：① 评分 = **真实讯飞 ISE**（如今 60.81082/70.37372 这类随机小数；Fake 桩固定 88/90/86/85 已在上批隔离——dev 用 Fake 时带 `is_fake` 标识+告警、生产 fail-fast 不可用）；② **流利度**由 whisper 词级时间戳派生——幻觉词（"Uh, I heard, uh"）会拉低 wpm/停顿分 → 本次幻觉抑制后应回升；③ 自证：录一句标准 "I'd like a coffee, please." → 发音/流利度应显著高于当前值。
- **登记**：docs/14 §3.5（双通道收紧说明）；安卓日志（播放器重构+重听解锁时机 UI 变更）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 真链路收口：whisper 本地直载 + 大模型评估 + FakeLLM 判定 · 61 op

- **背景**：用户拍板真链路（ASR 真实转写）；被墙环境下 HF 缓存「完整性校验」反复拦截（缺 `.gitattributes`/`README.md` 即拒绝、联网又是 ConnectTimeout）；
- **修复（dev-up.ps1）**：① HF_HOME 改为**默认缓存存在时不注入**（此前无条件注入 `data\models`（不存在）→ 绕开已下载模型，2026-09-07 同日第二次此因误判）；② 新增**本地模型直载**：扫描默认缓存 faster-whisper-small 快照（含 model.bin）→ `APP_ASR_MODEL=<快照目录>`，faster-whisper 本地路径加载，**完全绕过 HF 缓存校验/网络**；
- **VoiceStudio 大模型评估（用户提供 F:\...\OmniVoiceStudio-Data\data\models）**：`Systran/faster-whisper-large-v3`（2.9GB）**可直载可用**（已实测：config/tokenizer.json/vocabulary.json 齐全，转写文本正确），但 **CPU int8 RTF≈5.58**（5.78s 音频 → 32s）——不满足对话「3~5s 反馈」，**不默认启用**；登记为「精听/离线素材标注」可复用资产（显式 `APP_ASR_MODEL=<snapshots/<rev>>` 即切）。`deepdml/faster-whisper-large-v3-turbo-ct2`（1.5GB）**缺 tokenizer 不可用**；sherpa-onnx-whisper-tiny 为 onnx 格式（faster-whisper 不支持）；其余为 OmniVoice/VoxCPM/GPT-SoVITS/CosyVoice 等 TTS 模型（本仓不涉及）；
- **「两个场景回复一样」判定**：根 `.env` `APP_DEEPSEEK_API_KEY = [len 0]`（空）→ `get_llm_client` 走 **FakeLLMClient**（stubs.py 流式固定输出「Of course! Would you like it hot or iced? That will be four dollars, please.」——两张截图完全一致即为该桩句）。**不是故障，是 Key 未配置**：将 DeepSeek API Key 填入根 `.env` 的 `APP_DEEPSEEK_API_KEY` 后**重启 python 服务**（get_settings 为进程级缓存，--reload 不监控 .env）即可回复真实多样；
- **验证**：small 直载后服务恢复（用户截图：真实 ASR 转写「I want you some coffee」+ 真实 ISE 评分 60.24/73.73 + TTS 播报）；端到端冒烟（edge-tts→ffmpeg imageio 二进制→真实 whisper small+VAD：转写 100% 正确、duration=5.78s、no_speech=False）；全量 `pytest -q` 297 passed + ruff 全绿；
- **登记**：本条目；README「文档索引」无新文件不需登记。真链路链路现状：ASR 真（small·本地直载）/ ISE 真（app_id+key+secret 在 .env）/ TTS 真（edge-tts）/ LLM **仍假**（待 DeepSeek Key）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 回归修复：口语/自由说 ASR 全挂（uvicorn --reload 事件循环 + ffmpeg 依赖剪枝）

- **现象**：口语页「管线提示: asr_failed」、自由说「自由对话提示: internal」（两页首步都是 ASR）；`local/dev-logs/python-8000.err.log` 铁证 —— `raise NotImplementedError`（asyncio/subprocess.py → base_events.py:528 `_make_subprocess_transport`）；
- **根因（双问题叠加，均非业务代码）**：
  1. **uvicorn `--reload` 在 Windows 用 SelectorEventLoop**（`uvicorn/loops/asyncio.py`：`win32 and not use_subprocess → Proactor`，`--reload` 时 use_subprocess=True → Selector）——**Selector 不支持 `asyncio` 子进程**，`create_subprocess_exec` 直接 NotImplementedError；方式 A（docker 无 --reload → Proactor）不受影响，故此前「正常」；
  2. **`uv sync` 剪枝**：`imageio-ffmpeg`（本机 ffmpeg 二进制兜底，asr.py/README 登记）此前以传递依赖存在于 venv，我同步依赖后**被移除** → ffmpeg 缺失（即便修好循环也照样失败）；
- **修复**：① `ffmpeg_utils.run_ffmpeg/probe_duration_seconds` 全部改 **`asyncio.to_thread(subprocess.run(..., timeout=...))`**（任何 loop 类型可用；仍满足 P0-2 线程化 + 超时 kill；asr/ise 无需改动）；② `pyproject` **显式声明 `imageio-ffmpeg>=0.5`**（防再次剪枝）；③ 回归锁 `test_run_ffmpeg_works_under_selector_loop`（Selector 下真实执行）+ 非零/缺失错误断言；
- **验证**：`ffmpeg_bin()` 解析到 imageio 内嵌二进制；全量 `pytest -q` **297 passed** + ruff 全绿（121 文件）；`uvicorn --reload` 已热重载；
- **遗留（本机真链路前提）**：`data/models` 无 whisper 模型缓存且 `HF_HUB_OFFLINE=1`（dev-up 注入）→ 真实 ASR 需要先下载模型（`HF_HUB_OFFLINE=0` + `WhisperModel('small')` 预下载一次）或演示档 `APP_TESTING=true`（README 演示口径：无密钥全 Fake），二者选一后页面即可用；
- **踩坑**：SelectorEventLoop 下 `asyncio` 子进程不可用属平台级行为，代码层面不能靠运行时改 loop 策略（uvicorn 先建 loop 后 import app）；ffmpeg 二进制依赖必须显式声明（传递依赖不可靠）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 部署踩坑：JWT_SECRET 未注入导致 Java :8080 启动失败（dev-up.ps1 补 .env 注入）

- **现象**：`.\scripts\dev-up.ps1 start` → python/vite 健康 True，java False；`local/dev-logs/java-8080.out.log` 尾：`Caused by: java.lang.IllegalStateException: vocalverse.jwt.secret 未配置或过短（≥32 字节）：检查 JWT_SECRET 环境变量（docs/19 P0-9）`（JwtService.java:29 fail-fast）；
- **根因**：方式 B 本地链路——Java `application.yml:25` 用 `${JWT_SECRET:}`（环境变量，缺省空），而 `dev-up.ps1` 只注入 HF_* 三个变量，**从不加载根 `.env`**；Maven 子进程不读 .env → `JWT_SECRET` 为空 → P0-9 早抛。此前能跑是因为 shell 会话里手工 export 过；干净会话（PowerShell 重开）必现。Python 侧不受影响（pydantic-settings 自读 `.env`）；
- **修复**：`scripts/dev-up.ps1` 启动前按 setdefault 语义（仅未显式设置时）注入根 `.env` 全部键（附件：BOM 防护 TrimStart(0xFEFF)——记事本保存的 .env 首行带 BOM 会把 BOM 并进键名）；`Parser::ParseFile` 校验语法过；
- **验证**：解析器语法校验 OK；键匹配逻辑 dry-run 验证；重跑 `dev-up stop → start` 后 java 应 healthy（JWT_SECRET 42 字节 ≥32 达标）；
- **登记**：本条目（AI 代工，部署/脚本类归主线日志）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 跨端收尾：R-13 权威轮次 + SSE 协议 golden 双端护栏 · 31 op

- **R-13（va-arch-09，P1·S）**：`events.py TurnEnd` 增 `expected_turn`（服务端权威：本回合完成后 `state.current_turn`，即下一轮应提交的 `expected_turn`）；orchestrator **6 处 TurnEnd 发射点**全部回带（对话/轻回合/demo-hint/辩护/影子）；前端三处采纳——`MobileSpeakingView`/`PracticeView` 的 `currentTurn` 与 `DefenseView` 的 `questionIndex` 改为 **`e.expected_turn ?? 乐观值`**（乐观推进保留、服务端纠偏兜底）——断线/刷新后不再靠前端计数撞 40903「重来」；
- **va-arch-04 SSE 协议 golden（P1·M）**：新增**单语料双端断言**——`tests/fixtures/sse_event_cases.json`（v1 快照 12 例：全部 9 种事件 + audio_chunk 含/不含 duration + turn_end 含/不含 expected_turn + meta_block 最小/全量；由后端 pydantic 模型生成）→ 后端 `test_sse_protocol_golden.py` 3 例（序列化字节一致/重建回环/exclude_none 语义固化）+ 前端 `sse-protocol-golden.test.ts` 2 例（parseSseBuffer 解析==语料/缺省字段不存在）；**任一边契约漂移 → 单边 CI 红**（VS「共享 golden corpus 双端断言」工程思路落地，AGPL 仅借鉴）；
- **验证**：后端全量 `pytest -q` **294 passed/1 skipped** + ruff 全绿；前端 `lint/typecheck/test:run`（**95 passed**，+2 golden）/build 全绿；
- **踩坑**：① 前端 golden 读文件不能用 `new URL(relative, import.meta.url)`（vitest 下 import.meta.url 非 file scheme）→ `path.resolve(process.cwd(), …)`（cwd=apps/web，两级上级=仓库根）；② `asyncio.wait_for` 直接包 score_task 会**取消**任务致落库侧 CancelledError——shield+门控（见上批）；③ TurnEnd 6 处发射点多行/单行形态不一，逐个核对；
- **登记**：docs/14 §3.3（turn_end 行 + golden 护栏说明）；App 端轮次显示纠偏见安卓日志。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 语音链路剩余队列 P1 批（va-01/03/08 · vasr-01/05/07/09/10 · py-05/10）· 156 op

- **背景**：性能拷问×审查剩余「语音链路 Python 侧 P0/P1」全量落地（组长裁决续做）；含 1 项审查官升格 P0（va-03 ISE 收帧超时）；
- **va-03（P0·最痛）ISE 分级超时**：`_recv_result` 每帧接收 5s 墙钟（wait_for）；`score()` ws 会话总预算 12s（`asyncio.timeout`）；编排器 `await score_task` 改 **`wait_for(shield, 3s)`**（docs/14 §3.2「迟到≤3s 显示未评测」落为代码）：超时**不取消** score_task（shield），第 6 步不再等它 → **ISE 挂起不再拖停整轮 SSE**；落库侧以 `score_late` 门控不再重复无界 await；
- **vasr-07 Silero VAD（最强实锤兑现）**：`transcribe` 加 `vad_filter=True`（faster-whisper 内置，零新依赖）——docs/06 §8:116 承诺从「没做」变「一行兑现」，静音/噪段前置裁剪，稳词界 + 降带 BGM CER；
- **vasr-09 模型加载**：`_get_model` 双重检查锁（threading.Lock，并发首请求只加载一次）；`main._prewarm_asr` 改 `await asyncio.to_thread(client.warm)`（**显式 warm() 替代 getattr 探针**；加载移出事件循环，就绪探测不再被 10~30s 阻塞）；
- **vasr-01 转写墙钟**：`asyncio.wait_for(to_thread(transcribe), 300s)` —— whisper 挂起时信号量槽位可释放，消除「挂 2 次=全站 ASR 永久死亡」；
- **vasr-05 时长校验 + asr_seconds 修正**：`/turns` 前置 ffprobe（缺则 ffmpeg -i stderr 解析，`ffmpeg_utils.probe_duration_seconds`）→ 超 `max_dialog_seconds` 返回 **42204**（先校验后落盘/扣额度；探不出不阻断，字节界兜底）；`asr_seconds` 改用 `res.duration`（旧实现把 webm 字节当 16k 算）；错误码 42204 已登记 docs/api/error-codes.md（**42203 已被社区占用，踩坑：先查表再用**）；
- **vasr-10 判别位**：`ASRResult.no_speech`（no_speech_prob>0.7 或空转写）；影子跟读提示分流（「太安静了，试着大声一点」vs「没听清」），提高提示准确度、避免无意义的反复重试；
- **va-01 ffmpeg 工具层**：新 `app/audio/ffmpeg_utils.py`（`ffmpeg_bin/ffprobe_bin/run_ffmpeg/parse_duration_from_stderr/probe_duration_seconds`）——asr/ise 两份内联转码收拢为单一护栏（asr.py 除 `_run_ffmpeg_async` 薄壳；ise `_to_pcm16` 直接 run_ffmpeg；test_ise 导入与二进制探测同步迁移）；
- **va-08 评分客户端分级**：`get_scorer_client` 缺 Key 时按 `app_env` 分级—— **production → `UnavailableScorerClient` fail-fast**（score() 抛可读错误→明确「未评测」，杜绝假分 88/90/86/85 静默流入 skill/推荐链）；development → Fake+**`is_fake=True` 显式标识** + 告警日志；
- **py-05 LLM 连接池**：`DeepSeekLLMClient` 构造期常驻 `httpx.AsyncClient(limits=…)`；`base.get_llm_client` 按 (key, base_url, model) **缓存实例**（此前每调用新建 = 每次 TLS 握手）；
- **py-10 META 补偿封顶**：`SessionState.meta_failures`（新字段）——会话内连续失败 ≥2 次后跳过补偿，规则兜底（控 LLM 配额）；
- **验证**：新 `tests/test_audio_hardening.py` 10 例（时长解析纯函数/VAD+no_speech 判别/4 线程单次加载/ISE 收帧超时与正常帧/LLM 实例缓存/评分 fail-fast 与 Fake 标识）+ `test_asr_words` 适配 vad_filter 参数；全量 `pytest -q` **291 passed/1 skipped** + ruff 全绿（120 文件格式化）；
- **踩坑**：① Async 函数/`asyncio.timeout` 嵌套信号量内 ws 会话——预算边界放 connect 内；② 42203 撞车（先查表）；③ `vad_filter` 参数让既有 `_FakeModel.transcribe` 签名炸（TypeError unexpected kwarg）——fakes 需同步补参；④ 评分超时若直接 wait_for 会**取消** score_task → 第 7 步落库重 await 崩（CancelledError）——必须 shield + score_late 门控；
- **登记**：docs/api/error-codes.md（42204）；影子提示文案分流见安卓日志；R-13 权威轮次与 SSE golden 属下一批（跨端）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 性能拷问 P0 两连 + P1-B：推荐缓存 500 修复 / SSE 收尾同步解堵 / TTS 缓存确定性 · 67 op

- **背景**：上轮「性能拷问×审查」3 个 P0 + 1 个 P1 一并落地（组长裁决），全部按 code/test/docs 三 commit；
- **P0 · py-01 推荐缓存生产态 500（最痛）**：`rec/service.py` 旧 `_cache_get` 对 `redis.asyncio` 的 `r.get()` 未 await → `json.loads(<coroutine>)` 在 try **外**抛 TypeError（比"静默失效"更糟）；`_cache_set`/`invalidate` 同样从不 await（缓存零实现）。修复：三函数改 async+真 await+`json.loads` 入 try；`_recommend` 拆为**同步纯 ORM 核心** `_recommend_impl` + `asyncio.to_thread` 包装 `_recommend_cached`（db 注入路径保持同步，测试/内部调用零破坏）；`recommend_scenes/recommend_shadow` 改 async（路由 await）；**回归锁**：新 `tests/rec/test_recommend_redis_cache.py` 3 例（fakeredis 模拟生产 redis.asyncio：命中不重算+返回值确为 JSON 反序列化结果（若仍是协程必 TypeError，即日志缺陷回归锁）/invalidate 后重算）/redis 不可用降级重算不 500）——**新增 dev 依赖 fakeredis>=2.26**；
- **P0 · py-02 SSE 收尾同步解堵**：`orchestrator.py` 4 处 `complete_session(...)`（对话收尾/abandon/辩护/影子，:287/:529/:641/:869）改为 `await asyncio.to_thread(...)`（对齐路由层 practice.py:205 P0-2 纪律；`complete_session` 自建自关 Session，线程安全；同步 httpx 3s 也被移出事件循环）；
- **P1-B · TTS 缓存确定性（vtts-06）**：键扩为 `sha1(provider|engine_version|voice|rate|text)`（edge-tts 包版本经 importlib.metadata 入键，升级引擎/换音色/切 provider 不命中陈旧音频）；新增 `cache_is_fresh`（mtime TTL，config `tts_cache_ttl_s=86400`）、`prune_tts_cache`（容量 `tts_cache_max_mb=512` 按 mtime 裁剪最旧，min_keep=16 防高频句互踢）、统一出入口 `tts_synthesize_cached`；`orchestrator._tts_url_from_bytes` 与 `/tts` 路由共用（/tts 不再每次现合成；桶 consume 仍按端点限流计数）。**不搬 VS 内容寻址确定性**（edge-tts 在线非确定，前提不成立，va-arch-07）；
- **验证**：`tests/test_tts_cache.py` 9 例 + 全量 `pytest -q` 绿（新增 12 例）；`ruff check`+`format` 全绿；既有 `test_recommend.py`/`test_seed_recommend.py` 因 API 转 async 同步改 await（db 注入路径行为不变）；
- **踩坑**：① async 函数即使 db 分支也返回协程——同步测试全炸，逐处 `async def + await`；② `prune_tts_cache` 默认 min_keep=16 在 3 文件小目录下永不裁剪（测试暴露），测试传 min_keep=1 校验语义；③ fps 位率索引（沿用 P1-C 踩坑，本批无新 MPEG 帧）；
- **登记**：docs/44 P1-B ✅；本轮 fe-01（App 播放资源泄漏）记录见 `worklog/安卓开发日志.md`。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 TTS 链路整改 P1-C：缺句显式上报 + AudioChunk.duration（帧头估算）· 48 op

- **背景**：对抗拷问 vtts-04——句合成失败仅内部降级 None（素材静默丢句），前端无时长信息做 Gap-less 排播；docs/44 P1-C 定稿（借鉴 VS `report_dropped_chunks` 思路）；
- **后端**：
  - `app/audio/tts.py` 新增纯函数 `mp3_duration_seconds(data)->float|None`：MPEG 帧头位率换算 CBR 时长（跳 ID3v2、绝不抛错、非 MP3/坏数据 → None）；零依赖零 IO；
  - `app/practice/events.py` `AudioChunk` 增可选 `duration`（`exclude_none` 序列化 → 旧端兼容）；
  - `app/practice/orchestrator.py` `_tts_url_from_bytes` 改返 `(url, duration)` 元组；失败分支结构化日志 **`sentence no audio: %r (reason: %s)`**（缺句显式上报）；drain 两处 + 影子示范（:750）均透传 duration；
- **前端**（`sse-types.ts` + `MobileSpeakingView.playChunk` + `PracticeView.playChunk`）：`audio_chunk` 透传 duration；队列推进加「ended 不触发兜底」（loadedmetadata 定时单次推进，优先服务端 duration，15s 硬上限）——与 playTts 既有「时长兜底」口径一致；
- **测试**：`tests/test_audio_chunk_duration.py` 8 例（纯函数估算/ID3 跳过/坏数据 None/契约序列化/失败 (None,None)+日志/成功 url+duration）；前端 sse.test.ts 增 duration 透传 + 旧端兼容用例；
- **门禁**：Python `pytest -q` **268 passed / 4 skipped**（260+8）、`ruff check`+`format --check` 全绿（127 文件）；前端 `lint/typecheck/test:run`（**90 passed**）+ `build` 全绿；
- **踩坑**：① 自造 MP3 帧 byte1 位率索引对不上 MPEG2 L3 表（48kbps 是 idx 6 非 5）→ 时长差 20%；frame sync 需 11 位（byte1 高 3 位=111），初版 0x27 被解析器正确拒绝——修正为 0xF3/0x64；② `_tts_url_from_bytes` 改元组返回后，`pending_tts` 与影子示范调用点需同步解包（编译期类型已拦）；
- **登记**：docs/14 §3.3（audio_chunk 行 + duration?）、docs/44 P1-C 标 ✅（含验收/风险）、README 无新文件不需索引行；
- **待跟进**：server 事件埋点未做（`EventTypes` 白名单无失败类 → 登记看板化再扩）；crossfade 维持「本轮不做」（§6 待评估）。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 TTS 链路整改 P0-B：引擎生命周期契约（is_available/ensure_ready/unload）+ 单发重试/超时 + provider 分派

- **背景**：对抗拷问 vtts-01——`TTSClient` ABC 只有 `synthesize`（base.py:58-65），`get_tts_client` 恒返 EdgeTTSClient（base.py:116-124），无 is_available/ensure_ready/unload；edge-tts 断网/受限/改协议时整链静默（orchestrator.py 降级为 None），无超时/熔断/重试（docs/audit:128）。
- **改动**：
  - `app/audio/base.py` `TTSClient` 增 3 个**默认实现**的方法：`is_available()->(bool,str)`（默认 True）、`ensure_ready()`/`unload()`（默认 no-op）——向后兼容，子类/`FakeTTSClient` 无需改即兼容。
  - `app/audio/tts.py` `EdgeTTSClient`：`is_available`(edge_tts 可导入)、`ensure_ready`/`unload`(no-op)；`synthesize` 加**超时**（默认 30s + 可注入）+ **单发重试**（初试+重试=2，参考 VS「明确失败而非循环」），失败明确上抛 `RuntimeError`（不再静默）。
  - `app/audio/tts.py` 新增 `AzureNotWiredClient` 占位：`is_available()==(False,"Azure TTS 未接线（见 docs/44 P0-C）")`、`synthesize` 抛未接线错误——让 config 里 `tts_provider='azure'` 的「存在即切」承诺消失（docs/audit:135 K02）。
  - `app/audio/base.py` `get_tts_client` 按 `settings.tts_provider` 分派：`edge`→EdgeTTSClient、`azure`→AzureNotWiredClient（未接线显式报错，不静默用 edge）。
  - `app/api/routes/audio.py` `/tts`：合成前 `client.is_available()` 预检，不可用返回 503 可读错误而非 500。
- **验证**：`pytest tests/test_tts_client.py` 8 passed（is_available/重试后上抛/超时不挂起/Azure 未接线/工厂分派）；全量 `pytest -q` **260 passed, 4 skipped**；`ruff check` + `ruff format --check` 全绿。
- **踩坑**：`/tts` 预检局部变量命名用 `ok` 会遮蔽 response 辅助函数 `from app.core.response import ok`，导致 `TypeError: 'bool' object is not callable`——已改为 `available`（命名避开 response helper）。
- **待办（下步）**：P0-C 接线 Azure（引 azure-cognitiveservices-speech）；P1-C 缺句上报/duration；P1-B 缓存键/过期。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 TTS 链路整改 P1-A：文本归一化（缩写展开 / 数字→单词 / 零宽与重复标点清理）

- **背景**：对抗拷问 vtts-05——LLM 原文直接喂 edge-tts（orchestrator.py:397-400），`50%`、`3.5`、`Dr.`、`U.S.`、网址、重复标点等被读错/读怪；且全仓无任何归一化（num2words/缩写展开/零宽清理均为零命中）。
- **架构解耦**：新增纯模块 `app/audio/textproc/normalize.py`（engine-agnostic，幂等、绝不抛错、括号标记安全），与 `sentence_splitter.py` 同归 `app/audio/textproc/`。
- **改动**：
  - 新增 `app/audio/textproc/normalize.py`：`normalize_for_tts`/`normalize_text`。规则：安全过滤（零宽/bidi/连续标点封顶3/空白规整）+ 缩写展开（Dr./Mr./St./vs./etc./e.g./i.e.，cap/digit 守卫）+ 数字→单词（百分比/小数/序数/货币/年份/整数，经 num2words 0.5.14）；保守不改（粘字母 MP3/v2.5、千分位 1,000、区间 3-5、版本号 3.5.1、前导零 007、7+位ID）；`[...]`/`[[...]]` 标记跳过。
  - 接线到两个 choke point：`app/practice/orchestrator.py` `_tts_url_from_bytes`（归一化在缓存键前）与 `app/api/routes/audio.py` `/tts`（合成前归一化）——此两处为文本→引擎唯一入口。
  - 依赖：`pyproject.toml`/`uv.lock` 增 `num2words>=0.5`（MIT）。
- **验证**：`pytest tests/test_text_normalize.py` 14 passed；全量 `pytest -q` **252 passed, 4 skipped**；受牵涉测试（audio_stub/m2_core/free_chat/stream_sentence）71 passed；`ruff check` + `ruff format --check` 全绿。
- **口径**：保守——假阴性（数字不改）可接受，假阳性（改坏意思）不可接受；缩写式（I'll/We're）不做归一（edge-tts 原生可读）；`"No."` 未入表（对话答复常见真句）故 `"No. 5"`→`"No. five"` 为该边缘可接受。
- **待办（下步）**：P0-B 引擎生命周期（`is_available/ensure_ready/unload` + provider 分派 + 超时/熔断）→ P1-C 缺句上报/duration。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 TTS 链路整改 P0-A：流式句切分「缩写/小数点/网址误拆」修复 + 架构解耦

- **背景**：对抗拷问 vtts-03 指出的句切分硬伤——旧 `_SENTENCE_END_RE=[.!?][\s…]*` 无任何守卫，`Mr./Dr./U.S./3.5/Ph.D./.com` 被当句号切错。已用旧正则实测复现：`"Mr. Smith went to the store."→['Mr.','Smith went to the store.']`、`"It's 3.5 miles away."→["It's 3.","5 miles away."]`、`"The U.S. economy grew."→['The U.','S.','economy grew.']`、`"Visit example.com today."→['Visit example.','com today.']`。
- **架构解耦**（用户要求模块分清楚）：把流式句切分从 1000+ 行 `app/practice/orchestrator.py` 抽成**独立纯模块** `app/audio/textproc/sentence_splitter.py`（engine-agnostic，不 import 引擎/网络/配置）；后续文本归一化/发音词典/ssml-lite 同归 `app/audio/textproc/`（见 docs/44）。
- **改动**：
  - 新增 `app/audio/textproc/__init__.py`、`app/audio/textproc/sentence_splitter.py`：`StreamSentenceSplitter`/`find_sentence_end`/`MAX_SENTENCE_CHARS`；含缩写表 `_ABBREVIATION_GUARDS`（cap/digit 守卫）+ 中缀（3.5/U.S/e.g/Ph.D/v2.5）+ 点分缩写+单字母缩写 + 网址后缀 + 括号标签守卫 + 长句「分句边界→词边界→避开括号 tag 硬切」。
  - `app/practice/orchestrator.py`：删除内联 class + `_SENTENCE_END_RE` + `_MAX_SENTENCE_CHARS` + `import re`，改 `from app.audio.textproc.sentence_splitter import StreamSentenceSplitter`（构造器新增可选 `max_sentence_chars`，默认 300，对外行为兼容；`_MAX_SENTENCE_CHARS` 改名 `MAX_SENTENCE_CHARS` 已同步引用）。
  - `tests/test_stream_sentence.py`：导入改指新模块，新增 8 例回归（P0-A，修复前必失败）。
- **验证**：`pytest tests/test_stream_sentence.py` 17 passed；全量 `pytest -q` **238 passed, 4 skipped**；`ruff check` + `ruff format --check` 绿（仅 4 文件，均 "All checks passed"）。
- **口径说明**：按「宁少切、不误切」原则——`"on Elm St. He moved."` 的 `St.` 带 cap 守卫会被保守并入一句（假阴性可接受）；句间停顿控制/`AudioChunk.duration` 属 P1-C，下步处理。
- **待办（下步）**：P1-A 文本归一化（`normalize_for_tts`），归 `app/audio/textproc/normalize.py`；随后 P0-B 引擎生命周期 + P1-C 缺句上报/duration。

—— 执行人：组长 LHRCarrier（AI 代工，2026-09-07）

## 2026-09-07 组员 PR 评审处置与合入：PR#30 / PR#31 已完成（两 PR 均 MERGED）

- **PR#30 fix/p0-hardening → MERGED**（merge commit b360fbb）：处置 6 commits——① 阻断项：`sse.ts` read 拒绝改 `reject(err)` 传播（断网 onError+onClose、AbortError 静默）+ 2 例回归测试；② `heartbeat_stream` interval≤0 透传（兑现「0=关闭心跳」，修复前 0.063s 产 1363 行 ping）+ 1 例；③ `_persist_dialog_turn` 改线程内自建自关 Session（SQLAlchemy 非线程安全模式消除）；④ `post_turn` 分桶按 action 实际消耗（normal/retry 三桶、start/abandon 仅 LLM、hint/demo 无音频零扣）+ 4 断言测试；⑤ nginx `/manage/internal` 去尾斜杠拦截；⑥ 三份 workflow 补 `workflow_dispatch`（见下）；遗留登记 3 项（complete 短路晚于 LLM 摘要、demo/hint/abandon 分支同步 DB 写、联调页豁免）；
- **PR#31 feat/auth-session-security → MERGED**（merge commit 163e83b）：处置 4 commits——① `MobileSpeakingView` turn_end 空文本不解锁喇叭 + 1 例测试（与自由对话页 `if(reply)` 守卫一致）；② `logout` 吊销失败 `console.warn` 可观测 + 1 例测试；③ docs/18 J1 已知边界登记（access token 1h 残留 +「记住我」纯客户端语义）；④ 同款 workflow 补跑口；
- **CI 踩坑（已修，2026-09-07）**：本仓 `pull_request` 触发当前未生效——PR 分支推送后 0 run（与 python-ci 已有注释的 PR#24/#25 踩坑一致）；处置：frontend-ci/java-ci/secret-scan 补 `workflow_dispatch`（python-ci 早有），4 份 workflow `yaml.safe_load` 校验通过，手动补跑 8 个 workflow（两分支各 4）全绿——**后续 PR 分支需 `gh workflow run <name> --ref <branch>` 手动补跑，合入前须人工确认**；
- **合入流水**：#30 先合 → #31 `merge origin/main`（worklog 置顶区冲突按时间序人工解决：评审记录→#31 记录→#30 记录→旧内容）→ 手动补跑 CI → approve → merge；分支保护 = 1 个 approving review 且**新推送后旧批准自动失效**（dismiss_stale_reviews）——需在最终 head 上重新 approve；
- **验证**：本地 python 229 passed, 4 skipped（无 Docker 容器用例 skip）/ ruff+format 绿；前端 lint/typecheck/vitest 84/build 绿；Java 零改动（mvn verify CI 全绿）；8 个手动 CI 全绿（#30 含 Single-Writer 探针步骤，job 明细已核）。

—— 执行人：组长 LHRCarrier（AI 代审代改，2026-09-07）

## 2026-09-07 组员 PR 评审：PR#30（P0 加固收口）/ PR#31（会话安全增强 + 重听逐句化）

- **PR#30 fix/p0-hardening → request-changes（1 阻断 + 7 建议）**：
  - 已核查：CI 4 checks 全绿且 job steps 明细确认「Single-Writer 探针」步骤真实执行（非 0 jobs 静默失败）；错误码 40301/40401/42901 均已登记；worklog 署名/BUG 归档位置合规；契约三层对账一致；`X-Test-User-Id` 仅 testing 档生效（无生产冒充敞口）；
  - 🔴 阻断项：`apps/web/src/audio/sse.ts` L86-90 —— `reader.read()` 拒绝时外层 `new Promise` 永不结算（拒绝处理器 `throw err` 只产生 unhandledRejection，timer 已清 → await 永久挂起）：SSE 中途断网/组件卸载 abort 后 onError/onClose 不触发、90s idle 兜底失效 —— R-18 想防的「断流后永久 busy」反而在断流路径变为现实（修复前 `await reader.read()` 会传播到外层 .catch）。已用 Node 最小复现验证（settled=false + unhandledRejection），非纸面推断；修复建议 + 前置失败测试已写入 PR comment；
  - 建议 7 项：heartbeat_stream interval=0 忙循环（同算法复现 0.063s 产 1363 行 ping，与「0=关闭心跳」注释相悖）、`_persist_dialog_turn` 跨线程移交 SQLAlchemy Session（官方明确非线程安全）、complete 幂等短路晚于 LLM 摘要、post_turn 三桶无差别扣费（start 仅耗 LLM、hint/demo/abandon 实际零耗）与 free_chat「按实际消耗」口径不一致、nginx `/manage/internal` 无尾斜杠形式未拦、联调页豁免登记、demo/hint/abandon 分支同步 DB 写与「短事务化」范围确认；
  - 亮点：P0-1~9 + R 项覆盖完整，Redis Lua 释放、越权 40401 口径、Testcontainers 安全网、P0-7 探针自测 7 例均核验通过。
- **PR#31 feat/auth-session-security → comment（认可可合，5 建议）**：
  - 已核查：CI 3 checks 绿（java verify 含 ContractSnapshotTest；Python 零改动故 python-ci 未触发，符合预期）；「修复前失败」两条断言成立；契约/d.ts 同步；App 线记录入安卓日志、Java/契约入主线（混合条目拆分正确）；docs/18 J1 登记；
  - 建议：① MobileSpeakingView turn_end 解锁未守空文本（与 MobileFreeChatView 的 `if (reply)` 守卫不同；LLM 失败降级回合会出现空文本喇叭 → 重播空文本触发 /tts 422）——已挂行内 comment；② logout 吊销失败被静默吞掉建议 console.warn；③ access token 注销后 1h 内服务端仍有效登记为已知边界；④「记住我」纯客户端语义登记；⑤ 联调页豁免请组长确认登记；
  - 合入关系：与 #30 同基础 main@28cfa96，`git merge-tree` 验证代码可自动合并（仅 worklog 置顶区冲突）→ 建议 #30 先合再合 #31，worklog 人工合并。

—— 执行人：组长 LHRCarrier（AI 代审，2026-09-07）

## 2026-09-07 POST /auth/logout 登出撤销 + SecurityConfig 白名单收窄（配合前端「记住我」）

- 触发：用户反馈「关闭重开仍登录」→ 拍板补安全短板：退出登录必须是**有效登出**（原仅前端 `clear()`，30 天滑动窗口内 refresh 仍可续命）；
- 实现（Java）：
  1. `AuthController.logout`：`POST /auth/logout`（需合法 access token，无 Body）→ 吊销该用户**全部**未撤销 refresh token（`RefreshTokenRepository.findByUserIdAndRevokedAtIsNull` + 置 `revoked_at` 后 `saveAll`；`Envelope.<Void>ok(null)`）；
  2. `SecurityConfig`：`/auth/**` 全开放 → 公开白名单**仅** `login/register/refresh/forgot`；`/auth/logout`、`/auth/me` 落入 `anyRequest().authenticated()`；**匿名访问受保护端点 = Spring Security 6 默认 403**（非 401；401 仅来自 ServiceTokenFilter 显式 sendError 与 ResponseStatusException）——测试断言按实际行为写并注释说明；
  3. `AuthFlowTest.logoutRevokesAllRefreshTokens`：注册 + 再登录产生两份 refresh → logout 后**两份全部失效**（含未参与本次登出的注册期 token）+ 无令牌 403；
- 契约：springdoc 快照 `apps/web/src/api/specs/java-openapi.json` 经 `CONTRACT_SNAPSHOT_GENERATE=1` 重建（新增 `/auth/logout` 路径）；`pnpm gen:api` 同步 `java-api.d.ts`（+36 行）；docs/18 J1 行补 logout 登记；
- 验证：`mvn verify` 全绿（含 ContractSnapshotTest 契约对账、AuthFlowTest 5 例）；前端配套（记住我/退出接线/测试）见安卓日志同日期条；Python 零改动（`/auth` 全走 Java）；
- 边界：登出后旧 refresh 立即 401，「30 天窗口可续命」关闭；登录限流、演示账号弱密码（demo123456）为已知项（安全评审意见，未在本轮范围，建议答辩前处理）。

—— 执行人：Faust-sudo（AI 代工）

## 2026-09-07 提交与 PR：fix/p0-hardening（P0 全集+R-18+P0-7+asr_failed 修复，10 commits）

- **分支**：`fix/p0-hardening`（自 main@28cfa96），PR 已创建（base main）；
- **commit 拆分（代码/测试/文档分离，不 squash）**：
  1. `fix(py)` P0-4/P0-9 鉴权限流·限流时序·密钥三档（含契约快照刷新）
  2. `fix(py)` R-10/P0-2(audio) 信号量·ffmpeg 异步化
  3. `fix(py)` P0-1 会话态切 Redis（分级降级）
  4. `fix(py)` P0-3/P0-8/P0-2(practice)/P0-5/R-18 越权·幂等·短事务·边合成·心跳
  5. `fix(web)` R-18 SSE 客户端 idle 超时
  6. `fix(java)` P0-9 密钥 fail-fast（含 d.ts 漂移修复）
  7. `fix(deploy)` 必填密钥·模型预下载·nginx 拦截·Dockerfile 护栏
  8. `test(py)` P0 全套回归与集成安全网（Testcontainers PG/Redis）
  9. `chore(ci)` P0-7 单写方探针 + CI 模型下载步骤
  10. `docs(worklog)` 本记录 + BUG 实测归档
- **提交前门禁**：pytest **230 passed, 1 skipped**（含 pg/redis 容器用例）；ruff/format 绿；`compose config` exit 0；5 份 workflow `yaml.safe_load` 通过；此前全量检测（三端 CI 等价 + 实机 12 项）全过；
- **备注**：CI 触发路径 = PR 上 python-ci/java-ci/frontend-ci（pull_request）；docker-build 仅 push main 触发，合入后生效。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 BUG-0xx 修复：「管线提示 asr_failed」—— whisper 模型未预下载 / 容器到 HF 不可达（审计 R-11 欠账兑现）

- **现象**：练习上传音频回合 → SSE `error code=asr_failed`；容器日志 `ConnectError: [Errno 111]`（模型每次尝试从 HF 下载、容器网络不可达、`HF_HUB_DISABLE_XET` 未设——POC 备注 401 坑、R-11 点名欠账：hf-cache 未挂/未预下载/冷加载 500MB 超健康窗口；此前实机冒烟只测过 action=start 无音频路径）；
- **修复（按 R-11 预案「模型预下载进镜像」）**：① 本地 `curl --ssl-no-revoke` 下载 `Systran/faster-whisper-small` 四件套（model.bin 483MB）到 `services/python/.models-cache/huggingface/`（**权重红线不入库**，.gitignore 追加）；② Dockerfile `COPY` 进 `/app/models/whisper-small`；③ compose python-api `APP_ASR_MODEL=/app/models/whisper-small`（本地裸跑行为不变）；④ docker-build.yml 加 CI 构建前下载步骤（GHA 直连 HF + HF_HUB_DISABLE_XET=1，否则 push 后 CI build 因 COPY 缺文件失败；workflow 已 yaml.safe_load 校验）；
- **验证**：重建镜像 → 容器 healthy 且无预热失败告警 → **真音频回合全序列通过**（user_transcript→text_delta×15→score_delta→audio_chunk×3→meta_block→turn_end，零 error）；本地 `WhisperModel(本地目录)` 加载 OK；
- **踩坑（详见 BUG实测 归档）**：① 本机 Python SSL 证书链坏（uv 自带 CPython 无 local issuer；requests/httpx/huggingface_hub 全 `CERTIFICATE_VERIFY_FAILED`，curl `--ssl-no-revoke` 正常）——下载绕道 curl；② HF 仓库无 `preprocessor_config.json`（"Entry not found" 文本会被误存为脏文件）；③ 真音频热路径此前零实机覆盖（仅 Fake ASR 单测 + start 冒烟）。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 项目全量检测（P0 全集+R-18+P0-7 后终态 · 全项通过 · 可提交状态）

- **Python**：`uv lock --check` / ruff / format（121 files）/ alembic 0009 单头 / **P0-7 探针 exit 0** / 契约对账 exit 0 / **pytest 230 passed, 1 skipped**（含 pg×2、redis×4 真容器）；
- **Java**：`mvn verify` **BUILD SUCCESS**（48.7s；spotless 66 clean；38 tests 0 fail，含 ContractSnapshotTest）；
- **前端**：gen:api ×2 幂等 / lint / typecheck / **vitest 77 passed** / build 绿；
- **静态面**：compose config exit 0（含 P0-9 必填组）；5 份 workflow 本地 `yaml.safe_load` 全过；工作树 38 文件变更（+1386/−326）；
- **实机冒烟 12 项全过**：网关基础 6 项（401/404 拦截均在）+ 注册/登录/me/LLM 200 + 练习回合 SSE（turn_start1/text_delta16/audio_chunk3/meta_block1/turn_end1，快流无 ping 符合 R-18 预期）+ Redis 会话 3 键 + 缓存/音频落盘；
- **结论**：全项通过、无回归、可提交；剩余非 P0 登记项：defense/shadow DB 小段 to_thread、pg/redis 用例接 CI、DB 角色方案（M3）；**建议下一步按模块分批本地 commit（不 push）**；
- **产物**：`local/full-audit-report-2026-09-07.md`。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0-7 写方唯一性 AST 探针落地（docs/10 §3.1 矩阵 · docs/19 P0-7 · 纯 CI 面 · P0 全集收口）

- **探针**：`scripts/check_single_writer.py`（AST 精确版）——Java-owned 14 表白名单（docs/10 §3.1 总表：users/user_profiles/refresh_tokens/scenarios/songs/lrc/listening_materials/placement_questions/tickets/posts/post_comments/post_interactions/follows/post_likes 对应模型类）→ 文件级 import 映射 + `x = X(...)` 实例追踪 + 检查 `*.add(*`/`*.add_all(` 参数树（直接构造/实例变量/列表元素）→ 违规输出 `文件:行` + **退出码 1（CI 阻断,非告警）**；已知局限注释声明（不查批量 update/跨函数不追踪/flush 不单列）；
- **豁免**：`app/db/seed*.py`（docs/11 Q-A15 拍板① 初始化器语义）；tests/、alembic/ 不扫描；
- **CI**：python-ci 新增一步（docs/19 P0-7 守护必须硬门禁），workflow 已本地 `yaml.safe_load` 校验（AGENTS.md 踩坑 24/25 纪律）；
- **验证**：**现有 app 全量零违规**（接入 CI 前提,实测通过）——此前担心"写方唯一性代码层已破"，实测 Python 侧对 Java-owned 表零 ORM 写（内部委托路径 placement→/internal/level 均在，config 探针守护）；自测 7 例（直接构造/变量追踪/add_all 违规必抓、Python-owned 写+只读 Java-owned 放行、seed 豁免、全量安全网）；pytest **230 passed, 1 skipped**；ruff/format 绿（121 files）；
- **踩坑（环境级,已修）**：importlib `module_from_spec` 未注册进 `sys.modules` 时,Python 3.13 dataclasses `_is_type` 走 `sys.modules[cls.__module__].__dict__` → NoneType AttributeError —— 测试加载器必须先 `sys.modules[name] = mod` 再 exec_module（本机 anaconda 3.13 与 uv 3.12 均复现）;
- **至此 P0 全集收口**：P0-1/2/3/4/5/7/8/9 + R-04/06/10/12/18 全部落地（剩余非 P0 项：defense/shadow DB 小段 to_thread、pg/redis 用例接 CI、DB 角色方案 M3 再议）。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 R-18 SSE 心跳落地（审计 R-18 · 拍板：心跳 15s / 前端超时 90s · P0-7 顺延）

- **服务端（协议零新事件）**：`app/practice/events.py` 新增 `heartbeat_stream(inner, interval, serialize)`——`asyncio.wait(FIRST_COMPLETED)` 竞争「事件到达 vs 静默计时」；**关键设计**：静默超时**不取消**挂起的 `anext` 任务（`wait_for` 方案会以 CancelledError 杀死正在等待中的 LLM/ASR 协程——BaseException 且生成器不可恢复），仅取消除 sleep、yield 协议已登记的 `: ping` 注释行（docs/14 §3.3「每 ≤30s 推 `: ping`」此处才真正实现）；practice.py 与 free_chat.py 两处 SSE 热路径统一接线；间隔走新配置 `APP_SSE_HEARTBEAT_SECONDS`（默认 15s，协议上限 30s 的一倍余量；0=关闭）；
- **前端（sse.ts）**：`openSseFetch` 每次 `reader.read()` 独立 90s idle 计时（**任何字节——含 `: ping` 注释行——到达即重置**）；超时 → `reader.cancel()` + `onError('SSE 空闲超时')` + `onClose`（调用方既有错误分支复用，不新增 UI）；
- **测试**：后端 `test_heartbeat.py` 5 例（快流零 ping 透传 / 慢流 ping+继续 / 异常透传 / 结束收尾 / 默认 serialize）；前端 sse.test 新增 3 例（90s 无数据报错、**数据/心跳重置计时（10s+20s+80s 不超时→再 20s 超时）**、正常 EOF 仅 onClose）；
- **验证**：pytest **223 passed, 1 skipped**（+5）；前端 lint/typecheck/**77 tests**/build 绿；ruff/format 绿；实机重建 python-api 后回合 SSE 事件完整（turn_start/text_delta15/audio_chunk3/meta_block/turn_end），快流无 ping 符合预期；契约快照零影响（注释行≠JSON 事件，SSE 本就不进 OpenAPI）；
- **踩坑**：① `heartbeat_stream` 默认 serializer=sse_payload —— 若内部流已预序列化会二次序列化（free_chat 首版因此破，改为内部产出**事件对象**、由 wrapper 统一 serialize）；② 前端测试假 Response 必须带 `ok: true`（否则走错误分支）；③ 假 reader 的分支工厂若同步 resolve，三条 read 会挤在同一 tick，测不到"重置"（须按真实时序 setTimeout 分布）。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0 批次 0-3 后全栈回归 R2（三端门禁+契约对账+实机 · 1 处自引注释差异已修 · 全部通过）

- **结果**：pytest **218 passed, 1 skipped**（含 pg/redis 容器用例）/ ruff+format 绿 / alembic 0009 单头；`mvn verify` **BUILD SUCCESS**（38 tests, 0 failures, spotless 66 clean）；前端 lint/typecheck/**74 tests**/build 绿、`gen:api` ×2 幂等；实机冒烟 11 项全过（含**练习回合 SSE：turn_start→text_delta×16→audio_chunk×3→meta_block→turn_end**、Redis 会话 4 键、TTS 缓存/音频落盘）；
- **唯一发现（自引，非功能）**：`GET /api/v1/scenarios` 契约快照对账红 —— 批次 1 给 `list_scenarios` **docstring** 加了"P0-2 to_thread"一行 → FastAPI 将路由 docstring 写入 OpenAPI `description` → 文本级对账（CI 同口径）必红；**处置**：说明移入函数体注释、docstring 复原 → 对账 ok（exit 0）；**踩坑登记**：路由 docstring 属契约面，实现说明一律写代码注释；
- **产物**：`local/regression-report-R2-2026-09-07.md`；后续建议（报告 §7）：A. P0-7 探针（0.5 天）→ B. R-18 SSE 心跳（1 天，前后端）→ C. defense/shadow DB 小段 → D. 集成用例接 CI。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0 批次四：边生成边合成（首声预算）+ orchestrator 落库短事务化（docs/19 P0-5/P0-2 · 审计 R-04 · 拍板：音频=流文本/仅运行时缓存/仅 dialog 段）

- **P0-5（审计 R-04：逐句串行 + 等 LLM 全文结束 → 推算 6.1~7.6s 超 3~6s 预算）**：
  - `StreamSentenceSplitter`（纯函数）——流内 `.!?`(`+ 后随空白/引号`) 立即出句、跨 chunk 安全、**无标点长句 >300 字符在词边界截断**、流末 `flush()` 闭合尾句、**纯标点句过滤**（"Wow!!" 不产出独立 "!"）；输入为 TurnRunner 泄漏门放行的纯正文（META 已剥离，拼接==权威 reply_text——一致性前提）；
  - `_dialog_turn` 流循环内：出句即 `create_task(_synth_sentence)`（任务引用列表防 GC）→ 主循环**非阻塞按句序 drain** `AudioChunk`（乱序完成由 seq 归一；首声=ASR+首 token+1 句 TTS ≈3.5~4.5s）→ 流结束 flush+`gather` 排空；失败句跳过（字幕继续，docs/14 §3.2）；删除旧串行 TTS 块（`audio_urls` 改 `emitted_urls` 收集）；
  - **预合成缓存接线**（`cached_audio_path` 定义后零调用）：`_tts_url_from_bytes` 查缓存→合成→**原子写缓存**（`tts.atomic_write_cache`：tmp+os.replace 防并发/半文件；key=sha1(voice|rate|text)，目录 `{audio_dir}/cache/tts` 随清理策略覆盖）——首遍后同句即时返回；
- **P0-2 顺手兑现（dialog 热路径）**：落库段（user 消息+attempt+assistant 消息+commit）整段收进 `_persist_dialog_turn`（to_thread，**零 asyncio 依赖**：score 已 await、hits/fluency 线程外备齐）；`get_session_summary`/`get_rendered` 读库改 to_thread 预取；`state` 推进仍在异步侧（运行时态）；defense/shadow 小段按拍板未动（登记）；
- **验证**：pytest **218 passed, 1 skipped**（+8 切分器用例；pg/redis 容器用例仍绿）；ruff/format 绿；**实机 SSE 事件序 `turn_start → text_delta×18 → audio_chunk×3（逐句按序） → meta_block → turn_end`**；缓存 4 条 + 音频落盘确认；
- **踩坑**：① `Path` 忘记导入（TTS 缓存接线后任何合成即 NameError——靠 test_shadow 全回合抓到）；② `rstrip` 而非 `strip`——句尾引号会被边界匹配吞入句内（"Great job!  \""）；③ `tts_sentences` 移除引用后需确认无残留使用。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0 批次三：Testcontainers 安全网 + 会话态切 Redis + 同步 IO 短事务化（docs/19 P0-1/P0-2 · 审计 R-12/R-10 · 拍板：本地安全网/分级降级/安全子集）

- **① Testcontainers 安全网（先行，dev 依赖 +testcontainers 4.15、uv.lock 更新）**：`tests/test_pg_integration.py`（marker pg）——真 PG(16-alpine) 跑 `alembic upgrade head` + **`alembic check` 零 diff**（docs/10 §7.1-6 「M2 接 PG 首日门禁」首次真正落地）+ 完整回合/重复 complete 幂等/越权 40401（抓 JSONB/timestamptz/唯一约束）；`tests/test_redis_state_store.py`（marker redis）——SETNX 互斥、Lua 比较删除、TTL、降级与严格模式。无 Docker 自动 skip，不破坏默认门禁；
- **② P0-1 会话态切 Redis**：`state.py` 重构——`RedisStateStore`（`session:{id}` JSON EX 1800 + `lock:{id}` NX EX 60 + **Lua 比较删除**防错删他人锁）+ `MemoryStateStore` 保留为单测桩/降级后端 + `StateStore` 组合门面（接口不变，调用方零改动）；**降级按 `redis_required` 分级**（默认降级内存+60s 限频告警；严格模式抛错可感知），降级改 **协程工厂惰性化**（严格模式抛错时无 unawaited coroutine 警告）；
- **③ P0-2 安全子集**：asr/ise 的 ffmpeg `subprocess.run` → `create_subprocess_exec` + **15s 超时强制 kill**（超时/非零/找不到均带可读错误；顺带移除两文件 subprocess 导入）；`app/db/__init__.py` PG 显式 `pool_size=20/max_overflow=10/pool_timeout=5`；路由层（`_require_session_owner`/`list_scenarios`/`get_report`/`get_audio` 归属/`complete_session` 调用）与 `create_session` 的同步 DB 移入 `to_thread` 短事务；**orchestrator 内 6 处内联 DB 段按拍板留待 P0-5 同批**；
- **验证**：pytest **210 passed, 1 skipped**(pg×2 + redis×4 真容器跑通；新增 9 例)；ruff/format 绿；实机——python-api 重建 healthy、migrate 幂等(seed +0)、无 token /tts 401、**建会话后 `session:1` 出现在 compose Redis**（P0-1 端到端）；
- **安全网首次抓到方言差异**：① testcontainers 4.15 PG URL 为 `postgresql+psycopg2://`（须归一为 +psycopg）；② 真 PG FK 强制（SQLite 不校验）——完整回合用例须先种 `users` 行（测试内修正，非代码缺陷）；③ legacy `RedisContainer` 无 `get_connection_url()`（手工拼 URL）；④ pytest-asyncio 每用例独立事件循环 → redis 连接绑定 loop（客户端改**函数级**、容器保持模块级）；
- **待办登记**：pyproject/uv.lock 变更待审；pg/redis 标记用例接入 CI 留单独 PR（本次按拍板未动 workflow）。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0 批次回归测试（全栈门禁 + 实机冒烟 · 无回归 · 放行 Batch 2）

- **范围**：Batch 0（鉴权限流/信号量/密钥三档）+ Batch 1（越权守卫/报告幂等）落地后全量回归，对齐三端 CI 命令 + 容器经网关冒烟；
- **结果**：pytest **205 passed**（not gpu 口径）/ ruff+format 绿 / alembic 单头 0009 / Python 契约快照对账一致；`mvn verify` **BUILD SUCCESS**（spotless 66 clean；**38 tests, 0 failures**，含 ContractSnapshotTest）；前端 lint/typecheck/**74 tests**/build 全绿、`gen:api` 两次生成幂等；实机冒烟 8 项全过（重点：`/api/v1/tts` 无 token → **401**、`/manage/internal/level` → **404** 新拦截、注册/登录/me/带 token LLM 全 200）；
- **环境告警（非代码）**：本机 `apps/web/node_modules` 缺 `@vue/test-utils`（package.json/lockfile 已声明）→ `pnpm install --frozen-lockfile` 补齐后全绿；CI 新鲜安装无影响；
- **产物**：`local/regression-report-2026-09-07.md`（过程性报告，不入库）。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0 批次二：会话/报告越权守卫 + 报告幂等（docs/19 P0-3/P0-8 · 审计 R-05 · 拍板：短路+upsert 兜底/继续仅工作区）

- **P0-3（三处越权）**：`post_turn` / `complete` 入口新增 `_require_session_owner()`（短 SELECT `sessions.id+user_id`，权威源=DB，不依赖 StateStore 键空间）——**优先于读音频/落盘/LLM 摘要/限流**；`get_report` 改为 `Report JOIN sessions`（Report 无 user_id 列，scope/scope_id 多态引用无 FK——docs/10 开放项 D-1；非 session 报告暂无可读场景→一律 40401）；越权响应统一 404/40401（docs/api/error-codes.md 40301 行登记口径「不泄露存在性」，未新增错误码）；
- **P0-8（报告幂等）**：`complete_session` 重构——① 同键报告已存在（已完成会话再 complete）→ 短路返回既有 report_id（快照不动、不重算不覆写 sessions）；② 生成侧先查后更（docs/10 模型注记「重复计算=整行覆盖写」），并发/重复计算撞 `uq_reports_scope_period` 由覆盖写吸收，不再 500；
- **测试**：新增 `test_report_ownership.py` 4 例（user2 读 user1 报告→40401 / user2 提交 turn→40401 / user2 complete→40401 / 重复 complete→200 同 report_id 且仅 1 行，修复前分别 200/200/200/500）；既有 `test_rate_limit_429`、`test_turn_rejects_empty_audio` 因「归属校验先于输入/限流」适配为真实会话（意图不变）；
- **验证**：pytest **205 passed**（+4）；ruff check/format 绿；契约快照零新增 diff（无接口签名变化）；python-api 重建后 healthy + 无 token /tts 仍 401；仍仅工作区、未 commit/未推送；
- **踩坑**：① 归属校验前置改变了校验顺序——凡"故意用不存在的会话测输入守卫/限流"的用例都必须改为真实会话；② `Report` 原为函数内局部 import，重构后须提升到模块级（`from app.models import Report`）。

—— 执行人：Faust-sudo（AI 代工整理）

## 2026-09-07 P0 止血批次开工：裸端点鉴权限流 + 信号量 + 密钥三档（docs/19 P0-4/P0-9 · 审计 R-06/R-10 · 拍板：三档策略/全链路统一扣减/仅工作区）

- **范围(组内拍板 2026-09-07)**：Batch 0 = P0-4(语音裸端点鉴权+分桶限流+先校验后扣)+ P0-9(密钥三档 + nginx 拦 /manage/internal)+ R-10(whisper/ISE 信号量 2)——零迁移、不进 GitHub(先本地评审)；
- **P0-4(审计 R-06)**：`audio.py` 四端点(`/asr /score /tts /llm/chat`)挂 `get_current_user_id`(401)+ 分桶 consume(429)；**先校验后扣额度**并**全链路统一**——`practice.py` 原先由 `_rl_*` 依赖先扣后校验，改为预检(状态/归属/输入)通过后再扣；`free_chat.py` 同步统一且 ASR 桶仅实际转写时扣(docs/19 P1-5 按实际消耗)；`placement.py` 已是参考实现(L76-83),未动;
- **R-10(docs/06 §8)**：`asr.py`/`ise.py` 各加模块级 `asyncio.Semaphore(2)`(复核：此前全仓 0 个 Semaphore)+ Dockerfile `--limit-concurrency 10` 兜底;
- **P0-9**：Python `config.py` 密钥**三档**(testing→固定测试值/development→缺值告警/production→缺值启动即失败)+ Java `application.yml` 去默认值 + `JwtService`/`SecurityConfig` 构造期 fail-fast(≥32 字节, docs/06 §11)+ compose 显式 `${JWT_SECRET:?required}` 四组 + nginx `location /manage/internal/ { return 404; }`;**顺带揪出真实隐患**:根 `.env` 缺 `APP_JWT_SECRET/APP_SERVICE_TOKEN`,Python 一直靠 config 默认值(恰好同值)才工作——已补两键(本地 gitignored),compose 改为必填后此口关闭;
- **验证**：pytest **201 passed**(新增 4 例:生产档抛错/开发档告警/testing 回退/显式值不被覆盖 + audio 401 失败用例);ruff check+format 绿;`mvn verify` **BUILD SUCCESS**(spotless 66 files clean,测试全绿——测试档密钥走既有 `application-test.yml`,零 CI 改动);compose config 校验通过;契约快照待刷新(4 端点新增 header 参数,结构 diff 已核对);
- **踩坑**：① pydantic-settings 下测试进程 env `APP_TESTING=true` 会让 production 用例走 testing 档——用例须显式 `testing=False`;② `.env`(GBK)非 UTF-8,常规文本工具读写会乱码,追加用 `Add-Content -Encoding Default`。

—— 执行人：Faust-sudo（AI 代工整理）

# 2026-09-06 /auth/forgot 忘记密码（演示口径：工单闭环 + 防枚举 · 51 op）

- 背景：组长反馈 Sign Up 应真注册、Forgot password 也要做；注册复用既有 `/auth/register`（前端补注册表单、注册即登录）；
- **forgot**：`POST /auth/forgot {username}`（public）→ 用户存在则落 `tickets(feedback / 密码重置申请 / open)`（工单写方 Java，管理员侧可见可处理）；**防枚举**：存在与否同响应文案；演示环境无邮件/短信通道（登记：真实重置需邮件/短信通道 + 一次性令牌，P2）；
- 测试：AuthFlowTest 增 forgot 用例（工单落库 kind/title/status + 防枚举同响应）→ `mvn verify` 35 全绿；快照刷新 51 op + gen:api；前端 LoginView 3 例。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-06 社区 S2 实施（关注 + 互动通知真实化 · docs/41 定稿）

- **背景**：docs/37 定稿 §5 预留的 S2 = 关注 + 通知中心「通知/关注」两 tab 真实化；私信维持演示（IM 范围）；
- **Java（6 端点 · 50 op）**：FollowEntity/Repository（S1 建表 S2 实体化）+ 关注 4 端点（PUT/DELETE 幂等、自关注 42203、目标不存在 40402、推荐关注 followed 标记）；关注流 keyset（Criteria authorIds IN，未关注空短路）；**互动通知派生 + mergeKey 聚合**（(post, action, 当日 UTC) 分组 → 「张三 等 N 人…」，评论逐条，排除自身动作，仅本人可见帖，阈值游标 base64(ts|itemId)，演示窗口 50 条登记）；
- **前端**：通知中心两 tab 接真（通知=聚合文案+类型图标；关注=推荐关注管理+关注流）+ 顶栏「加好友」收口为跳「关注」tab；api/community.ts 增 6 函数；
- **测试**：Java `CommunitySocialTest` 5 例（幂等/越权/关注流/聚合/隔离）→ `mvn verify` **34** 绿；前端 4 例（聚合/关注流/动作重载/?tab 直达）→ vitest **71** 绿；lint/typecheck/build 绿；契约快照刷新（50 op）+ gen:api；
- **踩坑**：① `@PathVariable` 参数名与路径变量不一致 → 关注写入静默未生效（显式 `@PathVariable("userId")`）；② 模板内 TS 断言 `as A | B` 被 vue 编译器当过滤器 → 类型收窄移入 script；③ 旧测试对通知中心演示断言迁出（被新专用测试取代）；
- **登记**：docs/21（50 op + S2 两行）、docs/41（新，README 索引）、README 能测段、双日志。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-06 社区内容 S1 实施完成（P1 模型+契约 → P2 打卡委托 → P3 前端接流 → P4 登记；按 docs/37 定稿 + docs/40 计划）

- **P1 模型+契约（11 commits）**：契约冻结 5 项先登记（51ecb2d：错误码 40402/40302/42203/40904、envelope keyset 游标例外、/internal/checkin 契约、R-17 头修正、docs/20 写方矩阵）→ 迁移 0007（社区 5 表 + post_likes 键改造 0 行断言 + user_profiles.handle/tint + 部分唯一 uq_posts_checkin 双方言）+ 0008（存量 alembic check 漂移修正：user_skill_state 约束名/usage_log 索引声明；8225e38）→ Java 社区 10 端点 + 统一可见谓词 + 幂等互动 + CommunitySeeder（虚构作者 8 帖 + 历史打卡卡；5ce24fa）→ 单测 11 例（41c3328）+ 单写方探针 pytest 形态 M-2（315d57e）+ 契约快照（ab21114）。**踩坑**：① H2/JVM Instant 纳秒 vs DB 微秒精度差 → 游标归一 %1000（%1_000_000=毫秒会重复返页）；② @Modifying 计数不自清一级缓存 → 回读旧值（flush+clear）；③ 测试类无 @Transactional 方法间泄漏数据（补隔离）；
- **P2 打卡内部委托（5 commits）**：统一 internal client（3s + raise_for_status + camelCase；b14a0d2/f6e91eb）+ **修复 P0-6**（placement 档位回写 user_id→userId + 不再静默吞错；双侧契约测试回归）；complete_session 收尾触发打卡物化（仅 dialog、快照=最新 attempt、幂等键 (userId, practiceDate)）；迁移 0009 sessions.checkin_synced_at。**踩坑**：JwtAuthFilter 解析内部域伪 Bearer 失败清空 ServiceTokenFilter 身份 → 内部端点 403（已修：/internal/** 跳过 JWT 解析）；
- **P3 前端接流**（e5dd13d/8df1245，UI 明细见 `worklog/安卓开发日志.md` 同日条目）：api/community.ts（JAVA_BASE + 集中映射）+ stores/community.ts（游标/领域过滤/乐观回滚）+ 视图组件契约对齐（kind 真源 article/video/checkin、投币改「支持」不可取消、发帖领域 chips、评论面板真实流、通知中心标注演示）；community-demo.ts 删除；预览联调页 /preview/community（后端 test-only 开关豁免登记 docs/13 §8）；
- **P4 登记（本 commit）**：docs/06（§1/§9.6/§9.7/§10/§14）、docs/10（表 19→24 + 社区注记 + 写方矩阵）、docs/21（44 op、R-7 已修、P0-6 已修）、docs/34 §7 口径、docs/13 §8 例外、README（技术栈 Java 行 + 能测社区段）；
- **验证**：pytest **195** 绿（含探针/内部委托 7 例）、`mvn verify` **29** 绿（社区 14 例 + 契约快照对账）、`alembic check` 真 PG **零 diff**、vitest **65** 绿、lint/typecheck/build 三端全绿；
- **演示/联调**: `/preview/community` → `/m/home`（`VOICEVERSE_COMMUNITY_POST_ENABLED=true` + Java 种子）；冒烟路径见 docs/40 §1 DoD。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-06 社区内容 S1：调研 → 四官拷问 → 方案定稿 → 实施计划（组长全量认领）

- **背景**：移动端 community UI 已由组长完成（帖子+视频/三领域/投币/评论/发帖/关注/通知中心），docs/37 初稿按 docs/20 §3.1 判据落 Java 承办 + 打卡物化；
- **调研**：`docs/38-社区内容企业级实践调研.md`——企业级「帖子/图片/视频」处理手册（Media 单表+状态机+variants / 图片多规格+EXIF 清理+对象存储抽象 / 视频分片上传+异步转码回调验签 / status×auditStatus 正交+先审后发 / 统一可见谓词 / 计数冗余+唯一约束 / 游标多取一 / mergeKey 通知聚合 / 动作维度限流）；**来源项目按约定不披露**；
- **拷问**：`docs/39-社区内容方案拷问报告.md`——四官 68 问（A 需求/产品 19 · B 技术/架构 18 · C 数据/合规 18 · D 企业融合 13）+ 合流官裁决（11 冲突/9 P0/16 拍板/3 开放项）。**P0 命中**：发帖无标题 vs 卡片渲染 title·domain 中英映射缺失·打卡「每日一卡刷新丢进步」·投币免费可取消背离打赏心智·公开仓库注册即发帖无收口·种子作者 handle/tint/LV 无源·**checkin snake_case 契约复刻 P0-6 已证实的坏 bug**·错误码 40101 撞车·keyset 分页 vs PageView 契约冲突·新表不进 Python metadata 则 alembic check 必爆·feed 索引形状错配；
- **裁决落地（docs/37 定稿）**：投币→**「支持/充电」不可取消一人一帖一次**（无积分账户）·发帖**纯文本**（media 字段悖论消除）·keyset 契约+envelope 游标例外·错误码 40402/40302/42203/40904·feed 双索引+EXPLAIN·LV=cefr_level·handle/tint 入 user_profiles·checkin **新建统一客户端**（camelCase+raise_for_status+3s，顺带修 P0-6）·打卡**当日聚合卡**（公开面 {overall, practice_count}）·公众发帖默认关闭（VOICEVERSE_COMMUNITY_POST_ENABLED）·反借鉴清单（积分账户/多状态机/收藏夹/云转码/ES/队列全剔除）；
- **实施计划**：`docs/40-社区内容S1实施计划.md`——契约冻结 5 项前置、P1~P4 拆解（子任务/门禁/人日 7.5~9）、测试矩阵（H2/PG Testcontainers/前端/端到端）、实施期风险回退、超期回退预案；
- **认领**：组长 LHRCarrier 全量（Java/Python/前端接流/文档登记）；Faust-sudo、xiaoqing-one 不涉及；PR 互审按 docs/05（组员任一 1 人，无空闲则直推报备）；
- **待组长点头 2 项**（不阻塞启动，已按建议值写入）：① 预览页后端 test-only 开关豁免（社区接口即生产接口，登记 docs/13 §8 例外）；② 打卡公开字段集 {overall, practice_count}。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 README 重写：定位从「口语训练平台」演进为「学英语」App（组长定调）

- 组长定调：项目定位是**学英语**——各功能都往学英语上使劲：场景练习（开口说）、AI 自由说（先聊起来）、社区帖子新闻英文氛围（阅读与语感 + 文化习俗）、英文歌（高强度跟读）；**定位不是一成不变的，而是慢慢演进的**（演进方向写成规划，不做承诺式描述；该句不入 README，仅团队内部口径）；
- README 更新：① 开头定位与「练/浸/唱」三线功能矩阵重写；② 新增「演进方向（规划中）」：**词汇速记**（划词即查 → 个人词汇本，形态以设计为准）、**学习画像**（讯飞测评数据红利：弱音素/高频错词/流利度趋势）、**社区偏好画像独立系统**（点赞/投币/浏览行为与学习画像解耦）；③ 「当前能测」对齐现状（社区演示帧、先选场景流程、AI 自由说、15 类埋点、救援提示卡已下线）；④ 里程碑补 M2.5 移动端真形态；⑤ 工作日志行补安卓开发日志；
- 提交：docs(README) 单独 commit，直推 main（管理员直推，无 PR）。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 【迁移】App 端 UI 记录迁入安卓开发日志（组长指正 · 2026-09-08 已定规）

> 组长指正：**App 端 UI/设计相关记录归属 `worklog/安卓开发日志.md`**（本日志只留 Web/后端/全局事项）。
> 今日以下 App 端 UI 记录已全部迁往安卓开发日志（含后续组员反馈修正痕线，未改动内容）：
> 场景对话「先选场景再开工」开始流程 · 口语 Hub 收敛删除 · 自由对话页 Grok 式改造（3 子代理评审）·
> 口语界面 3 项（气泡尾巴/自动播/Hub 与自由对话最小可用版）· 移动端场景对话 2 个 UI 修（气泡尾巴+开场白自动播）。
> 其中涉及后端/迁移/契约的部分在主线下条留存，UI 与前端交互细节以安卓开发日志为准。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 自由对话后端与埋点（非 UI 主线留存：接口 / 迁移 / 契约 / 登记）

- **接口**：`routes/free_chat.py` `POST /api/v1/free-chat/turn`（multipart `audio`/`text` + `history` JSON，至少其一 → 422 404 码 42203/42204）→ SSE 子集 `user_transcript→text_delta*→turn_end`（`score_status=unavailable`）；无状态 LLM 转发器（TurnRunner 复用、system 全静态人设、无 corpus）；限流 asr+llm；**进 OpenAPI 契约**（快照 + gen:api 同步，frontend-ci 对账一致）；
- **埋点白名单扩值（迁移 0005/0006）**：`events.event_type` CHECK 10→12→15 类（`free_chat_open`/`free_chat_turn`/`free_chat_switch`/`free_chat_reset`/`free_chat_rate`；reset 随功能行改版恢复触发、rate 为预留）；alembic 单头 0006，本地 PG 已应用；docs/06 §9.1、docs/10 注记、docs/14 §6.3 登记；
- **测试**：`tests/test_free_chat.py` 6 用例（流式/校验/多轮 turn_index）+ `test_m2_core.py` 埋点 12→15 类逐类落库断言；后端 ruff+format+全量 pytest 绿；
- **坑**：① uvicorn `--reload` 多轮重载后子进程僵在 lifespan → 杀进程重启 dev-up；② `refresh-openapi.ps1` 导出的 Java 快照与库内差异仅 `servers` 字段 + 格式化（本地 springdoc 与 CI 生成路径不同）→ 回滚 Java 快照只提交 Python 快照；③ 埋点事件是 **DB CHECK** 白名单：改前端 `EventName` 之外必须同步 `EventTypes` + 迁移，缺一不可；④ `EventTypes` 注释超 100 列触发 E501。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 dev-up.ps1 自动拉起 DB 容器（修「电脑重启后 Java 起不来」的坑）

- 触发：重启电脑后跑 `pwsh -File scripts/dev-up.ps1 start`，健康等待后 `java(8080): False`；`local/dev-logs/java-8080.out.log`：`HikariPool-1 - Starting...` → `Connection to localhost:5432 refused` → `Unable to determine Dialect without JDBC metadata` → 上下文中止，mvn BUILD FAILURE（5.8s，非 30-60s 慢启动）；
- 排除「数据库密码改过」疑点：**Connection refused 发生在 TCP 建连阶段**（密码错应是监听端口存在时的 `password authentication failed`），且核验三处一致——PG 容器 init 环境（docker inspect）＝根 `.env`＝`services/java/application.yml` 默认回退均为 `vocalverse-dev`；
- 根因：主机睡眠/重启后 Docker 引擎恢复时杀掉容器——`docker ps -a`：`vocalverse-postgres-1` / `vocalverse-redis-1` 均 `Exited (255)` 且**同一秒同死**、容器日志无正常 shutdown 记录（止于 checkpoint）、exit=255 非 postgres 自身崩溃；而 `dev-up.ps1` 原文写明「脚本不负责数据库容器」，DB 死了无人拉起；
- 修复：`scripts/dev-up.ps1` start 新增 `Wait-DockerBase`——5432/6379 已监听则跳过；否则检查 Docker 引擎（未就绪尝试启动 Docker Desktop，等待 ≤90s）→ `docker compose up -d postgres redis` → 轮询 `docker compose ps` 至 postgres/redis 均 healthy（≤90s，Exited/unhealthy 提前退出并给排查命令）；
- 验证：`docker compose stop postgres redis` 制造复现 → `dev-up.ps1 start` 自动拉起两容器并 healthy → `python(8000)/vite(5173)/java(8080)` 全 True；`status` 复核 8000/8080/5173 全 LISTENING、health 全 True；
- 踩坑：① `docker compose ps` 默认只列**运行中**容器，判 healthy 要 `--format "{{.Service}}:{{.Status}}"` 按 service 名匹配（容器名带项目前缀）；② 端口健康用 `Get-NetTCPConnection -State Listen`，Docker Desktop 的 docker-proxy 仍在监听即视为容器可服务，无需连库探测。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-08 UI 相关记录迁移说明

> 组长指正：**App 端 UI/设计相关的记录归属 `worklog/安卓开发日志.md`**（本日志只留 Web/后端/全局事项）。
> 今日以下 UI 记录已全部迁往安卓开发日志：对话页细节修正 · v6.0 首页重设计 · v5.x 登录页复刻 ·
> v4.0 配色定稿 · v3.3 soft-brutalism · v3.1 对抗评审 · 图标库/UI 库调研 · Soft UI 样板阶段 ·
> app 端 UI 重制（5 页替换真实路由）。以后 UI 修改按 `docs/33-UI修改SOP.md` §5 落日志。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-08 fix(apps/web): 整页刷新/App 冷启后会话不恢复（bootstrapAuth 时序 bug · 实测命中）
- 现象（app 端电脑测试验证时暴露）：登录后一切正常，但 **F5/重启 WebView 后所有 `/api/v1` 请求 401「missing bearer token」**（token 明明还在 localStorage，手动带头上请求 = 200）；
- 根因：`main.ts` 里 `void bootstrapAuth()` 写在 `createApp(App).use(createPinia())` **之前**——`useAuthStore()` 此刻无 active pinia 直接抛错，被 `.catch(() => undefined)` 静默吞掉 → `setAuthToken` 从未执行，client.ts 全局 token 恒 null。SPA 内跳转不受影响（登录时 persist 已设置），所以此前 W1-W6 联调没暴露；
- 修复：`createPinia()` 先安装、`bootstrapAuth()` 在 mount 前调用（同步段先于页面 onMounted，首个请求即带 token）；注释写明时序硬约束；
- 验证：dev(5173) 代理到 compose 真后端——登录 → **reload** → `/m/chat`：`POST /manage/auth/refresh 200` → `GET /api/v1/scenarios 200` → `POST /api/v1/sessions` → `POST /api/v1/tts` 全通，页面渲染真实开场白（机场值机）与目标轮数；lint/typecheck/build 全绿；
- 影响面：APK 冷启动（WebView 每次加载都是整页刷新）同样受益——之前每次冷启都必须重新登录，修复后自动恢复会话。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-07 UI Concept Design skill 返工 v2：诊断规则漏洞 + 原型页对照参考帧重做

- 触发：组长反馈 v1 原型"效果一般"。对照 skill 自带的 7 张原版设计帧逐项诊断，问题一半在 skill 规则、一半在 v1 执行：
- **skill 规则漏洞（已修）**：① 参考帧最核心的**大幅手绘线稿插画**（气球/日历/星星母题）完全没写进 SKILL.md——这是"像原版"和"像普通后台"的分界线；② 图标块规格写错：帧里是**品牌色实底 + 白图标**（Burrito Bowl 深棕块），v1 做成了浅 tint 底彩图标；③ 次级按钮漏了纸面变体（白底+1.5px ink 描边，ref-landing-hero "View Leaderboard"）与白卡变体（track 灰底）的区分；④ 深色卡 badge 应为 **12px 圆角 chip** 不是胶囊；⑤ 尺度偏小：Display/Stat/分段控件/留白全往大气调（Display 48-56px / Stat 32px+ / 分段高 56px / 页边距 40-56 / 卡内边距 32）；⑥ 新增 tokens：pop-green `#A8E05F` 插画填涂色（仅限插画）、信任条与点线时间轴规则；
- **skill 遗留问题**：`templates/winforms/` 原缺失，已补 `Theme.cs`（色板/字体圆角令牌，dotnet 8 可编译）；`ThemeControls.cs` 未写——组长确认 Web 项目不需要 WinForms 模板，硬约束 ③ 改为"仅 WinForms 项目用模板，Web 跳过"；
- **原型页 v2（对照参考帧重做）**：三页全部加插画锚点（新增 `UicArt.vue` 手绘线稿组件：热气球/日历/星星/音符，2.5px ink 圆头线 + pop-green 填涂，悬停 200ms 微飘）；首页 = 双侧对称插画 hero + 信任条 + 点线时间轴列表；口语页 = 56px 分段控件 + 实色图标块 + 深藏青推荐卡（光晕 + chip）；唱歌页 = 深紫卡（光晕 + 大幅音符插画 + 总分 64px）+ 逐句点线时间轴；
- 验证：`pnpm lint`（0/0）/ `pnpm typecheck` / `pnpm build` 全绿；dev server 4 模块 transform 200；生产构建确认 uic 零残留；
- 入口不变：`/preview/uic-home`、`/preview/uic-speaking`、`/preview/uic-singing`（v2 已热更新，Ctrl+F5 强制刷新查看）。

—— 执行人：LHRCarrier

## 2026-09-07 UI Concept Design skill 原型验证 · 3 个概念页（dev-only 预览画廊）

- 背景：组内 `.trae/skills/ui-concept-design` skill（模板驱动现代桌面 UI：以视频原版设计帧为视觉正本 + 精确 design tokens + 组件决策树），用本仓库做效果测试首发；
- 产出：`apps/web/src/views/preview/uic/` 下 3 个概念页 + 共享 tokens 样式，走 docs/13 §8 预览工作流（registry.ts 3 行 + router/preview.ts 3 条路由）：
  1. `UicHome.vue` 学习主页 —— hero 双胶囊按钮（ref-landing-hero-light）+ 统计行（ref-profile-card-stats）+ 分段控件（ref-segmented-pill）+ 时间线列表卡（ref-card-light-timeline）；
  2. `UicSpeaking.vue` 口语陪练 —— 场景分类分段控件 + 场景卡网格 + 深藏青推荐卡（ref-dark-colored-cards，每屏 1 张深色卡约束）；
  3. `UicSinging.vue` 唱歌评分报告 —— 深紫总分卡（同色系 badge + 幽灵按钮）+ 四指标统计行 + 逐句评分卡；
- 价值观全部取自 skill 的 `tokens/design-tokens.md`（paper `#F5F4F1` / 白卡 r-24 / 炭黑胶囊主按钮 / accent `#2F6BFF` 唯一点缀 / shadow 仅一档 `0 8 24 rgba(28,28,26,.06)`），共享文件 `uic.css` + 线性图标组件 `UicIcon.vue`（1.5px 描边）；
- 验证：`pnpm lint`（0 warning 0 error）/ `pnpm typecheck` / `pnpm build` 全绿；生产构建产物确认不含 uic 任何 chunk（预览子树整枝剔除，零残留）；
- 与现有 docs/13 设计系统（多邻国活力绿）的关系：**概念页独立成体系**，仅供对比验收，未接入真实 view；验收后按各文件尾注释删除清单移除（删 4 处，门禁复绿）；
- 注：skill 的 `templates/winforms/` 模板目录在 skill 包内缺失（只有 references/ + tokens/），本次按 Web 端转译为 CSS 组件类，WinForms 侧使用时需补模板或按 tokens 重建。

—— 执行人：LHRCarrier

## 2026-09-04 方式 A `migrate` 一次性服务修复（uv run 前缀 + seed 容器路径/挂载）

**背景**：PR#27 方式 A 容器实测时发现 `docker compose up -d migrate` 从基线起就不可用（此前被「容器能起」掩盖）：① 命令裸 `alembic`（镜像内依赖在 `.venv/bin`，缺 `uv run` 前缀）→ `alembic: not found`；② 补前缀后 `seed.py:25` `parents[4]` 在容器布局（`/app/app/db/seed.py` 仅 4 级父目录）越界 → `IndexError: 4`（**与 PR#27 复审 P0 的 `main.py parents[3]` 同类容器路径假设**）；③ 种子数据 `data/seed/scenarios.json` 在仓库根，镜像构建上下文仅 `services/python`，容器内无该文件。

**修复**（2026-09-04 · LHRCarrier）：
1. `docker-compose.yml` migrate：`alembic upgrade head && python -m app.db.seed` → `uv run alembic upgrade head && uv run python -m app.db.seed`；
2. migrate 挂载 `./data/seed:/app/data/seed`（与 `./data/audio` 同约定，种子数据入库文件进容器）；
3. `app/db/seed.py`：`try/except IndexError` 布局感知——本地 `parents[4]`=仓库根；容器回退 `Path("/app")`。

**验证**：`docker compose config --quiet` ✓；`docker compose build migrate` ✓；`docker compose up -d migrate` → `Context impl PostgresqlImpl` + `[seed]…（跳过已存在）`，退出码 0，幂等 ✓；`ruff` / `pytest（test_seed + test_seed_recommend 6 passed）` ✓。完整复现/根因/踩坑见 `worklog/BUG实测/方式A-migrate一次性服务无法执行.md`（踩坑 3 条：migrate 失败不阻塞 compose、容器路径假设第三次踩坑、compose 命令需与镜像运行时同前缀）。

—— 执行人：LHRCarrier

## 2026-09-04 PR#27 复审整改：容器布局 `parents[3]` 越界 P0 + 「compose 注入 HF 三件套」失实表述更正

**背景**：PR#27（方式 B 三连排障）复审（LHRCarrier，`gh pr review --request-changes`）发现三点阻断：① `Path(__file__).resolve().parents[3]` 在容器布局（Dockerfile `WORKDIR /app` + `COPY . .` → `/app/app/main.py`，parents 仅 3 级）越界 → `IndexError` → 容器导入即崩，方式 A 全栈不可用（现有 CI 结构上测不出：python-ci 在 runner 上路径成立、docker-build 只 build 不 run）；② 代码注释/README/归档所述「容器由 compose 注入 HF 三件套（挂载 ./data/models）」与仓库事实不符——`docker-compose.yml` 无任何 `HF_*` 变量、仅挂载 `./data/audio`，docs/06 §8 模型缓存约定为 `hf-cache:/root/.cache/huggingface` 命名卷（默认缓存路径），审计 `docs/audit/语音链路现状与风险清单-V2.0.md` K03 明言 xet 变量未进 compose/Dockerfile；③ 与 main 冲突（worklog），且 PR 带入一个**无正文的游离标题**「## 2026-09-09 PR#25 推荐系统落地…」（main 本就有该记录，正文在 09-02 组）。

**修复**（2026-09-04 深夜 · LHRCarrier 执行）：
1. `services/python/app/main.py`：`try/except IndexError` 布局感知——本地布局（parents[3]=仓库根）注入 `HF_HOME=<仓库>/data/models` + `HF_HUB_OFFLINE=1`（setdefault，尊重显式覆盖）；容器布局跳过二者（维持 HF 默认缓存路径 = hf-cache 卷约定，不破坏容器首次下载流程）；`HF_HUB_DISABLE_XET=1` 两布局通用（docs/18：xet 401 绕过）；
2. 失实表述全仓更正：main.py 注释 / dev-up.ps1 注释与 setdefault 语义 / README FAQ 行 / BUG 实测归档两篇 / 主日志四条记录 / PR 描述——统一为「方式 B 本地 = 仓库 `data/models`；容器 = hf-cache 卷 + 默认路径（compose 未注入，K03 未闭合，另立整改）」；
3. `scripts/dev-up.ps1`：三变量改为仅在用户未显式设置时注入（与 main.py `setdefault` 同语义，尊重显式覆盖）；
4. `.gitignore` 补 `data/models/`（模型权重红线：禁止提交；此前未忽略 → `git status` 污染 + 误提交风险）；
5. rebase origin/main 解决 worklog 冲突：四条 09-04 记录按日期归入 09-04 组（main 顶部已是 09-07/08/09 记录）、删除游离标题；推送后重跑 python-ci（workflow_dispatch；本仓 `pull_request` 触发未生效是已知问题，python-ci.yml:8 注释）。

**验证**：`ruff check` / `format --check` 绿；`pytest -m "not gpu"` 全量绿；容器布局模拟导入（`<tmp>/app/main.py` 两级深度 = `/app/app/main.py` 等价布局）`import app.main` 成功——修复前同一模拟抛 `IndexError: 3`；方式 A 容器实测待 Docker Desktop 就绪后补（docker-build CI 不覆盖运行期导入）。

—— 执行人：LHRCarrier


## 2026-09-04 方式 B 三连排障 · 代码改动全过程记录（diff 级，供审 PR 回溯）

> 本日方式 B 联调连续三个故障（①Java 启动退出码 1 ②Python ASR 500 ③评分恒 90/86），修复涉及 **4 个仓库文件 + 2 个 BUG 实测归档**。本篇按「动机 → 方案取舍 → 最终 diff → 验证」完整记录每一步（三个故障的复现/根因见各自 BUG 实测文档，此处不再重复）。**09-04 深夜复审整改：容器布局 P0 + 「compose 注入 HF 三件套」失实表述更正，详见文末记录。**

### 一、改动总览（均已提交本 PR；容器布局防护为复审后追加修复）

| 文件 | 类型 | 动机 |
|---|---|---|
| `services/python/app/main.py` | 代码（+13 行） | ②ASR 500：HF 缓存环境默认值 |
| `scripts/dev-up.ps1` | 脚本（+7 行） | ②同上：一键起停显式注入同款变量 |
| `README.md` | 文档（+2 FAQ 行、1 行注释修正） | ①②③的 FAQ 落位 + 过时迁移注释 |
| `services/java/.env.example` | 文档/示例（±6 行） | ①残留占位值对齐 + 方式 A/B 说明 |
| `worklog/BUG实测/方式B-Java启动-DB密码失配.md` | 新增归档 | ①完整实测记录 |
| `worklog/BUG实测/方式B-Python-ASR-HF缓存失配.md` | 新增归档 | ②完整实测记录 |

另有 3 处 **gitignored 本地状态**（根 `.env`、`services/python/.env`、postgres 库密码），见第三节，不入库。

### 二、逐文件改动过程

#### 1. `services/python/app/main.py`（③前置修复，①②后置预防）

- **动机**：`score_item` 里 `asr.transcribe()` 是唯一无 fail-open 的环节，whisper 模型加载失败（hf_hub 1.29 走同步 httpx 联网 → huggingface 被墙 → `LocalEntryNotFoundError`）直接 500。
- **方案取舍**（三选一）：
  - 只写文档让用户手动设 `HF_HOME` → 记不住、每次联调必踩（本次就是踩了这个坑）；
  - 只改 `dev-up.ps1` → 只覆盖一键路径，IDE/裸 `uv run uvicorn` 仍会炸；
  - **进程入口 `os.environ.setdefault`（采纳）** → 覆盖一切启动方式，且 `setdefault` 尊重用户进程已显式设置的环境变量（不抢权）；
- **细节**：
  - 位置放在 `logger` 初始化前、任何 `huggingface_hub`/`faster_whisper` 导入之前（hf_hub 在首次 `WhisperModel()` 时按 `os.environ` 定缓存路径，必须在那一刻之前生效）；仓库内 `faster_whisper` 仅在 `app/audio/asr.py` 函数内延迟导入，路由导入不触发，顺序成立；
  - `_repo_root = Path(__file__).resolve().parents[3]`：`app/main.py` → parents[0]=app、[1]=services/python、[2]=services、[3]=仓库根，未硬编码绝对路径，团队其他机器克隆后自动成立；**复审修正（09-04 深夜）**：该写法在容器布局（Dockerfile `WORKDIR /app` + `COPY . .` → `/app/app/main.py`，parents 只有 3 级）越界抛 `IndexError` → 容器导入即崩（方式 A 全栈不可用），已改为 `try/except IndexError` 布局感知——本地布局注入 `HF_HOME`/`HF_HUB_OFFLINE`；容器布局不注入（维持 HF 默认缓存路径 = docs/06 §8 hf-cache 卷约定，不破坏首次下载流程），仅 `HF_HUB_DISABLE_XET=1`（docs/18：xet 401 绕过）；
  - 三变量口径改为：**方式 B 本地 = 仓库 `data/models` + offline=1**；**容器 = `hf-cache:/root/.cache/huggingface` 卷 + 默认路径（compose 当前未注入任何 HF_* 变量、未挂载 data/models——K03 未闭合，另立整改）**。早前版本写「与容器 compose 同约定（挂载 ./data/models）」经复审确认与仓库事实不符，全仓已更正；
  - setdefault 尊重显式覆盖；
- **不改的**：未把 HF 变量加进 pydantic Settings——它们不是业务配置而是 hf_hub 的系统环境变量语义，塞进 Settings 反而造成「两个真源」。

最终 diff（复审整改后）：

```python
# HF 缓存约定（docs/06 §8：huggingface 被墙，一律本地缓存）：方式 B 本地默认走仓库
# data/models（宿主预下载的 HF 缓存结构）+ offline=1；容器（/app/app/main.py）无「仓库根」，
# 不注入 HF_HOME/HF_HUB_OFFLINE（维持 HF 默认缓存路径 = hf-cache 卷约定，docs/06 §8；compose
# 未注入 HF 变量为 K03 未闭合项，另立整改）。必须在任何 huggingface_hub / faster_whisper 导入
# 之前生效；用户进程已显式设置时尊重之 (setdefault)。未设时首次 ASR 会尝试连 huggingface.co
# → SSL/连接失败 → items/audio 500（2026-09-04 实测）。
try:
    _repo_root = Path(__file__).resolve().parents[3]
except IndexError:
    _repo_root = None  # 容器布局（WORKDIR /app）：无第四级父目录，跳过本地缓存注入
if _repo_root is not None:
    os.environ.setdefault("HF_HOME", str(_repo_root / "data" / "models"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
```

#### 2. `scripts/dev-up.ps1`

- **动机**：方式 B 一键路径**显式注入**同款变量——入口 setdefault 是「兜底默认」，脚本显式设置是「可审计的启动契约」；两者同值，无冲突；脚本负责日志落盘（`local/dev-logs/`），显式变量让排查者一眼看到 HF 约定在生效。**复审修正**：改为仅在用户未显式设置时注入（`if (-not $env:HF_HOME)`，与 main.py `setdefault` 语义一致，尊重用户覆盖）。
- **位置**：`$Root/$LogDir` 初始化之后、`Get-PortPid` 之前（进程启动前完成注入，`Start-Process` 子进程继承）。
- **diff（+7 行）**：

```powershell
# HF 缓存约定（docs/06 §8 · 方式 B 本地，2026-09-04 修复）：
# huggingface 被墙 → 一律走仓库 data/models 本地缓存（宿主预下载 faster-whisper-small）。
# 不设则首次 ASR 尝试联网下载 → 连接/SSL 失败 → /placement/items/*/audio 500。
# 用户已显式设置时尊重之（与 main.py setdefault 同语义）。
if (-not $env:HF_HOME) { $env:HF_HOME = Join-Path $Root "data\models" }
if (-not $env:HF_HUB_OFFLINE) { $env:HF_HUB_OFFLINE = "1" }
if (-not $env:HF_HUB_DISABLE_XET) { $env:HF_HUB_DISABLE_XET = "1" }
```

#### 3. `README.md`（4 处）

| 位置 | 改前 → 改后 | 动机 |
|---|---|---|
| 方式 B §3 Python 步骤 | `# 建表（schema 真源=Alembic；M2 迁移 0001+0002）` → `# 建表（schema 真源=Alembic；合并后需升到最新 revision）` | 仓库已有 0003~0005，旧注释误导「只要 0001+0002」（首轮「迁移做了没」误判即源于此） |
| FAQ（`mvn spring-boot:run` 行后） | **新增**：`启动日志含 FATAL: password authentication failed ... 退出码 1` → 指向 DB 密码失配三处同步 + BUG 实测归档 | ①的报错与「漏起依赖」症状不同，原 FAQ 行覆盖不到 |
| FAQ（「语音接口返回固定文本」行后） | **新增**：`本地 ASR 500 / LocalEntryNotFoundError / httpx 连接错误` → HF_HOME 指向 data/models + 归档 | ②的报错特征独立成行（含同步栈识别线索 httpcore `_sync`） |
| — | FAQ 引用的 BUG 实测文件名 | 两处引用分别写 `worklog/BUG实测/2026-09-04-...` 与 `worklog/BUG实测/方式B-Python-...`，命名风格不统一，已统一为不带日期（与既有 `asr词级时间戳空.md` 等一致） |

#### 4. `services/java/.env.example`（±6 行）

- **动机**：①的残留——该文件仍带旧占位符 `DB_PASSWORD=change-me-db-password`、`JWT_SECRET=change-me-please-use-64-char-random`（09-01 的「三处默认值对齐」漏了这一处），且头注释只说「compose 下由根 .env 注入」，未说明方式 B 手动导出路径。
- **diff**：头注释改写为「方式 B 按需导出（给出 `$env:` 示例）／方式 A 由 compose 注入、本文件不参与／密码三处同步」，两个值改为 `vocalverse-dev` 与 `vocalverse-dev-jwt-secret-0123456789abcdef`（与 `application.yml` 默认、compose 回退值一致）。
- **注意**：Git 提示本文件工作区 LF→CRLF 转换（仓库 `.gitattributes` 强制 LF）——提交时以 Git 规范为准即可，**不要在提交前手动转 CRLF**。

#### 5. 新增 BUG 实测归档（2 篇）

- `worklog/BUG实测/方式B-Java启动-DB密码失配.md`：①复现/根因/修复/验证/踩坑 5 条（Dialect 表象、同步口径含 Java、根 .env 是 GBK 编码、POSTGRES_PASSWORD 仅初始化生效、PG 排查三步）。
- `worklog/BUG实测/方式B-Python-ASR-HF缓存失配.md`：②复现/根因/修复/验证/踩坑 5 条（httpx 栈分同步/异步、报错文案反查 site-packages、预热吞异常、容器/本地环境契约缺口应落代码默认值、ASR 无 fail-open）。**复审整改**：文中「容器由 compose 注入 HF 三件套（挂载 ./data/models）」等表述与事实不符，已更正为「容器 = hf-cache 卷 + 默认路径（compose 未注入，K03 未闭合）」。

### 三、本地（gitignored）状态变更（不入库，仅本机）

| 对象 | 变更 | 手法 |
|---|---|---|
| 根 `.env`（GBK 编码，保留原编码） | `POSTGRES_PASSWORD`→`vocalverse-dev`；`JWT_SECRET`→`vocalverse-dev-jwt-secret-0123456789abcdef` | 936 解码→替换→写回；与备份 diff 仅 2 行，注释完好 |
| `services/python/.env`（UTF-8） | `APP_DATABASE_URL` 密码→`vocalverse-dev` + 注释同步；四组密钥从根 .env 搬运（`APP_DEEPSEEK_API_KEY`/`APP_ISE_APP_ID`/`APP_ISE_API_KEY`/`APP_ISE_API_SECRET`） | edit/脚本，值未打印未入库 |
| postgres 库 | `ALTER USER vocalverse PASSWORD 'vocalverse-dev'`（不丢数据） | docker exec + scram 实测新旧密码互斥 |

### 四、验证与门禁

| 门禁 | 结果 |
|---|---|
| `uv run ruff check app/main.py` + `format --check` | ✓ 全绿（E501 修正后复跑） |
| `uv run pytest -q`（全量） | ✓ **265 passed**（17s；1 条无关 StarletteDeprecationWarning） |
| Python 端到端（:8001 隔离实例，edge-tts 真实语音） | ✓ `code=0`：转写逐词正确；**真实评分** pron=100.0 / flu=98.08 / completeness=100.0 / gram=100（ISE+DeepSeek 连通；此前 Fake 恒 90/86） |
| Java 端到端（`mvn spring-boot:run`） | ✓ `Started VocalverseApplication in 8.505s`；`/actuator/health`=UP；`/api/v1/ping` code=0 |
| 容器布局模拟导入（复审整改后补验：`<tmp>/app/main.py` 两级深度，= `/app/app/main.py` 等价） | ✓ `import app.main` 成功（修复前 `IndexError: 3`） |
| 清理 | ✓ 测试 attempts 已 DELETE；验证音频/日志文件已删；:8001 已停 |

### 五、待办 / 未决

1. **8000 现行进程未重启**（PID 21316，我方可读但无终止权限）：密钥/HF 变更需重启 uvicorn 生效，待成员在本人终端 `Ctrl+C` 后 `uv run uvicorn app.main:app --reload --port 8000`（或 `dev-up.ps1 stop; start`）。
2. **提交拆分**（已执行，按仓库纪律代码/文档分开）：`fix(py): 方式B HF 缓存默认值…`（`app/main.py`）、`chore(dev): dev-up.ps1 显式注入 HF 三变量`、`docs: 方式B 排障归档与 FAQ…`（README + worklog 三处）、`chore(java): .env.example 占位值对齐约定…`；**09-04 深夜复审整改追加**：容器布局防护 + 失实表述全仓更正（见文末记录）。
3. **FAQ 引用文件名风格**：已统一为不带头日期（与既有 `asr词级时间戳空.md` 等命名一致）；README 引用已改 `方式B-Java启动-DB密码失配.md`。
4. **根 `.env` 编码**：本机为 GBK（用户历史）；后续编辑务必按原编码（936）读写，UTF-8 工具会毁中文注释（已在归档踩坑 3 记录）。
5. **容器侧 HF 缓存未闭合（K03）**：compose 无 `hf-cache` 卷、无 `HF_*` 变量注入——容器内模型加载仍回退默认路径（无本地缓存时首次联网下载，被墙即 500）；建议后续独立 PR 补齐 compose（volume + XET 变量），本 PR 只保证不更坏、不误导。

—— 执行人：Faust-sudo


## 2026-09-04 入学测试评分恒为 90/86 → 密钥填错文件（根 .env vs services/python/.env）

**现象**：密钥已填、三端重启后入学测试仍恒 发音90/流利86/语法—（Fake 桩常数；`stubs.py L43` 硬编码 `ScoreResult(pron=90.0, flu=86.0)`，`FakeLLM` 输出非 JSON → grammar fail-open None）。

**根因**：方式 B 的 Python 进程读的是 **`services/python/.env`**（`config.py:17` `env_file=(".env", ".env.local")` 按 CWD 相对解析；启动约定 CWD=services/python），而密钥被填进了**根 `.env`**（那是 docker-compose/方式 A 注入用）→ `get_scorer_client`/`get_llm_client` 判空走 Fake。另外 `uvicorn --reload` **不监听 .env**——就算改对文件不重启也无效。

**处置**：根 `.env` → `services/python/.env` 同步四键（APP_DEEPSEEK_API_KEY / APP_ISE_APP_ID / APP_ISE_API_KEY / APP_ISE_API_SECRET；全程脚本搬运、日志不打印值）；隔离实例 :8001 实测真实管线 ✓ `pron=100.0, flu=98.08, completeness=100.0, gram=100`（edge-tts 合成语音，ISE/DeepSeek 均连通）；测试 attempt 已清理。

**教训**：① .env 按「哪个进程读它」分账——compose 读根 .env、方式 B 读 services/{py,java}/.env，填错位置 = 配置不生效且无任何日志；② `--reload` 只管 .py，.env 变更必须硬重启；③ 「恒定评分」先验桩/真（`FakeScorerClient` 常数即 90/86），再谈算法——README FAQ「语音接口返回固定文本」已写此约定。

—— 执行人：Faust-sudo


## 2026-09-04 入学测试录音 500 排障 · 方式 B 缺 HF 缓存约定（whisper 模型加载失败）

**现象**：`POST /api/v1/placement/items/1/audio` → 500；uvicorn 日志出现 httpx **同步**客户端栈（`httpcore/_sync` + `default.py::HTTPTransport`）与截断文案「…local disk. Please check your internet connection and try again.」。

**根因**：方式 B 本地 uvicorn 无 `HF_HOME`/`HF_HUB_OFFLINE` 注入（容器侧约定本为 `hf-cache:/root/.cache/huggingface` 命名卷承载默认缓存路径，docs/06 §8；但 **compose 当前未注入任何 HF_* 变量、也无 hf-cache 卷——K03 未闭合**，方式 B 更没有任何等价注入）→ `faster-whisper` 的模型在默认缓存（`%USERPROFILE%\.cache\huggingface`）里**没有**（只有 Qwen），而仓库 `data/models/hub` 里 **faster-whisper-small 完整存在** → huggingface_hub 1.29 试图联网下载 → huggingface.co 被墙（SSL `CERTIFICATE_VERIFY_FAILED`）→ `LocalEntryNotFoundError`（链出 httpx `ConnectError`）→ `score_item` 的 `asr.transcribe()` **无 try/except** → 500。与 DB/迁移/Java 无关；`_prewarm_asr` 预热失败只打 WARN 不阻塞，故服务照常启动、首请求才炸。

**修复**（docs/06 §8 本地缓存约定）：
1. `app/main.py`：进程入口 `os.environ.setdefault` `HF_HOME=<仓库>/data/models` + `HF_HUB_OFFLINE=1` + `HF_HUB_DISABLE_XET=1`（任何 hf 导入前生效；尊重显式覆盖；**复审整改**：容器布局自动跳过 `HF_HOME`/`HF_HUB_OFFLINE`——`parents[3]` 越界即视为容器布局，维持 hf-cache 卷默认路径，避免破坏容器首次下载流程）；
2. `scripts/dev-up.ps1`：启动 Python 显式注入同款三变量（仅在未显式设置时，尊重用户覆盖）；
3. `README.md` FAQ 新增该场景行，§3 迁移注释改为「升到最新 revision」。

**验证**（无 HF 环境变量冷起 :8001 隔离实例）：readyz OK → edge-tts 合成语音提交 → `code=0`，转写逐词正确、pron 90/flu 86/wpm 203.7；测试 attempt 已清理。复审后补：容器布局模拟导入 ✓（修复前 IndexError: 3）。详见 `worklog/BUG实测/方式B-Python-ASR-HF缓存失配.md`（踩坑 5 条：httpx 栈分同步/异步定位第三方库、报错文案反查 site-packages、预热吞异常、容器/本地环境变量契约缺口应落代码默认值、ASR 无 fail-open）。

—— 执行人：Faust-sudo


## 2026-09-04 方式 B（`mvn spring-boot:run`）Java 启动失败排障 · 三端 DB 密码对齐

**现象**：`Process terminated with exit code: 1`，`-e` 可见 `FATAL: password authentication failed for user "vocalverse"`；Hibernate 届时只抛表象 `Unable to determine Dialect without JDBC metadata`（SQL 异常是 WARN 级）。

**根因**：本机 postgres 容器 09-01 用根 `.env` 的 **`change-me-db-password`**（旧 `.env.example` 占位符）初始化；`services/python/.env` 已同步为同一值所以 Python 能连；唯独 Java 走 `application.yml` 默认 `vocalverse-dev`（shell 无 `DB_PASSWORD`）→ 建连被拒 → 启动即退。**与合并组长代码 / 迁移无关**：实测 `alembic_version=0005`（head）+ 26 表，已是最新；迁移缺失的症状是「启动成功、请求 500」，不是启动即退。

**修复**（三端对齐仓库约定 `vocalverse-dev`，零数据丢失）：
1. `ALTER USER vocalverse PASSWORD 'vocalverse-dev'`（scram 实测新旧密码互斥 ✓）；
2. 根 `.env`：`POSTGRES_PASSWORD` 对齐；顺带 `JWT_SECRET` 占位符 `change-me-please-use-64-char-random` → `vocalverse-dev-jwt-secret-0123456789abcdef`（对齐 `.env.example` 与 Java `application.yml` 默认；compose 未注入 `JWT_SECRET`，Java 走默认值——显式一致可防未来 compose 注入时验签失配）；
3. `services/python/.env`：`APP_DATABASE_URL` 密码同步 + 注释更新；
4. `services/java/.env.example`：残留占位值对齐并补「方式 B 手动导出 / compose 注入」说明；
5. README FAQ 增「`password authentication failed` + 退出码 1」独立行（与「漏起依赖」区分）。

**验证**：`mvn spring-boot:run` → `Started VocalverseApplication in 8.505s`；`/actuator/health`=UP；`/api/v1/ping` code=0；DemoSeeder 就绪。详见 `worklog/BUG实测/方式B-Java启动-DB密码失配.md`（含踩坑 5 条：Dialect 表象、密码同步口径含 Java、根 .env 是 GBK 编码、`POSTGRES_PASSWORD` 仅初始化生效、PG 排查三步次序）。

—— 执行人：Faust-sudo

## 2026-09-04 影子跟读联调台：录音完成 → 试听自己读的 → 确认提交/重录

- 需求（组员复测反馈「方便测试」）：录完先听自己的跟读再提交，避免闭眼提交后才发现录歪；
- 实现：`ShadowPreview.vue` 录音停止**不再自动提交**——本地 ObjectURL 试听条（原生 audio 控件）+「提交评分 / 重录」按钮；换句/换素材/卸载时 revoke 防泄漏；VoiceRecorder 的 cancel 路径不触发 onStop，仅真实停止才生成试听；
- 验证：lint（0 warning）/typecheck/vitest 19/build 全绿；dev 模块 transform 200。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 评分 DoD ③：META content/vocab 语义子分（LLM 判定 · 进展示不进总分）

打分「链路完成」DoD 剩余三项之③（④ 之后收尾）：

- **契约增量（docs/14 §3.4 + docs/26 同步）**：`[-META-]` 增 `content:{score,note}`（内容相关度/充实度）与 `vocab:{score,note}`（词汇多样性）——**口径 docs/07 Q38 拍板 C 落地**：LLM 判定、进报告展示、**不进量化总分**（S=0.4·发音+0.3·语法+0.3·流利度 不变），避免「语义对错混入口语技能分」；
- **改动面**：`meta.py`（properties content/vocab + render_meta 扩展，默认 None 不破坏既有调用；**防御：模型输出裸数字/字符串 → None 不伪造**）；`context_builder` system 契约行加字段描述（**system 仍逐字静态**——字段说明属契约正文，docs/26 ⑤ 不变）；`meta_executor` 补偿 prompt（_COMPENSATE_SYSTEM + user 注记）同步；`events.MetaBlock` + SSE 手写类型（sse-types.ts）加 content/vocab；orchestrator（MetaBlock 透出 + assistant 消息 meta 落 content/vocab）；`service.complete_session` 新增 `metrics.semantic`（聚合均分+轮次）；`stubs.FakeLLM` 的 META 带 88/84 子分（全链路可断言）；
- **前端**：ReportView 评分卡下方加「内容相关度 / 词汇多样性」两卡（标注不含总分；无数据隐藏）；
- **验证**：pytest **180 passed**（+3：META 解析与防御、补偿 prompt 形状、补偿透传；全链路测试断言 SSE meta_block 带 content/vocab + 报告 semantic={content:88.0/1轮, vocab:84.0/1轮}）+ ruff 全绿；前端 lint/typecheck/vitest 19/build 全绿；
- **踩坑**：① docs/14 契约行与 system 契约行是我在一天内第三次改「契约文本」——每次都要同时对照 docs/14、docs/26、meta.py 文档字符串与 _STATIC_TEMPLATE 四处，改一处漏一处（本次已四同步）；② 复用了"改 worklog 用标题行做锚点"的老毛病，两次吞掉下一条目标题——本次已逐处核对。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 评分 DoD ④：影子跟读/朗读编排分支（ISE 主场 · 三维评分 + 联调测试台）

打分「链路完成」DoD 剩余三项之④（顺序：④→③）：

- **素材基础盘点**：`shadow_materials` 表/迁移 0003/SessionCheck kind=shadow/`AttemptKinds.SHADOW_SPEECH`/推荐链路（type=shadow）**均已存在**，缺的只是生产编排；`seed_recommend` 补了 L2/L3/L4 三条演示素材（text_content/wpm 120/145/165，全仓此前无素材时 recommend_shadow 恒空——本次执行 seed 后验证 count=3）；
- **评分口径定版（docs/06 §9.3）**：三维 = `0.4·发音(ISE accuracy) + 0.3·语速匹配 + 0.3·停顿密度`；语速匹配（用户 wpm vs 素材原声 wpm）分段 ≤10%→95/≤20%→85/≤35%→70/≤50%→55/其余 40；停顿密度（pause_ratio）≤5%→95/≤10%→85/≤20%→70/≤35%→55/其余 40；素材缺 wpm → 该维缺省按剩余权重归一；**重音落点/连读识别留待 M3 前端韵律引擎（docs/24 ①），登记 P2 不伪造**；
- **新模块** `app/practice/shadow.py`（分句/分段打分/加权归一/规则教练笔记——LLM 不参与，无 META 泄漏面）；`_shadow_turn` 编排：start（出句+TTS 示范 AudioChunk，不推进）→ normal（ASR 特征 + ISE 题卡参考 → 三维分 → attempt(kind=shadow_speech, details.shadow) → 逐句推进 → 末句 complete_session）；
- **接入**：`create_session` kind=shadow + `shadow_material_id`（SessionCreate 契约 + 快照刷新，diff 仅该字段）；**顺带修一个潜伏 bug**：`create_session` 的 assembled 引用未初始化 `scenario`（defense 建会话同样踩 UnboundLocalError，只是此前无测试覆盖——本次 shadow 测试立刻抓出）；
- **联调测试页** `/preview/shadow`（ShadowPreview.vue + registry/router；后端 test-only `shadow_preview.py`：materials/tts（原始字节示范）/analyze，`include_in_schema=False`、默认关闭 `APP_SHADOW_PREVIEW_ENABLED`（本地已开，生产禁止）、删除清单文件尾）；
- **验证**：pytest **177 passed**（+24：纯函数分段/权重归一/教练档位、start→评分→收尾→报告全链路（fake 数值：wpm=145.83→speed 95、pause 0.3646→40、pron 90→overall 76）、素材 404/缺音频 422、测试台 404+openapi 零路径、analyze Fake 三维）；ruff 全绿；前端 lint/typecheck/vitest 19/build 绿（dist 无 Shadow chunk）；真链路（经 Vite 代理）：materials=3、analyze（ref-3 音频 × 面试题卡句——故意不相配 → pron 7.9/speed 85/pause 70/overall 50，coach "Slow down..."，**口径合理**：错题卡低发音分）；
- **踩坑**：① PowerShell `$PID` 是保留自动变量，`dev-up.ps1` stop 循环变量撞名 → 服务杀不掉（已改 `$procId`）；② 测试里 SSE JSON 断言别忘了冒号后有空格（`"conclude": false`），与旧代码无空格格式不同。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 联调台实测英文歌：链路扛住 + ISE 口语口径守卫（超长降级原因）

- **组员传整曲《阿云嘎 HOY-MIX-Regression.ogg》（3:56 / 236.71s / 9580KB）实测**：试听/转写 179 词/特征全出无崩溃——但数字对唱歌无语义（41.3s「停顿」= 器乐段、2.72s「词」= DTW 拉长，whisper 词级时间戳是口语标定）；ISE 因整篇歌词超长被拒/失败，页面却显示「未评分」，误导；
- **修复**：`analyze` 增口语口径守卫 —— 音频 >60s（`max_speech_seconds`）→ `audio_too_long`；参考 >300 字符（`MAX_ISE_REF_CHARS`）→ `reference_too_long`；ISE 异常 → `ise_failed`；`score_ref` 保留以表明「已触发评分」；测试台不盲等 ISE；
- **页面**：ISE 卡黄色提示降级原因；停顿标注对 ≥3s 超长间隙改「可能为器乐段/无词段，非口语停顿」；
- **口径记录**：唱歌长音频的评分走 M3 音准/节奏链路（sing_attempts/pyin/LRC DTW，docs/singing 22），本测试台只服务口语；这正好实证 docs/19 P0-5「流利度/发音口径不适配唱歌」的一面；
- **验证**：pytest **153 passed** + ruff 全绿（+2 守卫测试：reference_too_long / 236.7s audio_too_long）；前端 lint/typecheck/vitest 19/build 全绿；真链路：419 字符参考 → `reference_too_long(419 > 300 字符...)`，ref-3 正常路径 overall=90.82 无 error。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 联调台加「选中文件即试听」（本地回放，不上传）

- 需求（组员反馈「方便测试」）：选完音频立刻能听，再决定是否分析；
- 实现：`FluencyPreview.vue` 选择后 `URL.createObjectURL` 生成预览地址 + 原生 `<audio controls>`（显示文件名·大小；更换/卸载时 revoke 防泄漏）——纯浏览器本地回放，不经过后端；
- 验证：lint/typecheck/vitest 19/build 全绿；dev 模块 transform 200。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 测试台 ISE 口径修正（转写对转写开关）+ 开发服务脱离终端起停

- **缘由（组长提问「为什么流利度要有参考文本」）**：区分两种「流利度」——① 时间戳特征（wpm/停顿，纯音频+转写，**无需参考**）；② ISE 流利度分（评测引擎按「音频 vs 给定文本」对齐，**必须有参考**；生产对话口径 = ASR 转写当参考「转写对转写」，朗读/影子跟读才有题卡原文）。
- **修正**：测试台加「用 ASR 转写作为参考（转写对转写）」勾选**默认开**；后端 `/analyze` 增 `use_transcript_ref` 表单参数（手动 reference 优先），响应增 `score_ref`（manual/transcript/null）供页面标注；不填参考也不再是空评分——实测 ref-3.wav：score_ref=transcript / **overall=90.82 / flu=95.02 / pron=89.39**；未勾选时 score_ref=null（页面提示如何开启）。测试 +2 条（转写对转写、手动参考优先），pytest **151 passed** + ruff 全绿；前端 lint/typecheck/vitest 19/build 全绿。
- **开发服务起停重构**：uvicorn/mvn/pnpm 作为终端批次任务跑时，关终端弹「Terminate batch job (Y/N)?」且服务随会话死（断网重启后三端全掉）。新增 `scripts/dev-up.ps1`（start/status/stop，**Start-Process 独立进程** + 日志 `local/dev-logs/`；pwsh 7 执行），README 方式 B 增一键起停说明；已验证三端健康（python readyz / java ping / vite 200）。
- **踩坑**：vite 默认绑 `localhost`（::1），脚本健康探测用 `127.0.0.1` 会 false——已改 localhost（与之前的 5173 访问同坑）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 ② 联调发现 BUG：ASR 词级时间戳恒空（生成器二次迭代）已修 + 归档

- **现象**：`/preview/fluency` 上传 ref-2.wav（6.12s）→ 转写文本正确但 words=0、wpm/停顿全零；直接 `WhisperModel.transcribe(word_timestamps=True)` × 同文件却出 11 词——矩阵锁定封装层；
- **根因**：faster-whisper `transcribe()` 返回**生成器**；`transcribe_sync` 先「拉平文本」（`''.join` 消费殆尽）再「遍历取词」→ 第二次迭代恒空；**旧代码 `ASRResult.segments` 亦恒空**（无消费方、无断言，自 M2 静默存在；直调测试因恰好 `list()` 物化而正常，极具迷惑性）；
- **修复**：解包后 `segments = list(segments)` 物化一次 + 注释生成器契约（`app/audio/asr.py`）；回归测试 `tests/test_asr_words.py`（假模型返回生成器、断言 word_timestamps 透传+三处消费一致）——**删掉物化行必红（实测 1 failed）→ 恢复绿**；全量 **149 passed** + ruff 全绿；
- **真链路复验**（重启 :8000）：words=**11** / wpm=**124.06** / pause=**2** / max_pause=**0.96s** / ISE overall=**84.94** flu=89.66 pron=82.01；
- 归档：`worklog/BUG实测/asr词级时间戳空.md`（复现/根因/修复/验证/踩坑——**faster-whisper 生成器契约：要迭代两次必须先 list()**）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-04 评分 DoD ②：流利度时间戳特征（ASR 词级时间戳 → wpm/停顿 → 落库/报告/联调测试台）

打分「链路完成」DoD 剩余三项之②（2026-09-03 工作日志登记）：

- **特征模块**：`app/audio/fluency.py` 纯函数 `compute_fluency_features`（**恒定键集、坏数据全零兜底、永不抛异常**）——`wpm`（词数/有效说话段分钟，**排除录音首尾静默**）、`articulation_rate`（去停顿纯发音速率）、停顿统计（**相邻词间隙 ≥0.5s 计一次**、≥1.0s 长停顿；仅词间不记首尾静默）、`pause_ratio`；口径 docs/07 Q30（ISE fluency 仍为权威流利度分，本模块只出辅助）；
- **数据源**：faster-whisper `transcribe(..., word_timestamps=True)` → `ASRResult` 增 `words[{word,start,end,probability}]` + `duration`（契约变更 → `scripts/refresh-openapi.ps1` 刷新 python-openapi.json + `pnpm gen:api` 生成类型，diff 仅 ASRResult 两字段）；`FakeASRClient` 补同构词表（含 1.05s 停顿，测试可断言精确值）；
- **接入**：对话链路（orchestrator `_dialog_turn`：attempt 写 `wpm` + `details.fluency` + user 消息 meta 带 wpm/pause_count）与入学测试链路（placement `score_item`：同写 + 响应补 wpm）——**修复前 `attempts.wpm` 列恒 NULL**（列自 0001 迁移就存在但从未写入）；
- **报告**：`service.py` report `metrics.attempts[]` 增 `wpm` + `fluency_features`（前端 `ReportView` 流利度卡下显示「语速 ≈ N 词/分 · 停顿 ≈ M 次/轮」，仅无数据时隐藏）；
- **联调测试页（新功能固件规范 · 预览机制）**：前端 `views/preview/FluencyPreview.vue`（/preview/fluency，dev-only 生产零体积，已验 dist 无 chunk）+ registry/router 登记；后端 test-only `routes/fluency_preview.py`（POST /api/v1/fluency-preview/analyze：真 ASR→特征→可选真 ISE→与 attempts/report 同构演示载荷），`include_in_schema=False`（契约快照零 diff）、无表无迁移、默认关闭（`APP_FLUENCY_PREVIEW_ENABLED`，本地 .env 已开，生产禁止开启）、删除清单见文件尾注释；页内报告样张按 **lieflat-charts 报告模式 R09 × PORCELAIN** 色值呈现（与 `assets/lieflat/vv-learning-report.html` 同 token）；
- **验证**：pytest **148 passed**（新增 test_fluency 10 条纯函数 / fluency-preview 3 条（默认 404 + openapi 无该路径）/ asr 契约词表 1 条 / 对话→attempt→complete→report 全链路 1 条：wpm=145.83、pause=1、long=1）+ ruff check/format 全绿；前端 lint/typecheck/vitest 19 passed/build 绿；真链路冒烟（重启 :8000 后 `analyze` + 合成正弦 WAV）code=0 —— 正弦波 whisper 出 0 词级时间戳时特征全零兜底不崩；
- **踩坑**：① `refresh-openapi.ps1` 被 Windows PowerShell 5.1 以 ANSI 解析报语法错 → 必须用 pwsh 7 执行；② 执行刷新会把 Java 快照重写成压缩单行（live springdoc 未开 pretty-print，契约语义相同但 2343 行噪音 diff）→ 本次 Java 零改动，已 `git checkout` 恢复入库 pretty 版；③ `zip() strict` ruff B905、`import.meta` 等老坑之外，本次 vue-tsc build 门禁抓住 `w.gap` 可能 null（lint/typecheck 不报，build 报——与踩坑③同型「门禁分工」）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 ISE 批量对照实证：SpeechOcean762 人工标注 vs ISE（r=0.81，分档单调）

新增 `scripts/poc/ise_validation.py`（gold 对照脚本，本地素材 `local/english-audio/01-speechocean762/` 驱动，gitignored）：按 gold 总分（0-10）抽低/中/高各 30 句（固定种子 42 可复现）→ 逐句真 ISE 评分 → TSV 对比表。

**实测（90/90 成功，0 失败）**：
- pearson(gold_total → ise_overall) = **0.810**（强相关，发音评测准确性成立）；
- gold_acc → ise_pron = 0.730；gold_flu → ise_flu = 0.797；
- 各档 ISE overall 均值：low=**57.17** / mid=**80.39** / high=**88.27** —— 三档完全单调，可作为"水平分档"的实证依据（对应 A2/B1+/C1 近似的语音侧分档）。结论：**ISE 接入可靠性（链路）+ 准确性（对标）双双达标**；打分"链路完成"的 DoD 第①条达成（剩余：流利度时间戳特征、META content/vocab 语义子分、影子跟读编排分支——另排）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 讯飞 ISE 真链路接入：旧 HTTP 接口已下线 → 流式版重写（真调用全通）

组长提供 ISE 密钥（APPID/APIKey/APISecret，已写入 gitignored `services/python/.env` 与根 `.env`，不入库）。接入过程（真调用逐级排障）：

- **HTTP 版接口已下线**：`https://ise-api.xfyun.cn/v2/open-ise`（POST form + X-Appid/X-CheckSum MD5 签名）返回 `not found`/403——官方现行文档为**流式版 WebSocket**（`wss://ise-api.xfyun.cn/v2/open-ise`），据此整体重写 `ise.py`；
- **踩坑链（每级有官方文档依据）**：① WebSocket 握手 401 → url 查询参数通用鉴权（authorization/date/host，HMAC-SHA256，`host:…\ndate:…\nGET /v2/open-ise HTTP/1.1`）；② 每帧 `data.data`（base64）**≤26000 字符**（10163，PCM 每帧 ≤~19KB）；③ **business 必须每帧携带**、common 仅首帧；cmd 按阶段切换：参数帧 `cmd=ssb`（data.status=0）→ 音频帧 `cmd=auw`+`aus=1/2/4`（status=1/1/2，末帧带最后音频块）；每帧全带 business 曾致 `10222 DeadlineExceeded`，仅首帧带则 `30002 cmd needed`；④ 业务参数 `aue` **默认是讯飞定制 speex**，裸 PCM 必须显式 `aue=raw`（40007 SRecWrite）；⑤ 结果帧 `data.data` = **base64(XML)** 而非 JSON；⑥ 文本需 UTF8 BOM 头（`\uFEFF`+text）；⑦ 多维度分需 `rst=entirety`+`ise_unite=1`+`extra_ability=multi_dimension`，真实 XML 里 **sentence 层只有 accuracy_score/fluency_score/standard_score/total_score，integrity_score 只在 read_chapter 层** → 解析器做 chapter 回退；⑧ `score()` 曾漏包 `ScoreResult`（返回 dict）已修。
- **音频转码**：ISE 只收 16k 单声道 s16le 裸 PCM → `_to_pcm16`（ffmpeg）预处理（编排器传的是原始 WebM 字节）；本机无 ffmpeg → `_ffmpeg_bin` 增加 **imageio-ffmpeg 自带二进制回退**（`uv pip install imageio-ffmpeg`，README 登记的免管理员路径）+ PATH/env 优先。
- **验证**：① 单测 5 条（转码/分帧/真实 XML 解析/降级），**pytest 132 passed** + ruff 全绿；② 真调用（Windows SAPI 离线 TTS 生成测试音频，规避 edge-tts 偶发 DNS）→ **overall=90.90 / pron=92.59 / flu=87.70 / completeness=100.00 / 词级细评 9 条**；③ 服务端 `/api/v1/score` 走真评分器 → code=0 同分数，全链路通。
- **边界说明**：当前对话场景以 ASR 转写作为 reference（"转写对转写"，近似发音对齐）；ISE 的真正价值在**有题卡场景**（影子跟读/朗读/M3 唱歌，`category=read_sentence` 已支持，自由题 `category=topic` 可扩展）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 预览测试页机制统一修复：Agent Lab 404 根因 + Demo↔预览画廊双向通道

- **BUG1 · Agent Lab 测试台 HTTP 404**（以截图为准，用户口中 401 实为 404）：根因 = `agent_lab_enabled` 默认 False 且本地 `.env` 未设置 → 路由未注册（符合 docs/26 §8 约束：默认关闭、生产禁止开启）；修复 = 本地 gitignored `services/python/.env` 与根 `.env` 追加 `APP_AGENT_LAB_ENABLED=true`（带「生产禁止开启」注释；不提交、不进 CI、生产零暴露不变）。
- **BUG2 · /preview 画廊不可达且易跳出**：进入预览画廊只能手输路由，测试中误点「真实布局」模式的 TopNav 就回到 demo 应用；修复 = ① `DemoView.vue` 加 DEV-only 面板（`v-if="isDev"`，`isDev = import.meta.env.DEV` 生产折叠不渲染、不进用户导航）：「进入预览画廊」「直达 Agent Lab 测试台」双入口；② `PreviewLayout.vue` 画廊侧栏顶部加「← 回到骨架 Demo」、布局模拟模式浮动条加「回到 Demo」→ Demo 与测试页**双向唯一通道**，任何测试场景下都能一键回画廊/回 Demo。
- **踩坑**：① 8000 被 uvicorn `--reload` 的**孤儿 worker** 占用——父进程已死，netstat 显示的 PID 31736 是已消失的父进程（taskkill 必失败：找不到进程），真 socket 由子进程 34108（`multiprocessing spawn_main`）持有，杀子进程才释放端口；② 本地 `.env` 开启开关后 **pytest 本地必红**：`test_agent_lab_disabled_returns_404` 经 pydantic-settings 读取 `.env` 导致路由被注册 → 已在 `tests/conftest.py` 钉回 `APP_AGENT_LAB_ENABLED=false`（env 优先级高于 .env；CI 无 .env 行为不变）；③ `import.meta` 不能出现在 SFC 模板表达式（模板按 script 解析 → `vite:vue` 报错）——必须在 `<script setup>` 取常量；该错误 lint/typecheck 均不报，**build 门禁报**（已实测红→绿）。
- **验证**：① 后端重启（.venv uvicorn 8000，托管后台任务）后 readyz 200 + `POST /api/v1/agent-lab/turn` 真跑 DeepSeek 单轮 → envelope `code 0`（404→200 端到端）；② pytest **124 passed**（含默认关闭断言）+ ruff check / format 全绿（未改后端业务代码，agent-lab 本就 `include_in_schema=False` → 契约快照零 diff）；③ 前端 lint / typecheck / vitest 18 passed / build 绿（生产 dist 无 preview 残留）；④ 已起 dev 环境供复验：后端 8000 + 前端 5173。
- **BUG3 · 登录页报 `Unexpected end of JSON input`**：Java 服务未启动（8080 无监听，用户停服时只重启了 Python）→ Vite `/manage` 代理返回空体 5xx → `resp.json()` 抛 SyntaxError，页面只显示晦涩的 JSON 解析错误。修复 = ① 重启 Java（`mvn spring-boot:run`，JAVA_HOME 已对齐 Temurin 21；`POST /auth/login` 经代理验证 200/code 0/userId 1）；② `api/client.ts` `request()` 空体/非 JSON 改为抛 `ApiError`（如「Java（登录/管理端）服务不可达（HTTP 500，`/manage/auth/login`）——请确认对应后端已启动」）+ 补单测（修复前该测试必红：抛 SyntaxError），vitest 19 passed。
- **BUG4 · 单轮结果显示 `[object Object]`、user 卡片空白**：根因 = `/turn` 把 `build_context_for_display()` 的成果 `{system: str, user: str}` **再包了一层** → `data.system` 变成 `{system,user}` 对象（NCode 渲染 [object Object]），`data.user` 根本不存在（卡片空白）。修复 = 展示载荷扁平化 `{**display, "result": ...}`（前端本就按字符串渲染原文，无需改前端）+ 回归单测 `test_display_payload_is_flat_text`（修复前该断言必红）。另记：reply 尾部偶见 `[`（如 `...today? [`）为**模型侧多余输出**（正文末尾多写 `[` 后才写 `[-META-]`），META 抽取不受影响（meta_ok=True / coach_note / grammar / hits 皆正常）——先记录不干预（POC 语义），如需净化可在 splitter 加「marker 前仅剩 `[` 行则丢弃」的小规则。
- **BUG5 · 冒烟连跑五轮：reply 尾部全带 `[` + 末轮 conclude=false**：① reply 尾 `[` 根因 = `context_builder` 模板 `[{marker}]` 渲染成 `[[-META-]]`——模型逐字照抄：外层 `[` 落进正文（每轮 reply 尾多一个 `[`，你截图 5/5 全中）、外层 `]` 落在 meta 尾段靠兜底正则吞掉（META 仍解析，掩盖了契约偏差）；契约行应为裸 `[-META-]`（meta.py 文档同款）→ 已改 + 回归单测（断言无 `[[-META-]]`，修复前必红）；② 末轮 conclude=false 根因 = `/turns` 全轮共用表单 `concluded_by_turn`（默认 False）→ 冒烟第 5 轮上下文永远「Turn limit reached: False」→ conclude 必 false；已改为 POC 冒烟同款 `_effective_by_turn`（**末轮自动 True**；勾选保持全轮 True）+ 单测 + 页面说明（连跑冒烟末轮自动注入，无需勾选）。**验证**：后端重启后重跑 5 轮冒烟——reply 全部无 `[`、第 5 轮 conclude=**True**、补偿后 META 100%、tokens 1706p/391c；**观察项**：本轮 META 直出 1/5（补偿 4/5，补偿率 80% 偏离 <50% 目标）——docs/26 §9 观察带 40~75%，n=5 样本小且上一轮直出 4/5，先记录、多跑几轮看分布；若持续走高按 §11.4 顺序查契约/补偿 prompt。
- **BUG6 · 单轮卡片 system `[object Object]`（与 BUG4 同因，page 未刷新）**：5 轮跑完截图里 system/user 卡仍是**修复前的旧结果**（本回合结果 1233ms 与上轮完全相同）——连跑 `/turns` 不更新单轮卡，需重跑「运行单轮」或刷新页面。
- **改动清单**（10 个跟踪文件）：`apps/web/src/views/DemoView.vue`、`apps/web/src/views/preview/PreviewLayout.vue`、`apps/web/src/views/preview/AgentLabPreview.vue`、`apps/web/src/api/client.ts`、`apps/web/src/api/client.test.ts`、`services/python/app/api/routes/agent_lab.py`、`services/python/app/agent/runtime/context_builder.py`、`services/python/tests/test_agent_lab.py`、`services/python/tests/agent/test_context_builder.py`、`services/python/tests/conftest.py`；`*/.env` 为 gitignored 本地开关，不提交。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 PR#26 管理员直推合入 main（组内无人审 PR，组长行政决定）

组长决定：团队成员不参与 PR 评审，**管理员方式直推 main**（`gh pr merge --admin --squash --delete-branch`，合并 commit `ee8e7ae`，PR#26 = feat(agent): LLM 框架 P0 内核（ai4u 对齐分层切片））。

- **合入前核查（AGENTS.md「先查 CI 是否真的跑过」）**：python-ci 曾 1 次红（12s 失败）——根因 `test_orchestrator_compensate.py` 的 lint 修复（F811 重复导入/F841 sc_id）在工作区未提交 + `agent_lab.py` usage 字段漏 add（**又一次路径白名单遗漏**，已补 commit `802c2ad`）；补推后 **python-ci / frontend-ci / secret-scan 全 success** 才执行合并；
- **合入内容**：LLM 框架 P0 内核 + META 契约 v2.2 + 补偿调用接线 + Agent Lab 测试台 + 摘要双轨/usage_log（迁移 0004）+ 文档群（docs/10 19+2、docs/14 v2.2、docs/24/25/26、worklog 若干）；本地全量 124 passed + ruff 全清（main 上复核通过）；
- **直推后流程说明**：后续新 PR 仍按规范开（留痕/可追溯），合入由组长按本次模式 admin squash（CI 全绿为前提）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 补齐遗漏：orchestrator × META 补偿接线（未提交缺口，红→绿验证）

组长发现工作区有未提交文件：上批提交 `git add` 只圈了 `app/agent`，**漏了 `app/practice/orchestrator.py` 的补偿接线**（import + 调用块）——已提交版本中原生链路「流式未出 META → 补偿调用」从未生效（框架冒烟通过是因为脚本自身调了 compensate，生产 orchestrator 没调）。本次补齐：

- `orchestrator._dialog_turn`：`if not meta.ok → compensate_meta(...)`（docs/26 §9.4 设计原样）；
- 补接线回归测试 `tests/agent/test_orchestrator_compensate.py`（NoMetaLLM 流 + 合法 JSON chat）：**接线前必红（coach_note=None）、接线后绿**（已实测红→绿）；
- 全量 pytest **118 passed**。

踩坑：**跨目录批次提交时，`git add` 的路径白名单不是「整个功能」**——`app/agent` 与 `app/practice` 分属两个目录，漏一个目录就是静默功能缺口；下次提交用 `git status` 全量核对而非凭记忆圈路径。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 缺口补齐：摘要双轨落库 + usage_log 用量记账（迁移 0004）+ Agent Lab 指标化

按 docs/26 §10.3 两个缺口实施（组长拍板「缺口补上」）：

- **① 会话摘要落库**：`sessions` 加 `summary/summary_updated_at/summary_failed_at` 三列（迁移 0004，对齐 ai4u agent_conversation.summary*）；`app/agent/domains/summarizer.py`（ai4u summarizer 版：近 6 条原文 + 更早 40 条窗口 + 每 4 条增量触发 + 首尾保底 300/100 + 重试 1 次 + 失败标记；回合落库后异步触发、收尾 `complete_session` 覆盖写最终总结）；**注入 ContextBuilder 的 user 尾部 `[context]`**（`Rolling summary` 行——绝不放 system，POC §9 铁证）；
- **② usage_log 用量表**：迁移 0004 新表 + `app/agent/domains/usage.py log_usage`；`llm.py` 增 `chat_with_usage/stream_rich`（usage 透传）、`stubs.FakeLLMClient.stream_rich` 同型；记账点 = turn（TurnRunner 富流）/ meta_compensate / summary / conclude 四点；
- **Agent Lab 指标化**：连跑统计加 tokens、页面顶部「指标说明」卡（怎么用/测什么/八项指标口径与阈值）；docs/26 增 §11 测试指南、§10.3 状态更新 + §10.4 摘要口径；docs/10 表清单（19+2）与写方矩阵同步；EXPECTED_TABLES + usage_log；
- **验证**：pytest **124 passed**（摘要触发/失败标记/用量落库/迁移 offline 渲染（batch 仅 downgrade）/富流用量）；ruff + format 全清；
- **踩坑**：① `may_be_summarize` 首版用 `len(recent)<=RECENT_N` 判定导致永远早退（recent 被 LIMIT 截断）→ 改总消息数判定；② `op.create_table` 用 `*_pki()` 展开 + 无显式 PK → offline `--sql` 渲染 `getitem` NotImplementedError → 对齐 0003 样式（显式 PrimaryKeyConstraint + `length=` 形参）后通过。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 协作流程固化：新功能必须带联调测试页（AGENTS.md 第 3 条）

组长拍板固化为仓库纪律：**凡开发涉及前后端联动的新功能，必须按既有预览机制提供「团队联调测试页（可删无影响）」**（AGENTS.md 工作流程第 3 条，新增「审 PR 检查项」同步）。规范要点：

- **前端**：docs/13 §8 预览工作流（`views/preview/` + `registry.ts` 一行 + `router/preview.ts` 一行；dev-only 子树，生产构建零体积零路由）；
- **后端**：test-only 接口模板（`include_in_schema=False` 契约快照零 diff、无表无迁移、`*_enabled=False` 默认不注册、生产禁止开启）；
- **可删无影响**：删除清单写入接口文件尾注释；删除后全量门禁绿 + 契约快照零 diff；
- **首例模板**：Agent Lab（PR#26）——`AgentLabPreview.vue` + `app/api/routes/agent_lab.py`，后续新页克隆改造。
- 审 PR 检查项：涉前后端联动功能 PR 缺联调测试页或删除清单 → comment 要求补。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 Agent Lab · LLM 框架测试台（团队测试用，整删无影响）

按组长要求「做一个前端测试页，专供团队测试、不影响其它代码、删除无影响」，落地 **Agent Lab**：

- **前端**：`apps/web/src/views/preview/AgentLabPreview.vue`（预览工作流 docs/13 §8：dev-only 子树，生产构建 Rollup 整枝剔除——零体积零路由；注册表 + 路由各 +1 行）。能力：单轮实验（真 LLM）/连跑 5 轮冒烟（META 直出 vs 补偿、命中、收尾、统计）/system-user 原文查看（验证「system 全静态」契约）/学习者画像只读查看；
- **后端**：`app/api/routes/agent_lab.py`（`include_in_schema=False` → OpenAPI 契约快照零 diff；无表无迁移；`agent_lab_enabled=False` 默认关闭、未开启路由不注册 → 404）；`GET /agent-lab/turn` `POST /agent-lab/turns` `GET /agent-lab/learner`；
- **验证**：pytest 117 passed（含默认关闭 404 + 契约无 agent-lab 路径 + Fake 流式 META/无 META 补偿两路径）；ruff 全清；前端 lint/typecheck/test:run/build 全绿（后台跑毕确认）；**开启方式**：本地 `APP_AGENT_LAB_ENABLED=true`（生产必须保持关闭）；
- **删除清单**（已写入 agent_lab.py 文件尾注释）：删 vue 文件 + registry/路由各 1 行 + 后端路由文件 + main.py 2 行 + config 1 行 —— 无迁移/无契约影响。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 LLM 框架 P0 · 真 Key POC 实证与 META 契约 v2.2 定案（PR#26）

组长提供 DeepSeek Key 后，框架切片首次真实现跑，60+ 次调用得出**推翻两处原设计的实证结论**（详见 docs/26 §9）：

- **POC-2（流式 META 稳定性）初判 35% < 90% FAIL**（docs/18 预案=回退两调用）→ 四臂探针定位真因：**system 内动态 context 块是 META 契约杀手**（D=0% / D1=50% / E3=0%；A/C 静态无动态=100%，流式无影响）→ 初判推倒，无需回退全两调用；
- **契约 v2.2 定案**：system 纯静态（角色/规则/conclude 指令/输出契约）；动态全部挂 **user 尾部 `[context]`**（难度/语料[仅英文，剥离 `|中文释义` 污染]/画像/已命中/收尾/摘要）；**META 缺失条件补偿调用**（temperature 0.2）→ 全链路冒烟 **5/5 = 100%**（流式直出 3 + 补偿 2），hits/conclude 全部正确；
- **缓存 POC：NO-CACHE**（预热→300s 落盘→相同前缀，hit=0）→ ⑤ 收益重定位：「前缀稳定=契约稳定工程」（100% vs 0% 的实证差距），**缓存降费不作依赖、不进答辩主张**；`llm_cache_hit.py` 保留复测；
- **防御补丁**：模型输出 `grammar:90` 裸数字（META 畸形）→ 旧代码会崩溃（冒烟实测抓出），已加 dict 防御并补测试；
- 新 POC 脚本 3 份入库（ab 探针/框架冒烟/缓存验证，无 Key skip；llm_meta_ab 四臂矩阵可复跑）；
- 门禁：pytest 114 passed / ruff 全清 / format 全清；PR#26 已 push 第 2~3 批 commit（代码+测试+docs 分开），POC 结果已回写 PR comment。

**待办**：次日 reviewer 评审合并；`docs/24 §9`（B 系列）随前端重构推进；group 拍板 retry 命中口径（docs/14 §2.1 注释 vs 实现）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 LLM 框架对齐 ai4u · 评估与实施计划（docs/26）

组长拍板方向：LLM 部分不做小改，做成组内自研 ai4u 那样的分层框架（ai4u = 组长自研 Electron+Vue3+NestJS 桌面 AI 伴侣，`F:\WorkingL\ai4u`，Agent 运行时自研分层架构）。通读 ai4u 源码与 `docs/agent/` 后输出评估：

- **结论：可以，架构模式迁移而非代码拷贝**（技术栈不同 + ai4u 无 LICENSE/含外部素材，仅借分层思想，代码全部 VocalVerse 自研；不改任何对外契约，M2 DoD 测试全绿为硬门禁）；
- **映射**：scenes（dialog/defense 门面化）→ runtime（TurnRunner 流式循环+META 泄漏门 / ContextBuilder 单一入口（并入 docs/24 ⑤⑥）/ MetaExecutor 结构化输出权威 / MessageSink 落库门面）→ domains（**学习者记忆域**：mastery/skill/attempts → 易错点检索注入 + 摘要双轨 + Auto-memory 收尾写入）/ persona（双人格模板化）→ hooks（post-session/失效/兜底）→ core（llm + usage 记账，含 prompt_cache_hit_tokens）；
- **不迁移**：proactive（主动消息）/IM/TRPG/journal/来信/RAG 知识库/多角色——产品定位不匹配；「记忆」= 学习者画像而非情感记忆；
- **分期**：P0 内核（框架壳+ContextBuilder+MetaExecutor+TurnRunner+hooks+usage ≈2.5~3.5 人日，docs/24 A 系列并入）→ P1 memory 双轨（④摘要+Auto-memory+画像升级）→ P2 persona/场景收敛；
- **RAG 无自有知识库**：VocalVerse 语料走场景绑定，不迁知识库/RAG。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-03 InternalBeyond 对比调研 · 结果核验与落地计划（docs/24）
组员在 `local/InternalBeyond对比与借鉴分析.md` 提交对 Sui-IB/InternalBeyond（单文件离线个人网站，V2.6.2 @ 2026-09-01）的对比调研；组长要求核验可行性与制定落地计划：

- **核验**（下载 IB `InternalBeyond.html` 2.4MB 逐行比对 + LICENSE 原文 + DeepSeek 官方缓存文档）：
  - IB 侧 18 处行号引用**全部精准命中**（仅 1 处笔误：`prompt_cache_key` 实为 11663，非 14663）；
  - 许可确凿：代码 PolyForm Noncommercial 1.0.0（商用需作者书面授权）、视觉素材/文档 CC BY-NC-SA 4.0、项目标识不作商标授权 → 结论「只借算法思路、不拷代码素材」合规成立；
  - VocalVerse 侧引用（ise.py/asr.py/tts.py/audio.py/recorder.ts 行号、SSE 协议、8 轮上限、课程项目定位、mastery/skill 模块）**全部属实**；
  - 修正 3 处：⑤ 的 cache_control/prompt_cache_key 是 IB 多供应商适配，DeepSeek 官方缓存**全自动无需参数**；⑥ 本仓已有遗忘半衰期/句级掌握度，缺的仅是「检索注入」，投入中→低；② `webkitSpeechRecognition` 依赖 Google 服务器国内不可用、whisper RTF 已达标，边际价值低。
- **产出**：`docs/24-InternalBeyond借鉴落地计划.md`（已登记 README 索引）——范围裁定（⑤前缀缓存+⑥画像注入+①韵律引擎 P0；④摘要可选；②③登记前瞻；⑦报告导出 P2）；落点 = `practice/service.py:356 build_llm_context` 拆条 + 新增 `app/practice/learner.py` + 前端 `apps/web/src/audio/prosody.ts`（拍板确认浏览器端 TS 版）；任务分解合计 ≈3.3~4.3 人日（不占 M3 唱歌/前端重构主线）；PR 拆分 6 条；验收含「两次调用前缀逐字节一致」「合成信号 vitest ≥6 用例，修复前必失败」；风险回退表 + 5 个拍板点（P1 启动窗口 / P2 B3 契约落库 / P3 运行摘要 / P4 注入强度）。
- **进展（2026-09-03）**：计划升级 **v2 详细实施版**（单人今日执行）→ 三路子代理火力拷问完成 → **v3 修订定稿**（`docs/25-InternalBeyond落地计划拷问报告.md` 落档，README 索引已登记）。三官裁决：全量 A+B 6.5h 不可行 → 今日硬底线 = **A 系列（拆条+画像注入+6 pytest+ POC skip 路径）PR1 就绪待审（今日不合并，自评 comment + 挂 reviewer）**，B 系列降级（引擎骨架 + 全静音/纯音高 2 用例）；P0×6/P1×12 全部落地 v3（conclude 指令保留、P1 锚点改子串断言、VAD 线性域、f0 最小滞后、Python 侧聚合、白名单谓词、回退二选一、dotenv、日期误标更正等）。
- **组长拍板（2026-09-03 追加）**：LLM 框架优先——今日范围 = **A 系列全量 + 真 Key 验证**（POC-2 流式 META 实跑 + 缓存命中实测，LLM 链路从未真 Key 跑过），**B 系列整体顺延**（随 docs/23 前端重构波次，按 §2 设计定稿实施）。
- **二次追加（2026-09-03）**：方向升级为**对齐 ai4u 分层框架**（docs/26）——拍板采纳 §4 分期、今日按 §8「P0 内核最小切片」（ContextBuilder+MetaExecutor+TurnRunner 抽取 + learner 域基础版（含 ⑤⑥）+ META 泄漏门 + 最小 hooks；MessageSink/usage 顺延 P1）、usage 仅日志、答辩话术不透露 ai4u 仓库细节；**真 Key 实跑与框架切片同天完成**。docs/24 A 系列实现方式被 docs/26 §8 取代（目标不变）。
- **待办**：按 docs/24 v3 §3 时间块开工（09:30 起，今日 PR1 就绪待审）；PR 合并等次日 reviewer。

—— 执行人：LHRCarrier（AI 代工整理）


## 2026-09-03 修复：lieflat 学习报表雷达图点击重播后空白（BUG 实测入库）

用户报告 `vv-learning-report.html` 雷达图点击重播后消失、其余图正常。根因是本文件把两条正本
reveal 路径混用：带 `n.innerHTML=''` 的 obsReveal（basics/lupi 正本，SVG 专用）套到了 ECharts
雷达上——重播时先把 zrender 挂载的 canvas DOM 拔掉，eReveal 拿回残留实例 `clear+setOption`
不会重建 DOM → 空白。修复为 glance-porcelain.html 正本路径（obsReveal 不清空 + eReveal 复用实例，
SVG 图在各自 fn 开头自清空），与看板文件路径一致。

验证：无头 Edge 自动点击重播冒烟——修复前逻辑 canvas 数 0（必红），修复后 1（与缺陷一一对应）；
前端门禁 lint/typecheck/test:run/build 全绿；`node --check` 抽检通过。详见 `worklog/BUG实测/lieflat雷达重播失效.md`
（含坑 29：共用 reveal 的清空策略必须匹配图引擎）。

—— 执行人：LHRCarrier（AI 代工整理）

## 2026-09-02 唱歌相关文档归档 `docs/singing/`（组长要求整理）

组长要求把唱歌相关文档统一收纳：新建模块目录 `docs/singing/`，迁入 7 份文件（原 `docs/22-*` 6 份 + 原 `docs/audit/英文歌打分-…轴线D…` 1 份；文件名与内容除路径引用外零改动）：

- `docs/singing/22-英文歌打分系统集成拷问报告.md`（主报告）+ `-轴线A/B/C/E/F.md`（轴 A 算法 / B 契约 / C 数据 / E 前端 / F 运维）
- `docs/singing/英文歌打分-系统集成拷问-轴线D-离线参考旋律提取与Java薄管理端边界.md`（轴 D 离线提取 × Java 边界；原按「音频类 → docs/audit」落位，现随唱歌模块归组）

同步更新交叉引用：主报告/轴文件内互相引用路径、README 文档索引 7 行、docs/23 与 worklog 中的路径提及（已 grep 全仓验证 **0 处残留** `docs/22` / `docs/audit/英文歌` 旧路径）。唱歌文档均属 `docs/singing/` 子模块，编号 22 保留原样以便追溯；docs/23（前端重构调研）留在 `docs/` 根（其余系列文档与其并列，非唱歌模块）。

—— 执行人：LHRCarrier

## 2026-09-02 前端重构 · 市场同类设计调研（docs/23 · M3/M4 前置）

组长提出「重新构建前端」，先做市场调研再动手。产出《前端重构市场设计调研报告》（`docs/23-前端重构市场设计调研报告.md`，已登记 README 文档索引）：

- **现状盘点**：技术栈（Vue3.5+TS strict+Vite6+naive-ui+UnoCSS+Pinia+ECharts/p5/d3 + openapi 双快照生成）与页面表；引用 docs/19-M2 的 9 个 P0 交互问题与 FTUE 账（8 次点击 / 15s 强制等待 ≈ 90~120s 才开口）——**结论：重构主战场是交互层与信息架构，不是换皮**。
- **商业调研**：① AI 口语类（Speak：目标清单/三级提示/无惩罚重说/轻纠正重复盘/开口量仪表盘——七条行业标配；ELSA：音素级 + CEFR 对齐 93.88% 可信度路线；流利说/Laoora/Praktika/BoldVoice/Duolingo Max Video Call 速览）；② 游戏化类（Duolingo 设计系统：Feather Green 色系/Nunito/路径/streak/任务/联赛，佐证 docs/13 方向；报表可视化 6 手法）；③ K 歌类（全民K歌/唱吧/Smule/Yousician/UltraStar/nightingale：滚动歌词/逐句色卡/音高双轨/分享卡/练唱两段式）。
- **开源与技术**：LibreLingo（活跃度低，价值有限）；nightingale 与 docs/06 §9.4 口径同构（音高曲线 vs 参考旋律 + 星级 + 榜单）；AI 对话前端 8 条可迁移模式（LobeChat/Open WebUI/chat-ui 系）；管理端模板对照（naive-ui-admin 最省）；音频可视化选型（AnalyserNode 真波形 / wavesurfer.js 回放 / pitchy 实时音高 / D3 自绘音高曲线，勿用图表库）；移动端 8 条硬约束（iOS 手势内 getUserMedia、AudioContext suspended、autoplay 策略等）。
- **重构建议**：四象限（P0 交互修复 → IA 重排 → 对话页 Speak 化 → 视觉收尾 → M3 页面）；推荐信息架构（新首页免登录试用卡/路径化 hub/激励三件套）；逐页设计参照表（首页/hub/对话/报告/唱歌/报表/管理端）；技术决策表（**保留** Vue3+naive-ui+UnoCSS 全栈，新增 AnalyserNode/wavesurfer/pitchy，SSE 状态机重做）；5 阶段 ≈9~12 人日；答辩口径。
- **联动**：唱歌页设计依赖 docs/singing/22-英文歌打分系统集成拷问报告 已列 P0 未决项（逐帧 F0 是否落库等），前端 /sing 先静态高保真，等拍板。

—— 执行人：LHRCarrier

## 2026-09-02 英文歌打分模块 · 系统集成拷问（M3 预热）—— 前端架构调研员（AI 代笔）

按组长分工「英文歌打分我们来做，参考 nightingale；Python 端做模块、Java 端只做薄管理端」，对 M3 唱歌模块做了**系统集成拷问**并成文档（供组员参阅）：

- **产出**（均已登记 README 文档索引）：
  - `docs/singing/22-英文歌打分系统集成拷问报告.md`——**主报告**：六轴（A 算法 / B 契约 / C 数据 / D 离线提取与 Java 边界 / E 前端 / F 运维）汇总 + 未决缺口 P0~P3 决策表 + 建议实施顺序。
  - `docs/singing/22-…-轴线A/B/C/E/F.md` 与 `docs/singing/…-轴线D….md`——六轴逐问 Q/A 完整原文。
- **关键结论**：schema（`songs/lrc/song_pitch_refs/sing_attempts`）与评分口径（docs/06 §9.4：`0.5音准+0.2节奏+0.3发音`、pyin、DTW）**已定稿并迁移**，但**实现层全空**（无评分器/无参考旋律提取器/无端点/`create_session` 不认 sing/无 song_id）。
- **P0 阻塞（需组长拍板）**：① 参考旋律输入轨未定义（`songs.audio_url` 是本地路径、无独立人声/分离产物/无 `vocal_ref_url`）；② 用户逐帧 F0 是否落库（决定 D3 音准图能否画 & 评分器输出契约）；③ `songs.pitch_ref_status` 写归属冲突（songs 属 Java 独占、M-1 角色只授 Python SELECT → Python 物理写不了该列）。另：**逐句 ISE 发音限流配额炸弹**（一首歌 ≈几十句会打穿 60/h 桶）。
- **踩坑**：`docs/21` 的 `sessions.kind∈practice/defense/placement` 与模型 `SessionKinds(dialog/sing/defense)` 矛盾；`SingAttempt` 已建模（勿再当「未建模」）。

—— 执行人：前端架构调研员（AI 代笔；**正式署名待组长确认**，勿以本条目作为个人署名依据）

## 2026-09-02 PR#25 推荐系统落地 · 复审整改与合入（模型同步 / 契约快照 / CI 兜底）

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