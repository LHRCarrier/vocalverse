# VocalVerse 声语界

> AI 英语口语训练 + 英文歌练唱评分平台 —— 以"说得好、唱得准"为目标的智能发音教练

VocalVerse 面向不同年龄段英语学习者，基于大模型场景扮演（AI 数字人对话）+ 语音识别/合成/评分技术，提供：

- **口语陪练**：生活/工作/学习场景模拟对话，AI 数字人实时互动，发音、语法、流利度多维度评分
- **英文歌练唱**：英文歌曲跟唱，音准、节奏、发音逐句评分（本项目特色扩展）
- **个性化学习**：入学测试 + 学习画像 + 推荐算法，自动生成学习路径
- **可视化报表**：口语/唱歌成绩多维度分析与趋势展示

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | **Vue 3 + TypeScript(strict) + Vite 6 + pnpm**（Web 端；移动端以 PWA/响应式覆盖，原生 App 列为扩展） |
| Python 服务 | **FastAPI**：ASR（faster-whisper small/int8/CPU）、TTS（edge-tts，Azure 备胎）、讯飞评测（发音评分基线）+ wav2vec2 微调（门禁化自研加分项）、唱歌评分（pyin + DTW）、DeepSeek LLM 场景扮演 Agent、推荐（sklearn） |
| Java 服务 | **Spring Boot 3.3 / Java 21**（薄管理端）：用户管理、场景/歌曲库 CRUD、工单、JWT 签发 |
| 大模型 | DeepSeek API（场景扮演、语法判定、评分报告生成） |
| 模型训练 | **PyTorch**（CPU 推理；云 GPU 训练隔离环境）+ **Scikit-learn**（推荐、水平预测） |
| 数据 | PostgreSQL（Alembic 唯一 schema 真源）· Redis（会话/缓存/限流） |
| 部署 | Docker Compose（python 8000 / java 8080 / web 8088 / pg 5432 / redis 6379） |

## 启动指南（团队测试用）

### 端口速查（前端两个端口对应两种方式，别混淆）

| 端口 | 服务 | 属于 | 入口 |
|---|---|---|---|
| **5173** | 前端（Vite dev server） | **方式 B** 本地开发 | http://localhost:5173 |
| **8088** | 前端（nginx，反代 API 同源） | **方式 A** 容器一键 | http://localhost:8088 |
| 8000 | Python API（容器或本地均可） | A / B | /docs · /readyz |
| 8080 | Java API（容器或本地均可） | A / B | /swagger-ui.html |
| 5432 / 6379 | PostgreSQL / Redis | **仅容器**（A、B 共用） | - |

> ⚠️ 本地 `pnpm dev` 开着 5173 是**正常的**；8088 只在方式 A 容器启动后才有。方式 B 不要两种入口混用（代理分别配好，见 `apps/web/vite.config.ts`）。

### 0. 先明确当前阶段能测什么（M2 MVP 已落地）

- ✅ **能测（M2）**：注册/登录（Java JWT，演示账号 `demoadult`/`demoteen`/`demosenior`，密码 `demo123456`）→ 场景对话（录音 ≤15s → ASR 转写 → 三维评分 + 教练笔记 + 语言点覆盖度 + 救援提示卡 → 8 轮收尾）→ 评分报告（总分/覆盖度三栏/建议/再练）；自定义答辩导师（粘贴论文 → AI 评委英文提问 → 等级反馈）；埋点 10 类事件；SSE 流式（音频为时间轴权威、文本字幕）。
- ⏳ 真实语音链路需 `.env` 密钥（DeepSeek/讯飞）+ ffmpeg + whisper 模型；缺省时全链路走 Fake（`APP_TESTING=true`），联调冒烟脚本：`python scripts/poc/demo_smoke.py`。
- ⏳ M3（唱歌/推荐/报表/社区）仍为占位页。

### 1. 一次性准备（工具链）

```powershell
.\scripts\bootstrap.ps1        # 自检 node22/pnpm/python3.12/uv/jdk21/maven/docker/ffmpeg
winget install ffmpeg          # 缺 ffmpeg 时（音频转码必需）
```

