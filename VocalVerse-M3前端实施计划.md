# VocalVerse M3 前端实施计划

> 范围：补齐 M3 全部前端占位页（英文歌练唱 · 个性化推荐 · 可视化报表 · 社区 · 管理端）
> 数据方式：**前端先行 + mock**（走 docs/13 §8 预览工作流，预留 API 接入点，后端落地后平移集成）
> 仓库根：`d:\vocalverse-main\vocalverse-main`（下文路径均相对此根）

---

## 1. 摘要

VocalVerse 前端 M1/M2 口语闭环已交付。本计划补齐 M3 试生产的全部前端页面：以 `apps/web` 现有三层样式体系（naive-ui + UnoCSS + tokens）与预览工作流为底座，用 **mock 数据先行** 交付五个模块的可用界面，每个模块预留 `api/<domain>.ts` 接口模块，后端契约落地后仅替换 data 来源即可接通（types 同步迁入 `generated/*.d.ts`，见 §7）。

五个模块（对应 router 现有占位路由）：

| 模块 | 路由（现状 → 目标） | 特色 |
|---|---|---|
| 英文歌练唱 | `/sing`（占位）→ `/sing` + `/sing/:songId` | D3 逐句音准对齐图（本项目特色扩展，docs/06 §9.4） |
| 个性化推荐 | `/recommend`（占位）→ 真实页 | 推荐 feed + 水平预测趋势 + 学习路径（docs/06 §9.5） |
| 可视化报表 | `/stats`（占位）→ 真实页 | 趋势/雷达/四指标看板 + 导出（docs/06 §9.1） |
| 社区 | `/community`（占位）→ 真实页 | 打卡 + 成绩卡片分享 + 动态流 + 点赞（docs/06 §9.6） |
| 管理端 | `/admin/*`（占位）→ 5 个真实页 | 用户/场景/歌曲(LRC)/工单/评价看板 |

---

## 2. 现状分析

### 2.1 已落地（M1/M2，直接复用，不重做）
- 框架：Vue 3.5 + TS strict + Vite 6 + pnpm，naive-ui + UnoCSS + 设计 tokens + Pinia + vue-router（`apps/web/src/main.ts`、`App.vue`）。
- 口语闭环：登录/入学测试/场景对话/评分报告/答辩导师，见 `views/PlacementView.vue`、`PracticeView.vue`、`ReportView.vue`、`DefenseView.vue`。
- 基础设施：`api/client.ts`（envelope 解析 + authHeaders）、`api/practice.ts`、`api/events.ts`（10 类埋点）、`audio/recorder.ts`（已参数化 `start(maxMs)`，唱歌用 180s）、`audio/sse.ts`、`stores/auth.ts`、`useECharts.ts`（ECharts 懒加载）、`useP5Wave.ts`、`useTurnTimers.ts`。

### 2.2 M3 占位现状（待替换）
`apps/web/src/router/index.ts` 中以下路由全部指向 `views/PlaceholderView.vue`（props 仅描述文字）：
- `/sing`（唱吧）、`/recommend`（推荐）、`/stats`（报表）、`/community`（社区）
- `/admin/users|scenes|songs|tickets|dashboard`（管理端）

`layouts/UserLayout.vue` 的 `nav` 数组当前只挂了「唱吧 (M3)」「报表 (M3)」，缺 `recommend`、`community` 入口。

### 2.3 可复用资产
- `composables/useECharts.ts`：ECharts 按需注册 + dispose + ResizeObserver，报表/看板直接复用。
- `components/LieflatChart.vue`：iframe + srcdoc 渲染单文件 HTML；`assets/lieflat/vv-admin-dashboard.html`（评价看板）、`vv-learning-report.html`（用户报表）为 M3 可视化提供「先出图」参考。
- 预览机制：`views/preview/registry.ts` + `router/preview.ts`（DEV 三元，生产零 chunk）。
- 预览页存量：`HomePreview.vue`（学习主页，推荐页可参考）、`AdminDashboardPreview.vue`（评价看板·ECharts）、`AdminUsersPreview.vue`（用户管理表）。

### 2.4 关键约束（计划必须遵守）
- **样式纪律**：页面 hex 只来自 `styles/tokens.ts` 或 uno.config 映射，0 硬编码；仅浅色模式；内容宽 1080 / 断点 768/1280。
- **可视化栈边界**（docs/13 §4）：ECharts 仅报表/看板；**D3 仅唱歌逐句音准对齐图一处**；P5 仅品牌动效；Three.js 禁止。
- **转义纪律**：AI/用户文本一律 `v-text`/插值，禁 `v-html`（LLM 输出 XSS）。
- **前端 DTO 纪律**：正常情况从 `generated/*.d.ts` 导入；M3 后端契约未落地 → 本次手写 DTO 集中在 `api/m3-types.ts`（标注「待契约化」），后端落地后迁走（docs/13 §7）。
- **懒加载**：>100KB 库按页动态 import（D3/ECharts 均如此）。

