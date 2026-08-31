# 12 · 同构 Monorepo 参照架构对比与裁决（双拷问官交叉拷问报告）

> 日期：2026-08-31 · 触发：组员提问「admin/frontend/server 三服务能否按某同构 monorepo 参照项目（2 前端 + 1 后端全 TS）那样做，是否更清晰？」
> 方法：资深架构评审 → 双拷问官交叉拷问（技术/工程角度 × 项目语境/需求角度），各自多轮递进至**问询穷尽**。
> 定位：本文件是**评审记录**（与 docs/09 同级），**唯一权威仍是 docs/06**；本文裁决已并入 docs/06 §2.1 注记与 §7、§14。
> 注：参照项目为外部企业项目，出于保密不在此存档其名称、目录结构与具体文件内容，仅保留"同构特征"层面的抽象比对。

---

## 1. 确定性结论

1. **不能、也不应按参照项目整体照搬**。理由不是"目录层面异构"，而是**结构面三重不匹配**：
   - 参照项目 = 2 前端（frontend + admin）+ 1 后端（NestJS），全 TS 同构；VocalVerse = 1 前端 + 2 后端（Python 语音/LLM/推荐 + Java 管理端/JWT），Python/Java 为**课程强约束**（docs/00、01、03；docs/09 明标"作业条件"）。
   - 参照项目的"清晰"源于同构：单语言/单一 lockfile/共享类型包契约单源/单后端。目录改名不迁移这些收益。
   - `pnpm -r` 只编排 TS 应用，**编排不了 Python/Java 进程**——"三个服务放一个 workspace"在异构栈下不成立。
2. **当前 `apps/`+`services/` 双前缀布局维持**（AD-01）。拒绝根 workspace/共享包的**真实依据** = docs/08 Q9（"单前端不用 pnpm workspace 过度工程化"）+ docs/06 §10.1（同构工具链收益无法迁移到异构栈——Prisma 先例，答辩可直接引用）。
3. **网关已存在，不新增独立网关容器**：`apps/web/nginx.conf` 即唯一入口（/api/v1/→python、/manage/→java、/healthz、/readyz），vite dev 代理语义一致，前端全走同源相对路径（无浏览器 CORS 问题；main.py 未实现 CORSMiddleware 亦无碍）。
4. **管理端 UI = `apps/web` 内 `/admin` 路由 + admin 角色**，不建独立 SPA。理由：管理端最小集仅 3 能力（docs/02）、docs/04 无独立管理台 UI 里程碑、docs/07 Q41/Q42 要求的是"管理员登录 + 列表/查询/编辑/上下架 UX"（一条路由可承载）。
5. **再评估触发条件**：仅当出现"需要独立构建/独立域名的第二前端消费者"时，才考虑根 workspace + 共享包 + 独立网关；当前形态下**不设定该触发条件**（即"几乎永远不需要"）。
6. 明确不做清单（保留）：Java→NestJS / Prisma / mono-context 全仓 Dockerfile / "跨前端+双后端唯一真源"的共享契约包。

## 2. 参照项目 7 要素对照表

| 参照项目要素 | VocalVerse 判定 | 依据 |
|---|---|---|
| 全栈同构 TS | ❌ 不可迁移 | 课程强制 Python+Java（docs/01、03） |
| 根 pnpm workspace | ❌ 仅当出现第二前端时才考虑 | docs/08 Q9；当前 1 前端收益为零 |
| 共享类型包全栈唯一契约源 | ⚠️ 只作**纯前端内共享**（envelope/错误码/SSE/上限），不得称全栈唯一真源 | web 消费 Python 契约、admin 消费 Java 契约，两套不同（docs/06 §7） |
| 独立 nginx 网关容器 | ❌ 已具备且够用 | web/nginx.conf 即网关（§2.1 注记 3） |
| 根 compose | ✅ 已具备（且更完善：healthcheck + service_healthy） | docker-compose.yml |
| mono-context Dockerfile | ⚠️ 部分借鉴（逐包 COPY 为层缓存友好设计），但 VocalVerse 保留 per-service context | 先补 `.dockerignore`（见 §3 P0-1） |
| 根 `pnpm -r` 编排 | ⚠️ 无需；polyglot 编排 = `scripts/dev.ps1`（覆盖面更大） | dev.ps1 |