- 版本基准见 `.tool-versions` / `.nvmrc`（Node 22.11 / Python 3.12 / JDK 21）。

### 2. 方式 A：Docker Compose 一键（体验/验收，最省事）

```powershell
cd 仓库根目录
Copy-Item .env.example .env    # 可选；不填也能起（占位符），但 AI 功能保持 stub
.\scripts\dev.ps1              # 构建并启动 5 个服务（首次较慢，见常见问题）
```

启动完成后：

| 入口 | 地址 | 验证点 |
|---|---|---|
| 前端演示页（容器入口） | http://localhost:8088 | 显示「VocalVerse 框架骨架」，Python/Java 状态为 ✓；点「开始录音」→ 允许麦克风 → 6 秒后显示 stub 转写 |
| Python API 文档 | http://localhost:8000/docs | 可试 `POST /api/v1/asr`、`/tts`、`/score`、`/llm/chat`（返回 stub 结果） |
| Python 健康检查 | http://localhost:8000/healthz 、/readyz | 返回 `{"status":"alive"}` / `code=0` |
| Java API 文档 | http://localhost:8080/swagger-ui.html | `/actuator/health` 返回 UP |
| 数据库 | localhost:5432 (PG) / 6379 (Redis) | 账号见根 `.env`（默认 vocalverse / vocalverse-dev） |

停止：`docker compose down`（清数据加 `-v`）。

### 3. 方式 B：本地开发热重载（M2 起日常开发用）

数据库/缓存仍在容器里跑（**Docker Desktop 必须先启动**，daemon 未运行会报 `failed to connect to the docker API`），三端各自本地起：

```powershell
docker compose up -d postgres redis        # 1. 只起依赖
docker compose ps                          #    确认 postgres、redis 均为 healthy 再继续

# 2. 前端（终端 1）——注意：本地 dev 端口是 5173（不是 8088）
cd apps/web; pnpm install; pnpm dev        # http://localhost:5173（代理已配 8000/8080）
# 3. Python（终端 2）——首次 uv sync 会下载 CPU 版 torch，较慢
cd services/python
uv sync
Copy-Item .env.example .env                # 填 DeepSeek/讯飞密钥（M2 真实管线需要；不填则走 Fake）
uv run alembic upgrade head                # 建表（schema 真源=Alembic；M2 迁移 0001+0002）
uv run python -m app.db.seed               # 幂等 seed：8 套场景内容 + 入学测试题库
uv run uvicorn app.main:app --reload --port 8000   # 注意：uv 前缀不能省（Windows 下 venv 不在 PATH）

# 4. Java（终端 3）——首次先 mvn -N wrapper:wrapper 生成 mvnw
cd services/java
mvn spring-boot:run
```

> ⚠️ 方式 B 与方式 A 端口相同（8000/8080），**不要同时起**；各服务更多细节见 `services/*/README.md`。
>
> 💡 **一键起停（推荐，2026-09-04 起）**：三端用**独立进程**启动（日志 `local/dev-logs/`，gitignored），
> 关终端不会再弹「Terminate batch job」：
> ```powershell
> pwsh -File scripts/dev-up.ps1 start    # 启动三端 + 健康等待（电脑重启/断网后重跑一次即可）
> pwsh -File scripts/dev-up.ps1 status   # 查看监听与健康
> pwsh -File scripts/dev-up.ps1 stop     # 按端口杀三端
> ```
> 注意：Windows PowerShell 5.1 会因 UTF-8 解析报错，必须用 `pwsh`（7）执行。

### 3.5 手机端（Android APK · 今日交付形态）

方式 A 全栈起好后（8088 可用），手机壳 = Capacitor 8 远程 URL 型：Android WebView 直接加载
`http://<局域网IP>:8088`（nginx 同源反代，后端零改动）。

