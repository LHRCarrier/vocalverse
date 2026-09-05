# VocalVerse · 工作日志

> 团队可见的工作记录（入库）。负责维护：LHRCarrier（组长）；其他成员需补充时经 PR 追加到 `VocalVerse工作日志.md`。
> 用途：按日记录项目关键改动、验证结果与踩坑；新记录追加在最上方。正式决策看 `docs/06-技术框架决策.md`（ADR 唯一权威）。

## 2026-09-05 晚2 场景对话改「先选场景再开工」开始流程（组长拍板）

- 触发（组长反馈）：① 删「点击录音（≤15s）」提示行；② 现状是进 `/m/chat` 立刻自动开题（气泡马上有开场白、连场景都没选）——要求：进页**先让用户选场景**，选好再进流程；
- 实现（用户给的产品形态，样式不变只换 Icon）：`stage: choose → intro → practice` 三态——
  - **choose**：无 sceneId 进页（Tab/中央 + 直达）→「先选一个场景开始」空态 + CTA（打开场景选择弹层），不建会话不自动开题；带回显 demo 无效（旧 boots 场景[0]）已废弃;
  - **intro**：选定场景（或直入 `/m/chat/:id`）→ 会话就绪 + 开场气泡（`speakable` 可点播、**不自动播**）→ 底部大按钮 = **播放图标**（新增 `MobileIcon play` 模板，样式与录音钮完全一致）；
  - **practice**：点播放 → `playOpening()`（播开场白，气泡喇叭 spinner 复用既有 playTts）→ 按钮**变回录音图标**，进入正常回合流；
- 边界：`/m/chat`（无参数，从口语 Tab/自由对话「场景选择」不带 id 时）走 choose；`/m/chat/:id` 直入 intro；页内切场景仍回 intro（重听开场白）；带 sceneId 的失败重试不丢场景；
- 埋点：不加新事件（开场播放复用既有气泡喇叭交互，不进指标口径）；
- 验证：前端 lint 0 warning / typecheck / vitest / build 全绿；后端零改动。
- **BUG 修复（同日，组员复测）**：home 点口语 Tab 未选场景直接出题（机场·值机开场白）——根因：**vue-router 可选参数 `:sceneId?` 无值时 params.sceneId = `''`（空串）而非 undefined**（node 实测 `r.resolve('/m/chat').params → {"sceneId":""}`），旧判定 `!== undefined` 放行 → `boot()` → `Number('')=0` 找不到 → `?? scenes[0]` 落默认场景；修复：判定补 `&& !== ''`，且 watch 补 `:id → 无 id` 回退到「先选场景」态（resetToChoose）。
- **组员反馈（同日）**：「先选一个场景开始」空态文字说明太多 → 标题 + 副文案全部删除，只留线稿锚点 + 「选择场景」按钮。
- **组员反馈（同日）**：空态出现两个「选择场景」入口（空态按钮 + 底部功能行）——按「不重复不浪费」原则：**choose 态隐藏底部功能行的「场景选择」**（选完场景后的页内切场景入口保留）；空态整体垂直居中，按钮落位在**视觉中点下方**（`.u-empty--center`：min-height 视口-顶栏-dock、按钮 margin-top 32px）。
- **组员指正（同日）**：**自由对话页功能行出现的「场景选择」是设计失误**——场景选择只属于场景对话页（先选场景流程）；自由对话功能行删「场景选择」（含 sheet 挂载与带 scene_id 跳转分支），只留「场景对话」（切回 `/m/chat` 由该页自己走选场景流程）。
- **组员反馈（同日）**：自由对话的「场景选择」换成**「新对话」**（清空当前对话记忆重新开始；空态禁用；`free_chat_reset` 事件由预留恢复触发）；顺带修潜在 bug：`abort` 由 const 改 let，新对话后重建 AbortController（abort 过的 signal 复用会导致下一回合立即失败）。
- **组员反馈（同日）**：自由对话空态提示文字（标题「自由对话」+ 副文案）也全部删掉——与场景对话空态同标准，只留插画并垂直居中（`.u-empty--center`）。
- **组员反馈（同日）**：加载动画用**墨水下落效果**（组员给的 css-rain-bg 方案，36 层 radial-gradient 交错点阵 + 150s 线性循环）——适配纸面主题（面板底 `--u-paper`、墨色保留组员 `#272257`），落地 `.u-load` 两个场景：① 场景对话进场景加载态（替换原「正在进入场景…」图文）；② 自由对话「AI 思考中」状态改为 44px 雨条动画；`prefers-reduced-motion` 关闭动画；等组员视觉验收。
- **组员澄清（同日）**：墨雨原意是「**各个功能页之间/APP 启动**」的整幅加载动画，不是页内加载；且被启发后拍板改为**更轻的方案**：**一条 3px AI 状态线**（`.v-line`）——静默 = 纯黑一条线、AI 处理中 = **彩色流光**（repeating-gradient 四色 96px 周期无缝循环）、出错 = 纯红；落地两页顶部（场景对话：loading/busy → 流光，errorMsg → 红；自由对话：sending → 流光，errorMsg → 红）；页内加载回归极简（场景对话加载态 = 居中插画，仅状态线表达处理中）；**.u-load 墨雨 CSS 保留未引用**（预留给启动页/整幅加载，注释已标明）。
- **组员反馈（同日）**：彩色流光效果不佳——参照墨雨的自然过渡，改为**浅→深平滑彩虹渐变**（8 档色标无硬边、头尾同色 `#cdd7fe` → 100% 循环无缝；`background-size:200%` + `background-position:0%→200%`）；速度降为 2.2s。
- **组员反馈（同日）**：场景选择弹层显示「暂无场景，请先执行 seed」——**排查结论：DB 有 8 场景、接口正常，是前端 access token 过期**（1h TTL；旧代码只在启动时 bootstrapAuth 刷新一次，会话中途 401 无兜底）；修复三层：① `client.ts` 加 **401 静默续期**（注入式 `setAuthRefresher` 防循环依赖，防重入，refresh 后重试一次，docs/18 F3 落全）；② `stores/auth.ts` bootstrapAuth 注册 refresher；③ 场景弹层与场景页 boot **区分「加载失败」与「无数据」**——失败 → 可操作提示 + 重试按钮，不再误报 seed（seed 提示只在接口 200 且列表为空时显示）。
- **组员反馈（同日）**：移动端容器背景换**点格背景**（组员给的 dot-grid 方案：双 radial-gradient 交错点阵、48px 网格）——落 `.u-phone`，点色用 token 墨色 5% 代替纯黑（与纸面底一致）；底部输入/功能栏 `u-fc-bar-wrap` 由纯纸色改透明让点格透出；等组员视觉验收（不合意可调点色/间距）。
- **组员反馈（同日）**：点格浓度 5% → **20%**（看效果；参数就三处：点半径 5% / 淡出 6% / 网格 48px）。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 晚 口语 Hub 收敛删除：两页聊天模式 + 功能行互切 + 场景选择弹层