---

## 3. 总体方案

1. **mock 先行**：新增 `apps/web/src/api/mock/m3-data.ts` 集中提供五个模块的假数据（类型与未来接口 DTO 对齐）；各 `api/<domain>.ts` 模块当前从 mock 取数，内部结构 =「注释标注的待接端点 + mock 实现」，后端落地时只改实现不改组件。
2. **预览工作流**（docs/13 §8）：用户可见强视觉页（唱歌、报表、推荐、社区）先做 `views/preview/*` 高保真 → 视觉验收 → 平移为真实 `views/*.vue` 并删除预览页；管理端 CRUD 页复用已有 `AdminDashboardPreview`/`AdminUsersPreview`/lieflat HTML，直接落真实页（工作流已约定"含管理端模块走预览"，但存量预览已覆盖看板/用户管理，其余 CRUD 表页交互简单，直接实现并复用同一验收表）。
3. **路由/导航改造**：见 §5 各模块；`UserLayout.vue` nav 增补 `recommend`、`community`，去掉「M3」后缀。
4. **类型与接入点**：`api/m3-types.ts` 手写 DTO + 每个 `api/<domain>.ts` 顶部 TODO 标注对应后端端点（依据 docs/06 §9、docs/21 §2 端点清单），后端落地后 `pnpm gen:api` + 迁移。

---

## 4. 基础设施（先行，其余模块依赖）

### 4.1 新增 mock 数据层
- 新建 `apps/web/src/api/mock/m3-data.ts`：导出 `mockSongs`（歌曲列表含 LRC）、`mockLrc`、`mockSingAttempts`（逐句三围评分）、`mockRecommendations`（推荐 feed + 理由 + 水平预测序列）、`mockStats`（口语/唱歌趋势 + 雷达 + 四指标）、`mockCommunity`（动态流/打卡/点赞）、`mockAdmin`（用户/场景/歌曲/工单/看板数据）。
- 数据口径对齐 docs/06 §9：歌曲用公有领域/自创曲目占位；推荐 3 画像互异；四指标按 §9.1 定义命名。

### 4.2 手写 DTO 类型
- 新建 `apps/web/src/api/m3-types.ts`：`Song`、`SongLrc`、`SingLineScore`（音准/节奏/发音）、`SingReport`、`RecommendItem`、`LevelForecast`、`StatTrend`、`StatRadar`、`MetricBoard`、`CommunityPost`、`AdminUser`、`AdminScene`、`AdminSong`、`AdminTicket`、`DashboardMetric`。
- 每个类型顶部注释 `// TODO(契约): 后端 M3 契约落地后迁入 generated/*.d.ts`。

### 4.3 API 域模块骨架
新建（内部先用 mock，方法签名 = 未来真实签名）：
- `apps/web/src/api/sing.ts`：`fetchSongs()`、`fetchSongLrc(id)`、`submitSingAttempt(id, audio)`、`fetchSingReport(id)`
- `apps/web/src/api/recommend.ts`：`fetchRecommendations()`、`fetchLevelForecast()`
- `apps/web/src/api/stats.ts`：`fetchStatsOverview()`、`fetchTrend()`、`fetchRadar()`
- `apps/web/src/api/community.ts`：`fetchFeed()`、`toggleLike()`、`fetchCheckinStatus()`
- `apps/web/src/api/admin.ts`：`fetchUsers()`/`toggleUser()`、场景/歌曲/LRC CRUD、`fetchTickets()`/`updateTicket()`、`fetchDashboardMetrics()`

每个模块统一注释格式：`// NOTE: M3 后端契约未落地，当前返回 mock；接线后改 request()`。

---

## 5. 分模块实施

### 5.1 英文歌练唱（特色，最复杂，先做）

**路由**（`router/index.ts`）：
- `/sing` → `views/SingHubView.vue`（meta.title「唱吧」，requiresAuth）
- 新增 `/sing/:songId` → `views/SingView.vue`（meta.title「跟唱」，requiresAuth）

**文件**：
- `views/SingHubView.vue`：歌曲列表卡片（封面占位图形/名称/难度档/类型/BPM + 时长），点选进跟唱；复用 tokens 色调 + 胶囊按钮。
- `views/SingView.vue`：跟唱主流程——
  - 顶部：歌曲信息 + 参考旋律播放（mock 音频或静音提示）。
  - 中：LRC 歌词**逐句**高亮滚动，当前句录音按钮（`recorder.ts` `start(180_000)`，复用 `useTurnTimers` 计时）。
  - 结果：逐句三围评分（音准/节奏/发音）+ 综合分 `0.5·音准 + 0.2·节奏 + 0.3·发音`（docs/06 §9.4，公式抽成纯函数放 `composables/useSingScore.ts` 便于单测）。
  - 整首结束后跳 `SingView` 内嵌总结或报告。
