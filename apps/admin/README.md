# VocalVerse 管理端控制台（`apps/admin`）

独立 SPA 管理后台：**运维 / 运营 / 审核** 三角色 RBAC。设计与拷问见
[`docs/50-管理端后台设计.md`](../../docs/50-管理端后台设计.md)、[`docs/51-管理端后台拷问报告.md`](../../docs/51-管理端后台拷问报告.md)。

> **为什么是一个独立应用而不是 `apps/web` 里的一个路由**：旧管理端（`apps/web` 的 `/admin` 路由 + `AdminLayout.vue`）
> 已按需求方口径**整体废弃并删除**，管理端唯一形态是本控制台。它有自己的身份体系（`admin_users`，与 App 的
> `users` 无外键、无字段共享）、自己的权限语义（34 个权限码，不是 `ROLE_ADMIN`）、自己的构建与发布节奏。
> ADR 修订申请见 `docs/50 §2.3`（**待组长拍板**）。
>
> **模块隔离**：本应用**零 import `apps/web` 源码**。设计 token 是**复制**而非共享（`src/styles/tokens.ts`），
> 契约类型是**手写**而非复用 App 的生成物（`src/api/dto/**`）。理由：两端契约与发布节奏独立，
> 共享会让控制台被 App 的变更绑住（`docs/50 §3.1`）。

## 快速开始

```powershell
# 0) 依赖：PostgreSQL/Redis（容器）+ Python + Java
docker compose up -d postgres redis

# 1) Python 运维域（指标 / 预警 / LLM trace / 书籍 / 媒体）
cd services/python
uv run alembic upgrade head          # 含控制台迁移 0013（15 张表）
$env:VOICEVERSE_CONSOLE_BOOTSTRAP_USERNAME  # 见下方「首个账号」
uv run uvicorn app.main:app --reload --port 8000

# 2) Java 控制台域（身份 / RBAC / 审计 / 审核 / 内容）
cd services/java
mvn spring-boot:run                  # :8080

# 3) 控制台本体
cd apps/admin
pnpm install
pnpm dev                             # http://localhost:5174
```

**端口 5174**（避开 `apps/web` 的 5173），两者可同时起。生产入口是 `/console/`（自带 nginx server 块，见 `nginx.conf`）。

### 两个上游不是失误

| 前缀 | 上游 | 域 |
|---|---|---|
| `/manage/**` | Java :8080（rewrite 剥前缀） | 身份 / RBAC / 审计 / 审核 / 内容 |
| `/api/v1/**` | Python :8000（不剥） | 运维（指标/预警/LLM trace）/ 书籍 / 媒体 |

这是**按数据归属方分服务**：每个服务只暴露自己**拥有（写）**的数据。控制台 SPA 是组合层——
让 Java 去读 Python 的表会破坏 `docs/06 §10` 的单写方矩阵（`docs/50 §3.2`）。
两个前缀下的 `/console/**` 子路径**不重叠**。

## 首个账号（空库必须走这一步）

控制台身份与 App 账号**完全独立**，且**不提供自助注册**。空库上先由 env 驱动的一次性 bootstrap 创建 `super`：

```powershell
$env:VOICEVERSE_CONSOLE_BOOTSTRAP_USERNAME = "your-admin"
$env:VOICEVERSE_CONSOLE_BOOTSTRAP_PASSWORD = "<强口令>"
```

- **仅当 `admin_users` 为空**时创建；弱口令/默认口令会**拒绝创建并打 ERROR**（不允许"默认口令"后门）；
- 日志打印"已创建引导账号"但**永不打印口令**；
- 上线后清空这两个变量，账号由 `console:admin:write` 管理。

## 三个角色看什么

| 角色 | code | 控制台里能看到 |
|---|---|---|
| 运维 | `ops` | 服务总览（依赖探测与容器健康检查**同源**）、性能指标、预警中心、**LLM Trace**（对齐 DeepSeek harness 的 GenAI span 树：`ENTRY→AGENT→STEP→{LLM,TOOL}`） |
| 运营 | `operator` | 歌曲 / 听力素材 / 书籍 / 场景 / 媒体库 / 上架流水 / 工单 |
| 审核 | `moderator` | 待审队列 / 举报处理 / 处置记录（含**视频/媒体**，`content:media:read`） |
| 超级管理员 | `super` | 全部，另含管理员 / 角色权限 / 审计日志 |

**导航按权限裁剪，不按角色名重排**——同一个功能在任何角色下都在同一位置，只有"看得见/看不见"的区别（`src/router/nav.ts`）。

## LLM Trace 的隐私设计（改之前先读这段）

- **内容捕获默认关闭**：`APP_LLM_TRACE_CONTENT_CAPTURE=false` 时 `llm_span_contents` **零行**，
  且结构元数据与内容**分表存储**——因此"我们没存 prompt"是**可从库结构自证**的，不靠声明；
- 读内容需要**独立权限码** `ops:trace:content:read`（看性能不需要看用户对话），且**每次读取写审计**；
- **答辩域（`kind IN ('defense','thesis')`）即使开启也硬排除**——那是用户粘贴的论文正文，脱敏规则对它无效；
- 内容保留 72 小时，trace 结构保留 30 天。