- 触发（组长反馈）：`/m/speaking`（口语 Hub）不再需要——全部收敛成聊天页模式：点击「场景对话」按钮直接切换；功能行中间的「新对话」改为「场景选择」；「语速」按钮去掉；
- 拍板（组长）：删 Hub 页（路由 `/m/speaking`+组件+Tab 指向）；口语 Tab 与中央 + 直达 `/m/chat`（默认场景）；预置场景列表平移到「**场景选择**」底部弹层（`components/mobile/ScenePickerSheet.vue`，两页共用，懒加载场景列表）；自由对话页功能行 = `[场景对话] [场景选择]`；场景对话页功能行 = `[自由对话] [场景选择]`（页内切场景：`watch route.params.sceneId` → 重置状态重启会话）；语速（含 `/tts` rate 接线）与「新对话」移除；
- 边界保持：场景对话不直入随机场景——「场景选择」由用户点选后才进 `/m/chat/:id`（原 Hub 场景列表语义原样保留）；
- 埋点：`free_chat_switch{to:scene, scene_id?}` 保留触发；`free_chat_reset`/`free_chat_rate` 因功能改版**暂不触发**，白名单（CHECK 15 类）与 docs/06 §9.1 预留登记（避免再造迁移回退）；
- 验证：前端 lint 0 warning / typecheck / vitest / build 绿；后端未动（0 变更，无迁移）；本改动无 OpenAPI 影响；
- 注：上一轮「语速三档 + 新对话收编」的 code 已随本轮提交历史保留在仓库（git 历史可回溯），但 UI 不再暴露。
- **组员反馈修正（同日）**：① `/m/free-chat` 返回键用 `router.back()` 会撞 `/demo`（history 依赖，直进 URL 场景可复现）→ 改为确定性导航：自由对话返回 → `/m/chat`、场景对话返回 → `/m/home`；② `/m/chat` 排版错乱——录音钮/录音标签为 `position:fixed`，功能行却是文档流元素排到页面中部 → 功能行改 `.u-tb--dock`；③ 组长再反馈：录音按钮要"到上面去" → 初版调 fixed 坐标（功能行贴底/钮上移），**但标签仍被按钮遮挡**（多 fixed 元素各自定位难保不叠）→ **彻底重构为单一固定容器 `.u-chat-dock`**（标签→录音钮→功能行 flex 自然堆叠，指针穿透容器、子元素恢复），内容区留白 216px；再调坐标的教训：fixed 元素多了以后坐标对表不可靠，改用容器布局。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 自由对话页 Grok 式改造（3 子代理评审 → 建议落地 → 提交）