```powershell
# 构建 APK（已预置 server.url=http://192.168.1.3:8088；换环境改 apps/mobile/capacitor.config.json 后 npx cap sync）
cd apps/mobile/android; .\gradlew.bat assembleDebug
# 产物：apps/mobile/android/app/build/outputs/apk/debug/app-debug.apk（≈4MB）
# 安装：adb install -r <apk>（手机开 USB 调试），或传 APK 到手机直接安装
```

- 演示账号：`demoadult` / `demoteen` / `demosenior`，密码 `demo123456`；
- 手机与后端起在**同一局域网**；Web 体验入口同源（PWA：`/manifest.webmanifest`，安卓可"添加到主屏幕"）；
- 详细说明/删除清单见 `apps/mobile/README.md`，产品与技术决策见 `docs/27`~`docs/29`。

### 4. 启动成功判定（验收清单）

- [ ] `docker compose ps` 五个服务全部 `healthy`；
- [ ] 8088 演示页两个服务状态均为 ✓；
- [ ] `GET /readyz` 返回 `code=0`、`data.status=ready`；
- [ ] 录音演示能完成一次「录音→stub 转写」闭环（不出 413/500）；
- [ ] （可选）本机 `mvn verify`、`pnpm test:run`、`pytest` 各自通过（CI 同款）。

### 5. 常见问题（FAQ）

| 现象 | 处理 |
|---|---|
| `docker compose` 报 `failed to connect to the docker API` | **Docker Desktop 没启动**：先启动 Docker Desktop 并等引擎就绪（任务栏鲸鱼图标转绿），再执行 compose |
| `mvn spring-boot:run` 报 Hibernate `JdbcEnvironmentInitiator` / 数据库连接失败 | 方式 B 漏了起依赖：先 `docker compose up -d postgres redis` 且 `docker compose ps` 显示 healthy；若 Java 配置连的不是容器库，检查 `DB_HOST` 环境变量（默认 localhost:5432，见 `services/java` 的 `application.yml`） |
| 端口 8088/8000/8080 被占用 | `Get-NetTCPConnection -LocalPort <port> -State Listen` 找 PID 释放；或改 compose 的 ports 映射 |
| Java 启动日志结尾报 `APPLICATION FAILED TO START ... Port 8080 was already in use` | **机器上已有 Java 实例在跑，别开第二个**（第一个是活的，不是服务挂了；2026-09-01 实测踩坑：第二个实例失败、第一个一直正常服务）。`Get-NetTCPConnection -LocalPort 8080 -State Listen` 找 PID 确认；要换新版本就 `taskkill /PID <pid> /F` 后再起 |
| Java 启动日志显示 `using Java 24.x` / IDE 直接跑但端口被自己占 | **`JAVA_HOME` 设错**：项目钉死 JDK 21（docs/06 §3），以 Temurin 21 为准：`[Environment]::SetEnvironmentVariable('JAVA_HOME','C:\Program Files\Eclipse Adoptium\jdk-21.0.8.9-hotspot','User')` 后**重开终端**；`mvn -version` 显示 Java 21.0.x 即对齐。Java 24 跑 Spring Boot 3.3 当前能起但有一串 native-access 警告（未来版本会直接拦截）且与 CI 环境不一致 |
| 前端请求 404 / 服务不可达 | 先确认对应服务容器 `healthy`；方式 B 下需先 `docker compose up -d postgres redis` |
| Docker 卡顿/服务起不来（WSL2 默认内存 2GB） | 按 `infra/dev/.wslconfig` 示例设 `memory=8GB,processors=4`，执行 `wsl --shutdown` 后重启 Docker |
| 首次 `dev.ps1` 很慢 | 正常：基础镜像 + Python 依赖（含 CPU torch ≈200MB）；网络差可给 Docker 配镜像加速 |
| 语音接口返回固定文本 | 预期行为：M1 全部为 Fake 实现（`services/python/app/audio/stubs.py`），M2 替换为 faster-whisper / edge-tts / 讯飞 ISE |
| Windows 长路径/编码问题 | `git config --global core.longpaths true`；`.gitattributes` 已强制 LF（.ps1/.bat 用 CRLF） |
| Java 日志中文乱码（如「演示账号就绪」变「婕旂ず璐」） | 双重错位：① 编译期 pom 未声明编码（已钉 `project.build.sourceEncoding=UTF-8`，改 pom 后重新编译生效）；② 运行期终端码页——VSCode 终端先 `chcp 65001` 再起 Java，或 `mvn spring-boot:run -Dspring-boot.run.jvmArguments="-Dstdout.encoding=UTF-8 -Dstderr.encoding=UTF-8"`（Java 18+ 生效）；Python/edge-tts 脚本同理：`$env:PYTHONIOENCODING='utf-8'` |
| `.env` 忘记填密钥 | M1 不阻塞（占位符可起）；M2 起 DeepSeek/讯飞必须填，且严禁提交 `.env` |
| seed/迁移报 `password authentication failed for user "vocalverse"` | **DB 密码与 compose 默认不一致**：`services/python/.env` 的 `APP_DATABASE_URL` 密码必须等于 `docker-compose.yml` 的 `${POSTGRES_PASSWORD:-vocalverse-dev}`（`.env.example` 默认已是 `vocalverse-dev`）；改密码需三处同步（compose 环境变量 / services/python/.env / 根 `.env` 的 `POSTGRES_PASSWORD`） |
| `alembic` 命令不识别 | Windows 下 venv 不在 PATH：一律 `uv run alembic ...`（uv 前缀同样适用于 uvicorn/pytest） |
| 8000 端口 `WinError 10013`（访问被拒） | 端口被占用（旧 uvicorn 实例等）：`Get-NetTCPConnection -LocalPort 8000 -State Listen` 找 PID 释放后再起 |