- `components/sing/SingScorePanel.vue`：逐句三围评分卡（橙 `score` 色 + 深色文字）。
- `components/sing/PitchAlignmentChart.vue`：**D3 唯一落点**——逐句「用户音高轮廓 vs 参考旋律」对齐图（动态 `import('d3')`，卸载清理，失败降级 CSS 提示；仅此一处用 D3）。
- `composables/useSingScore.ts`：综合分计算 + 逐句分段纯函数（抽离便于 happy-dom 单测，docs/13 §5）。

**验收重点**：`docs/13 §8` 验收表（token 零硬编码/对比度/断点/空态）；D3 图不阻塞首屏（懒加载）。

### 5.2 可视化报表（高价值）

**路由**：`/stats` → `views/StatsView.vue`

**文件**：
- `views/StatsView.vue`：报表总览——Tab 切换「口语 / 唱歌」两套维度（口语：发音/语法/流利度；唱歌：音准/节奏/发音）+ 导出按钮（mock：`a[download]` 导出当前 JSON/CSV 摘要，标注后端落地后接真实导出）。
- `components/stats/TrendChart.vue`：成绩趋势折线（`useECharts` + LineChart）。
- `components/stats/RadarChart.vue`：多维雷达（`useECharts` + RadarChart，需在 `useECharts.ts` 增补 `RadarComponent` 注册）。
- `components/stats/MetricBoard.vue`：四指标 KPI 卡（CTR/完成率/互动率/跳出率，docs/06 §9.1），参考 `assets/lieflat/vv-learning-report.html` 布局。

**决策点**：可视化「iframe 渲染 lieflat HTML vs 移植 Vue SFC（ECharts）」——本计划取 **移植 Vue SFC + useECharts**（与 docs/13 §4「ECharts 报表」一致、易接真实数据）；lieflat HTML 仅作视觉参考，不保留双份同款（docs/13 §8「删除预览页」纪律）。此决策登记入计划，无需再拍板。

### 5.3 个性化推荐

**路由**：`/recommend` → `views/RecommendView.vue`

**文件**：
- `views/RecommendView.vue`：三区块——① 推荐 feed（场景/歌曲/听力素材卡片，带「推荐理由」标签）；② 水平预测趋势（「预估未来水平」折线，`useECharts`）；③ 学习路径（按当前档位/兴趣生成的任务列表，mock）。
- `components/recommend/RecommendCard.vue`：item 卡片（类型图标 + 难度 + 标签 + 推荐理由 + CTR 埋点 `recommend_impression`/`recommend_click`，复用 `api/events.ts` 的 `track`——注意 `events.ts` 的 `EventName` 现缺 `recommend_impression/recommend_click`，需**增补枚举**，对齐 docs/06 §9.1 十类）。
- `components/recommend/LevelForecastChart.vue`：`useECharts` 折线。

### 5.4 社区

**路由**：`/community` → `views/CommunityView.vue`

**文件**：
- `views/CommunityView.vue`：打卡条（今日是否 ≥1 次口语练习，mock 状态）+ 动态流（只读列表 + 点赞）+ 分享入口。
- `components/community/ShareCard.vue`：成绩卡片 **canvas 生成图片**（绘制总分/维度 + 品牌色）→ 下载（`a[download]`）+ Web Share API（`navigator.share` 存在则用，否则降级复制链接，不发任何敏感数据）。
- `api/community.ts`：`toggleLike` 乐观更新。

### 5.5 管理端

**路由**（`router/index.ts`，替换 `/admin` 下 `PlaceholderView`）：
- `views/admin/UsersView.vue`（用户管理：列表/查询/禁用启用/档案，复用 `AdminUsersPreview` 视觉）
- `views/admin/ScenesView.vue`（场景库：表格 + 上下架 + 增删改，naive-ui NDataTable/NModal）
- `views/admin/SongsView.vue`（歌曲库：歌曲 + LRC 词库编辑）
- `views/admin/TicketsView.vue`（工单：状态流转 新建/处理中/已解决/关闭）
- `views/admin/DashboardView.vue`（评价看板：四指标 + ECharts，复用 `AdminDashboardPreview`）

**说明**：管理端页面交互以 naive-ui 表格/表单为主（不新增 D3/P5），复用 `useECharts`；页面走 `AdminLayout`（已就绪）。「权限 = admin/user 角色」的访问控制为后端职责，前端仅保留 `requiresAuth`，实际角色守卫待 Java 落地后由 `stores/auth` 扩展（本计划不实现角色逻辑，登记为待办）。

---

## 6. 路由与导航改动汇总