- 触发（组员截图）：①「新对话」浮动按钮压住第一条用户气泡（P0 遮挡）；② 用户指 X·Grok 客户端作参照——底部一排功能卡切换产品能力，要求同款落我们的功能；并明确「先派子代理出设计缺陷报告再动手」；
- 评审：3 个子代理并行（布局交互 / 视觉组件映射 / 功能信息架构），交付三份只读报告，要点：
  - **P0** 浮动 `u-fc-reset--float`（absolute top:24/right:16/z-index:20）压内容 → 收编进底部功能行（顶栏三段式被否：上轮已按组长反馈删标题）；
  - **P1** `.u-content` 140px 底部留白死区（本页无浮动 Tab 栏）+ `min-height:100vh` 导致整页滚动、输入栏被顶出 → `100dvh` + `.u-fc-box{flex:1;min-height:0}` 内部滚动；
  - **P2** 触控 <48dp（圆钮 38px）、内联自造色 `#16303a`（= `--u-dark-teal` 重复写死）、placeholder 对比度、字号 12.5/14.5/11.5 非网格、`.u-fc-mic` 无 disabled 态；
  - **功能行候选裁定**（IA 代理）：放**自由对话页输入栏上方**（非 Hub/非全局导航）；`场景对话`（跳 Hub 保边界，不直入随机场景）｜`新对话`（空态禁用）｜`语速`（`+0%→+15%→-25%`，后端 `/tts` rate 已支持，纯前端接线 + localStorage）；**不做**：角色预设（后端 `_SYSTEM_PROMPT` 全静态）、语音/打字模式开关（双通道已并存，开关冗余）、评分/报告（违反 MVP 无评分契约）、音色（属「我的-设置」口径）；
- 落地：功能行 `.u-tb` 浅色 chip（track 底 + ink 反白选中态语义，64px 高）；输入栏主/次钮——麦克风 = 右侧 48px ink 英雄钮（voice-first，录音态转 error 红）、发送 = 48px track 次钮；删浮动「新对话」；头像 token 化`var(--u-dark-teal)`；字号回收；埋点 3 类 `free_chat_switch/reset/rate`（EventTypes + **迁移 0006** CHECK 12→15 + docs/06 §9.1 / docs/14 §6.3 登记）；
- 验证：前端 lint 0 warning / typecheck / build 绿；后端 ruff+format+全量 pytest 绿（埋点 15 类逐类落库断言）；alembic 单头 0006 且本地 PG 已应用；契约无 OpenAPI 变更（events 路由 schema 未动，快照零 diff）；
- 坑：① EventTypes 注释行 103 字符触发 E501（注释也计列宽，重排）；② docs/31 §3 token 表指向 mobile-soft.css（`--s-*` 天蓝）与已落地 mobile-uic.css（`--u-*` 纸灰）不一致——文档漂移已记录，待补（不在本轮范围）。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 口语界面 3 项：气泡尾巴修复 + 进页自动播修复 + 口语 Hub 与自由对话（最小可用版）