## 3. 双拷问官发现的问题清单（合并去重）

### P0（已落地/待办）
- **P0-1 全库无 `.dockerignore`**（✅ 2026-08-31 已补 3 个）：`services/python/.venv`≈1.1GB、`services/java/target`≈55MB、`apps/web/node_modules`≈121MB 此前全部进入各自 build context。per-service context 只是"分开污染"，不是"躲开体积"——与 mono/per-service 无关，先补忽略才是堵体积的正解。
- **P0-2 跨语言改契约 → 手工同步前端类型**（✅ 2026-08-31 已落地动作 C）：本仓库契约真源在 Python/Java 侧（OpenAPI），workspace/TS 共享包**不能**解决此痛点；只有**构建期由 OpenAPI 生成前端 TS 类型**（`openapi-typescript`）才能消解。docs/06 §7 已改写（"不做运行时 codegen"≠"不做生成"，原表述有歧义，已澄清）。

### P1（待办，见行动清单）
- 网关/联调前：X-Request-Id 透传未实现（docs/06 §11 有声明、代码未落地；nginx 未注入、main.py 无中间件）——三服务排障链路各断一次。
- `/manage` 前缀剥离在 nginx（proxy_pass 尾斜杠）与 vite（rewrite）两处需同步改（✅ 已加互指注释，CI 冒烟断言待 M2）。
- workspace 化隐含成本（仅当时机成熟才触发）：web Dockerfile 构建上下文、frontend-ci 缓存 path、dependabot directory 需同 PR 迁移。

### P2（观察）
- `audio/*`（sse.ts 42 行 / recorder.ts 88 行）强绑 Vue、无包间复用 → 共享收益≈0，不抽包。
- 课程"列了≠必须做"先例（docs/02 砍移动端 Kotlin/Obj-C）→ 管理端 UI 同理非强制。
- 参照项目 Dockerfile 用 `--frozen-lockfile=false`（镜像内重装）；VocalVerse 保持 frozen。
- docker-build.yml 无 GHA 构建缓存（需 buildx docker-container 驱动）。

## 4. 修订后行动清单

| 动作 | 内容 | 状态 |
|---|---|---|
| A | docs/06 §2.1 注记 + §7 codegen 口径澄清 + §14 登记（不推翻 AD-01） | ✅ 已落地 |
| B | 补 3 个 `.dockerignore`（python/java/web） | ✅ 已落地 |
| C | `openapi-typescript` 构建期生成前端类型（生成文件入库 + CI typecheck 兜底） | ✅ 已落地（2026-08-31） |
| D | `/manage` 两处一致性守护（注释互指已加；CI 冒烟断言随 M2 前端冒烟） | ⏳ M2 |
| E | 管理端 UI = `apps/web` `/admin` 路由 + admin 角色（等 docs/04 排期，不建独立 SPA） | ⏳ 排期 |
| F | X-Request-Id 全链路透传（nginx 注入 + Java filter + Python middleware 已落地，各端有测试；logback/loguru JSON 结构化留待 M2） | ✅ 已落地（2026-08-31） |

## 5. 答辩口径（若被问"为什么不像参照项目那样做"）

> "某同构参照项目是 2 前端 + 1 后端的全 TS monorepo，其清晰来自单语言、单契约源与单后端；本项目按课程要求为 1 前端 + Python 语音/推荐 + Java 管理端双后端异构栈，PNPM workspace 无法编排 Python/Java（docs/08 Q9、docs/06 §10.1 已有同款先例——Prisma 因此被否）。因此保留 apps/services 分层；网关与 compose 已具备；管理端用 Web 内 /admin 路由承载。真正的维护痛点（跨语言契约手动同步）用 OpenAPI 构建期生成前端类型解决，而不是换 workspace。"

## 6. 问询穷尽声明

双拷问官各自完成多轮递进（事实核查 → 最强反方辩护 → 二阶后果 → 收敛），分别于技术层（Dockerfile/网关/契约/CI/缓存/依赖图）与语境层（课程约束/ADR 证据/管理端 UI 计划/里程碑/动机三分/替代路径五条/文书纪律）收敛至"无更强反驳"。剩余仅两类不可问项：①用户真实动机（已由组员确认＝要清晰、少混乱）；②运营细节守护（.dockerignore 纪律、X-Request-Id、/manage 一致性），均不改变本裁决。