- `router/index.ts`：
  - 上游用户端路由：`/sing`、`/sing/:songId`、`/recommend`、`/stats`、`/community` 五条替换 `PlaceholderView`。
  - `/admin` 下五条替换为 `views/admin/*` 真实页。
- `views/preview/registry.ts` / `router/preview.ts`：新增的预览页登记与路由；平移集成后按 docs/13 §8 **删除预览页 + 撤登记**。
- `layouts/UserLayout.vue`：`nav` 补 `{ label:'推荐', to:'/recommend' }`、`{ label:'社区', to:'/community' }`，并将「唱吧 (M3)」「报表 (M3)」去掉后缀。

---

## 7. 后端接入点预留（本次不实现后端，但登记接口名）

> 依据 docs/06 §9、docs/21 §2 端点清单；落地后仅替换 `api/*.ts` 内 mock 实现 + DTO 迁移。

| 前端模块 | 预留端点（`/api/v1/` or `/manage/`） | 归属 |
|---|---|---|
| sing | `GET /songs`、`GET /songs/{id}/lrc`、`POST /sing_attempts`、`GET /reports/{id}`（唱歌 scope） | Python |
| recommend | `GET /recommendations`、`GET /level-forecast` | Python |
| stats | `GET /stats/overview`、`GET /stats/trend`、`GET /stats/radar` | Python |
| community | `GET /feed`、`POST /posts/{id}/like`、`GET /checkin` | Python |
| admin | `GET/PATCH /manage/users`、场景/歌曲/LRC CRUD、`GET/PATCH /manage/tickets`、`GET /manage/dashboard` | Java |

- DTO 迁移路径：`api/m3-types.ts` → 后端契约快照刷新 → `pnpm gen:api` → `client.ts` 的 `ApiSchemas` 导入。
- SSE/唱歌逐句评分若走流式，复用 `audio/sse.ts`（后续扩展 `SseStreamEvent` 联合，登记为待办）。

---

## 8. 假设与决策

1. **范围**：仅前端；后端 M3（Python 唱歌评分/推荐/报表聚合、Java 管理端 CRUD）不在本计划。
2. **数据**：全部 mock 先行；不直连任何真实 AI 服务（严守 R1，docs/20 §2.4）。
3. **可视化裁决**：报表/看板用 ECharts（移植 Vue SFC），**不使用** lieflat iframe 双份方案；D3 仅唱歌一张图。
4. **唱歌发音评分复用口语引擎**（docs/06 §9.4），前端只需渲染「音准/节奏/发音」三围 + 综合公式，不前端实现评分算法。
5. **角色/权限**：管理端仅保留 `requiresAuth`；admin 角色守卫待 Java 落地后扩展（前端登记待办，不在本计划实现）。
6. **歌曲版权**：mock 歌曲一律公有领域/自创曲目占位，不粘贴真实歌词商用曲（docs/06 §9.7）。
7. **删除纪律**：预览页平移后必删 + 撤 registry 登记（docs/13 §8），不保留双份。

---

## 9. 验证步骤

每完成一个模块（或基础设施）在 `apps/web` 下自测：

```powershell
cd d:\vocalverse-main\vocalverse-main\apps\web
pnpm install
pnpm lint            # ESLint 9 flat
pnpm typecheck       # vue-tsc --noEmit（TS strict）
pnpm test:run        # vitest（新增 useSingScore、社区乐观更新等纯逻辑单测）
pnpm build           # vue-tsc -b && vite build（验证懒加载/D3 独立 chunk、生产零 Preview chunk）
```

视觉验收（docs/13 §8 验收表逐项）：
- 页面内 hex 全部来自 `tokens.ts`/uno.config（grep 无硬编码色值）。
- 文字级绿 `#15803D`；黄/橙配深色文字；正文 ≥12px。
- 间距 4 基元；内容宽 1080；圆角 8/12/胶囊；断点 768/1280 可用；空态 + 首次引导态齐全。
- 动效 ≤2 处/页；D3/ECharts 动态 import + 失败降级。
- `pnpm build` 后确认 dist 无 Preview chunk（生产扣除机制生效）。

手动走查（`pnpm dev` → `http://localhost:5173`）：
- 唱歌：进 `/sing` 选歌 → `/sing/:songId` 逐句跟唱 → 三围/综合评分 + D3 对齐图 → 结束；救援/空态可达。
- 报表：`/stats` 口语/唱歌 Tab 切换、趋势/雷达/四指标渲染、导出按钮可用。
- 推荐：`/recommend` feed + 水平预测图 + 学习路径；点击触发 `recommend_click` 埋点。
- 社区：`/community` 打卡、点赞乐观更新、成绩卡片 canvas 下载 + Web Share 降级。
- 管理端：`/admin/*` 五页表格/CRUD/看板渲染，侧边栏导航正常，无 `v-html` 渲染模型/用户文本。