详细决策与约定见各服务 README 与 `docs/06-技术框架决策.md`。

## 仓库结构

```
apps/web/         前端（Vue3+TS+Vite6；录音 / SSE / 埋点 / PWA manifest）
apps/mobile/      Capacitor 手机壳（Android 首发；server.url 型加载线上全栈，详见 apps/mobile/README.md）
services/python/  语音管线 + LLM Agent + 推荐（FastAPI；Alembic 唯一 schema 真源）
services/java/    薄管理端（Spring Boot；JWT 签发）
infra/            部署与 nginx 配置
scripts/          dev.ps1 / bootstrap.ps1（Windows 一键）
docs/             00~05 规划文档 + 06 技术框架决策（ADR 唯一权威）+ 07/08 拷问报告 + 09 框架评审 + 10/11 数据库 + 12 同构Monorepo对比裁决 + 13 前端设计系统 + 14 功能规格（v2 拍板）+ 15/16 双子拷问报告 + 17 合流与拍板记录 + 18 实施计划 + 19 六路拷问报告 + 20/21 系统设计说明书（架构/接口）+ api/ 契约
worklog/          团队工作日志（VocalVerse工作日志.md，按日追加）
```

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/00-案例原始要求.md` | 案例 #7 docx 原文（选题总表、案例功能、开发语言、技术点，逐字转录） |
| `docs/01-选题依据.md` | 课程案例 #7 原文要点 + 扩展方向（唱歌评分） |
| `docs/02-功能规划.md` | 功能模块清单与 MVP 砍范围建议 |
| `docs/03-技术选型.md` | 技术方案、API 选型、云 GPU 预算 |
| `docs/04-分工与里程碑.md` | 三人分工与阶段里程碑（M1~M4） |
| `docs/05-GitHub协作规范.md` | 分支保护、PR 流程、commit 规范 |
| **`docs/06-技术框架决策.md`** | **ADR 权威文档**：双子代理拷问产出 + 组长拍板（拓扑/版本/CI/契约/音频/指标口径/评分公式/合规），与 00~05 冲突以本文档为准 |
| `docs/07-需求拷问报告.md` | 需求拷问官 **63 问原文**（范围/指标口径/评分口径/社区/合规/DoD）+ 38 条 ADR 建议——docs/06 的决策依据，答辩可引用 |
| `docs/08-技术架构拷问报告.md` | 技术架构拷问官 **60 问原文**（目录/版本/CI/契约/音频/模型/DB/Windows 坑）+ AD-01~40 决策清单——docs/06 的决策依据 |
| `docs/09-技术框架评审.md` | 资深架构视角框架评审：匹配度/性能预算审计（ASR 延迟为头号风险）/可维护性/评分表 + P0~P2 问题清单与按里程碑行动表 |
| `docs/10-数据库设计.md` | 19 表库结构设计（用户/场景/歌曲/评分/埋点/工单…）+ 字段口径 |
| `docs/11-数据库拷问报告.md` | 数据库拷问官报告：字段/索引/口径拷问与拍板 |
| `docs/12-同构Monorepo对比与裁决.md` | 双子拷问官交叉拷问「能否按同构 monorepo 参照项目做」+ 多项修正 + 答辩口径；裁决已并入 docs/06 §2.1 |
| `docs/13-前端设计系统.md` | 前端设计系统（naive-ui/UnoCSS/设计 token 三层分工 + B 多邻国活力配色 + 路由表 + 动效可视化栈 + 答辩口径） |
| `docs/14-M2场景对话与答辩导师规格.md` | **v2 拍板稿**：场景对话回合状态机/SSE 流式协议/prompt 模板/语言点覆盖度/教练双人格/2 级救场 + 答辩导师（W3 极简：三级题库/提问依据/等级标签阶梯/软删脱敏） |
| `docs/15-M2场景对话需求拷问报告.md` | 需求/产品拷问官 28 问（覆盖缺口/达成度悖论/差异化立论/排期）+ 10 条拍板建议 |
| `docs/16-M2场景对话技术拷问报告.md` | 技术/架构拷问官 37 问（假流式/LLM 调用预算/CHECK 迁移/安全注入/延迟复算）+ 量化表 |
| `docs/17-M2场景对话拷问合流与拍板记录.md` | 双子拷问合流：交叉验证矩阵/分歧裁决（答辩极简·软删·等级标签）/v1→v2 对照/登记义务清单 |
| `docs/18-M2实施计划.md` | M2 实施计划：DoD/契约冻结清单/三人任务分解（组长 Python+Java/算法/前端）/PR 拆分 12 条/pytest+vitest 矩阵/风险回退表/联调演示准备 |
| `docs/19-*.md` | 六路拷问报告：需求调研里程碑的架构/UX/商业合规拷问 + 竞品深度分析（流利说/Speak） |
| `docs/20-系统架构设计说明书.md` | **系统设计①**：五层划分/应用内分层/服务边界/写方唯一性矩阵 + 守护机制设计（M-1~M-4）/3 张 Mermaid DFD/P0 目标态排期表 |
| `docs/21-接口设计说明书.md` | **系统设计②**：OpenAPI 双快照对账（Python 20 ops/Java 6 ops 端点清单）/SSE 契约/内部 REST 契约登记/契约整改项 R-1~R-16/变更流程 |
| `docs/singing/22-英文歌打分系统集成拷问报告.md` | **M3 唱歌模块·系统集成拷问主报告**：六轴（A 算法/B 契约/C 数据/D 离线提取与 Java 边界/E 前端/F 运维）系统集成拷问汇总、未决缺口 P0~P3 决策表、建议实施顺序 |
| `docs/singing/22-英文歌打分系统集成拷问报告-轴线A.md` | 轴线 A：评分算法与参考旋律（pyin/DTW/音准·节奏·发音/缺失降权/Fake 接口/逐帧 F0）逐问 Q/A |
| `docs/singing/22-英文歌打分系统集成拷问报告-轴线B.md` | 轴线 B：Python API 契约与异步（整首跟唱形态/端点/Redis 任务轮询/ISE 配额炸弹/错误码）逐问 Q/A |
| `docs/singing/22-英文歌打分系统集成拷问报告-轴线C.md` | 轴线 C：数据模型与存储（sing_attempts 建模复核/榜单/大 JSON/级联/24h 清理/迁移）逐问 Q/A |
| `docs/singing/22-英文歌打分系统集成拷问报告-轴线E.md` | **系统集成拷问·轴线 E**：Web 前端（录音→上传→评分展示→音高/节奏可视化）与移动端/PWA；唱歌交互形态/录音转码/可视化选型/轮询/移动端 8 约束/组件复用 + 未决缺口 B1~B7 |
| `docs/singing/22-英文歌打分系统集成拷问报告-轴线F.md` | 轴线 F：运维/测试/合规/并发（线程模型/信号量/readyz/24h 清理/基准脚本/战略风险 G9）逐问 Q/A |
| `docs/singing/英文歌打分-系统集成拷问-轴线D-离线参考旋律提取与Java薄管理端边界.md` | 轴线 D：离线参考旋律提取管线 × Java 薄管理端边界（audio 解耦/触发编排/单写方冲突/薄管理端最小端点/合规） |
| `docs/23-前端重构市场设计调研报告.md` | **前端重构调研**：现状盘点（技术/页面/设计系统/9 个 P0 体验问题）+ 商业同类设计调研（Speak/ELSA/流利说/Duolingo/全民K歌/Smule/Yousician）+ 开源与前端技术模式（LibreLingo/nightingale/LobeChat 系/管理端模板/音频可视化选型）+ 重构建议（IA/逐页参照表/5 阶段落地/答辩口径） |
| `docs/24-InternalBeyond借鉴落地计划.md` | **IB 借鉴落地计划 v3（三官拷问修订定稿）**：范围裁定（⑤前缀缓存⑥画像注入①韵律引擎；④/⑦/②③不做或后置）+ 详细设计（`build_llm_context` 静态/动态**重写**（保留 conclude 指令与 `(none)` 兜底）、`learner.py` 画像注入（Python 侧聚合+白名单+TTL 缓存+收尾失效挂钩）、`prosody.ts` 纯函数韵律引擎（线性域 VAD+f0 最小滞后拾取）、`llm_cache_hit.py` POC）+ 测试用例（修复前必失败）+ 单人时间块（A 硬底线+B 骨架）/PR 拆分（今日就绪待审不合并）/风险回退/答辩口径；许可红线（只借思路不拷代码素材） |
| `docs/25-InternalBeyond落地计划拷问报告.md` | **IB 落地计划三官火力拷问报告**：技术（A 系列 P0×2：删 conclude 指令/锚点自相矛盾）、算法（B 系列 P0×3：VAD 单位域/特征作用域/f0 平局错频）、范围排期（全量 6.5h 不可行裁决：A 硬底线+B 骨架）、P1×12/P2×15 整改全部落地 docs/24 v3 + 事实核查修正（日期误标/.env/章节号） |
| `docs/26-LLM框架对齐ai4u评估与实施计划.md` | **LLM 框架对齐 ai4u 评估与实施计划**：ai4u（组内自研桌面 AI 伴侣）Agent 运行时解剖（scenes/runtime/domains/hooks/core）+ 映射表（→ `app/agent/` 分层：ContextBuilder/TurnRunner/MetaExecutor/MessageSink/学习者记忆域/persona）+ 不迁移清单（proactive/IM/TRPG/journal/RAG）+ 分期（P0 内核 2.5~3.5 人日 → P1 memory 双轨 → P2 persona）+ 风险回退 + 答辩口径；docs/24 A 系列并入 P0 内核；仅迁移架构模式不拷贝代码（ai4u 无 LICENSE、含外部素材） |
| `docs/27-移动端方案.md` | **移动端方案（待评审稿）**：真实产品化定位 → Capacitor 8 壳（远程 URL 型，Android 首发 iOS 跟后）复用现有 Vue 应用零后端改动；MVP 只做「口语对话闭环」；调研借鉴（道法术器：Freemium 定价/三问/渠道/合规工具）+ 周计划 W0~W4 + 真机实测表 + ADR 修订申请（§13，拍板后执行）+ 开源调研（ETOS §4.1 / MobileGym §4.2 / 22 候选采纳清单 §4.3） |
| `docs/28-开源语音音频能力借鉴落地计划.md` | **开源语音/音频能力借鉴落地计划（待评审稿）**：语言学习类+音频处理类开源项目调研（10 候选，node 抓 GitHub + npm 许可证核验）→ 转译落地；P0 三切片（A 前端音频底座 = wavesurfer.js BSD-3 + recorder polyfill MIT；B 服务端 ASR 降级 = sherpa-onnx Apache-2.0 第二引擎；C 跟读交互增强 = 借鉴 SpeechShadowing 出句→录音→对照 + 静音切句）+ 红线表（pitchfinder GPL/peaks.js LGPL/AGPL 两项目一律只借思路）+ ADR 修订申请（§6）+ 答辩口径；浏览器 WASM 离线 ASR 结论「服务端降级 + 移动端原生性价比更高（P1）」 + 正确包名警示（`wavesurfer.js@7.12.11`，勿装占位包 `wavesurfer@1.3.4`） |
| `docs/29-移动端与音频底座实施详细设计.md` | **移动端与音频底座实施详细设计（四路拷问合流·待评审稿）**：79 问拷问（前端/音频/后端/排期）→ 五条交叉共振发现（P0 归属错配·排期矛盾·存量三红旗·降级语义空洞·许可细化）+ 裁决建议表（A 组先决 G1~G3 / B 组实施 G4~G11 / C 组文档修正）+ 切片重排（S1 波形组件随 M3 落 / S2 ASR 降级+信号量前置 / S3 跟读后置 / S4 手机壳加分项）+ 文件级详细设计（S1~S2 含 TDD 用例）+ W 计划修订（6 周弹性+提审并行）+ 合规清单 + PR 拆分与门禁 |
| `docs/design-system/vocalverse/*.md` | **设计系统分层检索副本**（ui-ux-pro-max skill 维护，供 AI 构建页面时分级读取）：MASTER.md（色彩/圆角阴影/字体/交互反馈/触控/反模式）+ pages/home.md + pages/login.md（页面级覆盖，优先于 MASTER） |
| `docs/30-移动端App测试方法.md` | **移动端 App 测试方法**：L0 门禁 / L1 Web 功能联调（W1~W10 用例表）/ L2 壳专项（A1~A7）/ L3+L4 真机八约束+蓝牙麦专项（B1~B12，docs/27 §8 实测表口径）/ L5 商店预检 + 回归 DoD + 已知缺口（自记「勿当通过」）；核心思想：功能测结构化状态断言、视觉测原型基线并排比对 |
| `docs/31-移动端UI重设计（Soft UI Evolution）.md` | **移动端 app UI 重设计（app 端唯一真相源，样板阶段）**：拍板方向 Soft UI Evolution + Voice-First 元素层 + Micro-interactions（排除夜店深色/程序员极简/少儿低幼）；四条硬规则（UI 即信息 / 排版呼吸感 / 交互必有反馈 / app 丝滑）+ token 表 + 组件规范 + 页面落地顺序（首页/登录样板已完成）+ 验收清单；机器副本 `docs/design-system/vocalverse/`（MASTER + pages/home + pages/login） |

## 里程碑（详见 docs/04、docs/06）

1. **M1 骨架**（第 1 周）：本仓库脚手架 + 三端 CI + 语音三件套 stub 联调
2. **M2 MVP**（第 2-3 周）：口语闭环（注册→入学测试→场景对话→录音→评分→建议→报告）
3. **M3 特色**（第 4-5 周）：唱歌评分做深（音准/节奏/发音）+ 推荐/报表演示化 + 四指标看板；（门禁）wav2vec2 微调
4. **M4 联调**（第 6 周）：性能 p95 达标、演示脚本、答辩材料

## 红线（公开仓库）

API Key、密码、真实用户数据、训练集原始文件、模型权重、原始音频、商用音乐 **严禁入库**；密钥只进 `.env`（已 gitignore）。
