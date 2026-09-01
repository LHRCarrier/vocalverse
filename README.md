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

### 0. 先明确当前阶段能测什么（M1 骨架）

- ✅ 能测：三服务连通性、录音组件（MediaRecorder → WebM/opus）、**stub 音频管线**（ASR/TTS/评分/LLM 均为 Fake，返回固定演示文本）、CI/镜像构建。
- ⏳ 尚无：真实语音识别/合成/评分、场景扮演多轮对话、推荐/报表（M2~M3 接入，接口与数据模型已定，见 docs/06）。

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
Copy-Item .env.example .env                # 填 DeepSeek/讯飞/Azure 密钥（M2 需要）
uv run uvicorn app.main:app --reload --port 8000

# 4. Java（终端 3）——首次先 mvn -N wrapper:wrapper 生成 mvnw
cd services/java
mvn spring-boot:run
```

> ⚠️ 方式 B 与方式 A 端口相同（8000/8080），**不要同时起**；各服务更多细节见 `services/*/README.md`。

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
| `.env` 忘记填密钥 | M1 不阻塞（占位符可起）；M2 起 DeepSeek/讯飞必须填，且严禁提交 `.env` |

详细决策与约定见各服务 README 与 `docs/06-技术框架决策.md`。

## 仓库结构

```
apps/web/         前端（Vue3+TS+Vite6；录音 / SSE / 埋点）
services/python/  语音管线 + LLM Agent + 推荐（FastAPI；Alembic 唯一 schema 真源）
services/java/    薄管理端（Spring Boot；JWT 签发）
infra/            部署与 nginx 配置
scripts/          dev.ps1 / bootstrap.ps1（Windows 一键）
docs/             00~05 规划文档 + 06 技术框架决策（ADR 唯一权威）+ 07/08 拷问报告 + 09 框架评审 + 10/11 数据库 + 12 同构Monorepo对比裁决 + 13 前端设计系统 + api/ 契约
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

## 里程碑（详见 docs/04、docs/06）

1. **M1 骨架**（第 1 周）：本仓库脚手架 + 三端 CI + 语音三件套 stub 联调
2. **M2 MVP**（第 2-3 周）：口语闭环（注册→入学测试→场景对话→录音→评分→建议→报告）
3. **M3 特色**（第 4-5 周）：唱歌评分做深（音准/节奏/发音）+ 推荐/报表演示化 + 四指标看板；（门禁）wav2vec2 微调
4. **M4 联调**（第 6 周）：性能 p95 达标、演示脚本、答辩材料

## 红线（公开仓库）

API Key、密码、真实用户数据、训练集原始文件、模型权重、原始音频、商用音乐 **严禁入库**；密钥只进 `.env`（已 gitignore）。