这是 `docs/06 §9.7` 「只存评分/转写/元数据」的**受控例外**，修订申请见 `docs/50 §2.3` 修订 3。

## 设计语言（与产品同族，但不是同一套）

| 维度 | 取值 | 说明 |
|---|---|---|
| 色彩 | 继承产品 `u-*` 纸墨（`ink #1c1c1a` / `paper #f5f4f1` / `accent #2f6bff`） | `ink` 与图表层 lieflat Mono 的 `INK` **完全相同**，所以 UI 与图表天然一家人 |
| 圆角 | 控件 8 / UI 卡 16 / 胶囊 999 | 控制台尺度，不用移动端的 20~24 |
| 图标 | **Tabler only**，`unplugin-icons` 编译期内联 | 仓库硬规则（`docs/35`）；显式映射见 `src/components/layout/NavIcon.vue` |
| 组件 | naive-ui，**单一注入点** `themeOverrides`（`src/App.vue`） | 主色用现行 `#2f6bff`，**不是**已退役的移动端绿 |
| 图表 | **锁 lieflat Mono 单一色彩系统**，手写 SVG 为主 | `src/components/charts/**`；偏离清单见 `docs/50 §12.4` |

**对比度**：焦点环、链接、徽标前景都按 WCAG AA 校过（原稿的 `#e8edff` 焦点环在白底只有 1.17:1，等于隐形）。

## 门禁

```powershell
cd apps/admin
pnpm lint && pnpm typecheck && pnpm test:run && pnpm build
```

- **`pnpm typecheck` 是真的会检查的**：脚本显式 `-p tsconfig.app.json`。
  ⚠️ `apps/web` 的同类脚本是 `vue-tsc --noEmit`，而根 `tsconfig.json` 是 solution-style（`files: []`）——
  **一个文件都不检查**（2026-09-10 实测：故意写类型错误，退出码 0）。控制台不复制这个缺陷。
- CI：`.github/workflows/admin-ci.yml`（独立 workflow，paths `apps/admin/**`）。
- ESLint：`max-lines` 350 / `max-statements` 60（与 `apps/web` 同口径）；`src/components/charts/**` 因
  "一个图型一个文件、与 lieflat 模板一对一可追溯" 而豁免行数限制。

## 部署

```powershell
docker compose --profile console up -d --build admin-console   # → http://localhost:8089/console/
```

挂在 `console` profile 下：默认 `docker compose up` **不启动**它，因此 README 里原有的五服务验收口径不变。
控制台自带 `Dockerfile` + `nginx.conf`（**独立 server 块**，`apps/web/nginx.conf` 零改动）。

⚠️ 网关侧要动的两处（改一处必须改三处：`vite.config.ts` / `apps/admin/nginx.conf` / 文档）：
`/console/manage/` → java（剥前缀）、`/console/api/v1/` → python（剥前缀）；
且**每个 location 都要单独写 `proxy_set_header X-Request-Id $req_id`**（nginx 不继承），
漏写会让"浏览器回显 / Java 审计行 / Python 日志"变成三个不同 uuid。

## 目录

```
src/
  api/            envelope 客户端（双上游）、手写 DTO（dto/ 按域拆分）、端点封装
  stores/         auth（独立令牌 vv_console_*）/ alerts（顶栏角标轮询）
  router/         nav.ts（导航模型 + 权限）+ index.ts（守卫：未登录跳登录、无权限跳 403）
  layouts/        ConsoleLayout（只负责排布）
  components/
    layout/       ConsoleSider / ConsoleHeader / NavIcon
    common/       PageHeader / AsyncBlock / StatTile / StatusBadge / PermissionGate
    charts/       mono.ts（lieflat Mono 移植）+ ChartCard + 14 个图型组件
  views/          ops/ content/ moderation/ system/ dashboard/ + Login/403/404
```

## 已知缺口（**不得当成已实现**）

完整清单在 `docs/50 §15.2`（G-1~G-17），最要紧的三条：

- **G-17 内容创作 UI 未接**：增删改 + LRC 编辑的**后端已就位**，前端尚无表单——
  与工单同类的"有 API 没界面"，补齐前不得宣称"运营管理已闭环"；
- **G-2 下架暂无用户可见效果**：`songs`/`listening_materials` 的 `status` 还没有用户侧消费方，
  页面上有常驻提示说明这一点（不假装生效）；
- **G-3 停用账号后 Python 侧最长 15 分钟仍可访问**：Python 读不到 Java 的 `token_epoch`，
  故控制台令牌 TTL 收紧到 900s 作为缓解。

## 相关文档

| 文档 | 内容 |
|---|---|
| `docs/50` | 设计：权限模型 / 15 张表 / 端点 / 并发 / 日志 / UI / 图表 / ADR 修订申请 / 验证记录 |
| `docs/51` | 四路对抗拷问 + 逐条裁决 + 实现期自查缺陷 + 残余风险 |
| `docs/api/error-codes.md` | `46xxx` 管理端段（15 码） |
| `docs/api/envelope.md` | 控制台端点前缀、错误 `data` 的结构化例外、控制台鉴权专节 |