- 触发（用户截图 + 拍板）：① AI 气泡尾巴长在气泡**左下角**（`.u-bubble--ai::before` bottom:10px），头像在行首——参照微信应从**头像垂直中心**发出；② 进 `/m/chat` 页 `boot()` 对开场白自动 `playTts()`，**进页必响**；③ 用户认为「口语」Tab 定义不清——口语应 = **场景对话（固定出题）+ 自由对话（LLM + TTS）**；
- 真相澄清：自由对话此前**只有 LLM 框架 + Agent Lab 测试台**（2026-09-03：dev-only、默认关闭、文本输入、不建会话不入库），并非产品页；会话 kind 也只有 `dialog | defense`；
- 拍板（组长）：按**最小可用版**落地；自由对话输入 = **语音 + 打字都要**，输出 = LLM 流式文本 + 回合后 TTS 自动播报（喇叭可重听）；MVP 不做评分/报告/入库（刷新即失忆，二期见 docs/14 §12.4）；
- 产出：
  1. **气泡尾巴**：`bottom:10px` → `top:18px`（头像 44px + 2px 顶距 → 中心 24px；菱形 12px 中心对齐），圆角 `16px 16px 16px 4px` → 全 `16px`；`played` 语义改名 `speakable`（喇叭出现条件）；
  2. **自动播**：开场白删自动播放（喇叭立即可点）；录音提交后的回合语音仍自动播放（跟读流程需要，用户边界确认）；
  3. **后端** `routes/free_chat.py`：`POST /api/v1/free-chat/turn`（multipart `audio`/`text` + `history` JSON，至少其一）→ SSE 子集 `user_transcript→text_delta*→turn_end`；无状态 LLM 转发器（TurnRunner 复用、system 全静态人设、无 corpus）；限流 asr+llm；**进 OpenAPI 契约**（快照 + gen:api 已同步）；
  4. **前端**：`/m/speaking` 口语 Hub（场景对话/自由对话两模式卡 + 预置场景列表）· `/m/free-chat`（气泡同款 + 文本输入 + 麦克风 ≤15s + 「新对话」重置）；TabBar 口语与中央 + → `/m/speaking`；埋点 `free_chat_open`/`free_chat_turn{audio}`（EventTypes + **迁移 0005** 扩 `events.event_type` CHECK 10→12 类；docs/06 §9.1 登记）；
  5. **文档**：docs/14 §12（定义/接口/前端/分期）+ §6.3 埋点、docs/06 §9.1、docs/10 注记、docs/30 W11/W12；
- 验证：后端 ruff+format+全量 pytest 绿（新增 `test_free_chat` 6 用例；12 类事件逐类落库）；前端 lint 0 warning / typecheck / vitest 19 / build 绿；**CI 同款契约对账**（app.openapi() vs 快照）一致；alembic 单头 0005 且已应用到本地 PG；**真机链路实测**：Java 登录取 JWT → 自由对话打字轮（真实 DeepSeek 流式 + turn_end）→ 第二轮带 history（turn_index=2、上下文连续）→ 空输入 422；
- 踩坑：① uvicorn `--reload` 多轮重载后子进程僵在 lifespan → 杀掉重启 dev-up 恢复；② `refresh-openapi.ps1` 导出的 Java 快照与库内差异只有 `servers` 字段 + 格式化（本地 springdoc 与 CI 生成路径不同）→ **回滚 Java 快照**，只提交 Python 快照 + 生成类型；③ 埋点事件是 **DB CHECK** 白名单：只改前端 `EventName` 会静默丢事件，后端 `EventTypes` + 迁移缺一不可（本次一并登记 docs/06-09.1、docs/10）；
- **组员反馈修正（同日晚，截图验收）**：① 自由对话页左上「自由对话」标题与返回钮重叠 → 删除标题（保留返回钮 + 右上角浮动「新对话」）；② 输入栏发送钮渲染成空圆圈——`MobileIcon` 联合类型早声明了 `'arrow'` 但**从未实现模板** → 补模板（code 审查盲区：类型允许 ≠ 可渲染）；③ 口语 Hub 无返回导航 → 补 `.u-back--float` 返回钮（与其它移动页一致）。

—— 执行人：组长 LHRCarrier（AI 代工整理）

## 2026-09-05 移动端场景对话 2 个 UI 修：气泡尾巴位置 + 进页自动播开场白

- 触发（用户截图反馈）：① AI 气泡尾巴长在气泡**左下角**（`.u-bubble--ai::before` bottom:10px），而头像在行首——参照微信，小尾巴应从**头像垂直中心**发出；② 进 `/m/chat` 页 `boot()` 对开场白自动 `playTts()`，**进页必响**，像微信应点喇叭才出声；
- 修复：`apps/web/src/styles/mobile-uic.css`——尾巴 `bottom:10px` → `top:18px`（头像 44px+2px 顶距 → 头像中心=距气泡顶 24px；菱形高 12px 中心对齐 24px），气泡圆角由 `16px 16px 16px 4px` 改全 `16px`（4px 小角是配旧左下尾巴的切角，尾巴上移后残留显得像缺口）；`MobileSpeakingView.vue`——开场白删除自动播放、气泡直接 `speakable:true`（喇叭立即可点）；`played` 语义改名 `speakable`（「该气泡有可播语音 / 喇叭出现条件」，原语义是「首次完整播过才有重听按钮」）；
- 边界（按用户意图保留）：**录音提交后 AI 回合语音仍自动播放**（跟读流程需要：先听后说）；若也要改成全手动点播，一行 `playChunk` 可再调；
- 验证：`pnpm lint` / `pnpm typecheck` / `pnpm test:run` / `pnpm build` 全绿。

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
