# AGENTS.md · VocalVerse 协作约定

面向在本仓工作的 AI 助手/代理。人类约定见 `README.md` 与 `docs/06-技术框架决策.md`（ADR 唯一权威）。

## 审 PR 的硬性要求

1. **必须留 PR comment。** 审完一个 PR，结论要以 `gh pr review` 或 `gh pr comment` 落到 PR 上，不能只写在聊天里或只体现为 commit message —— 队友看不到聊天记录。
   - 有阻断性问题 → `gh pr review --request-changes`；
   - 只是建议 → `gh pr review --comment`；
   - 认可可合 → `gh pr review --approve`。
2. **结论要能被复现。** 报缺陷就给出触发路径（点击序列 / 请求序列），能写成测试的就写成测试，并说明该测试在修复前是否失败——「测试全绿」本身不构成证据。
3. **先查 CI 是否真的跑过。** `conclusion=failure` 且 `jobs.total_count=0` 表示工作流启动失败（一个 step 都没执行），不是某个测试挂了。见工作日志踩坑 24/25。
4. **改队友的 PR 分支前先确认仓库关系。** `gh pr view N --json isCrossRepository,maintainerCanModify`：
   - 同仓分支 + 有写权限 → 直接推该分支，PR 原地更新，不产生新 PR；
   - fork 且 `maintainerCanModify=false` → 只能新开 PR 把 base 指向对方分支，或用 review suggestion。

## 提交与验证

- Conventional Commits，中文正文；**代码 / 测试 / 文档分开 commit**，不 squash 粘连。
- 提交前跑对应门禁（本地）：
  - 前端 `apps/web`：`pnpm lint && pnpm typecheck && pnpm test:run && pnpm build`
  - Python `services/python`：`uv run ruff check . && uv run ruff format --check . && uv run pytest -q`
- **改 `.github/workflows/*.yml` 后必须本地 `yaml.safe_load` 解析一遍**：未加引号的标量里出现 `": "` 会让整份工作流非法且静默不执行。

## 记录纪律

- 主线日志 `worklog/VocalVerse工作日志.md`，新记录置顶。
- **App 端 UI/设计记录走安卓日志**：凡 `apps/web` 移动端真形态（`/m/*`）及其他 App 相关的**界面/交互/视觉**记录，一律写 `worklog/安卓开发日志.md`（组长 2026-09-08 定规；AI 代工新记录同理，不得放主线日志）；Web/后端/全局事项留在主线日志；混合条目（前后端联动功能）拆分——UI 部分入安卓日志，后端/迁移/契约部分留主线。
- BUG 实测归档 `worklog/BUG实测/`，每条含 复现 / 根因 / 修复 / 验证 / 踩坑。
- 新增错误码先在 `docs/api/error-codes.md` 登记再用。

## 工作流程（组员执行规范 + 合入检查项，2026-09-07 固化）

> 本节规范对象：**在本仓提交工作的所有成员**（人类/AI 代工时由成员认领）。AI 助手在审 PR/合入时按本节逐项检查（与「审 PR 的硬性要求」配套），发现违例以 PR comment 要求补充/整改。

1. **worklog 即时时 + 署名**：每完成一段独立工作（代码改动/文档产出/验证结论），立即在 `worklog/VocalVerse工作日志.md` **置顶追加**该段记录——不攒到一天结束、不做完不留痕。
   - **每段记录必须带执行人署名**（小节标题带名字，或正文末「—— 执行人：XXX」；用 GitHub ID 或真名，以 `docs/04`/项目分工文档登记为准）；
   - **署名不确定/不知道时，先问组长，禁止猜测或留空**；
   - 个人过程性内容（未定稿草稿/仅自用）不进主线日志。
   - 审 PR 检查项：涉及功能/文档的 PR，其对应记录已在主线日志置顶且带署名，否则 comment 要求补。
2. **文档放置检查**：工作结束前逐项核对产出物去向，不得默认丢仓库根：
   - **个人过程性文档**（草稿/临时/仅自用）→ `local/`（gitignore，不入库）；
   - **供团队阅读且有长期价值** → `docs/`，并**按模块分子目录放置**：
     - 音频/语音链路类 → `docs/audit/`（现成模块：语音链路审计 V1/V2、采集模板等）；
     - API 契约/错误码/接口规格类 → `docs/api/`（现成模块：envelope、error-codes）；
     - 需求/设计/评审/规划类 → `docs/` 根（沿用 00~21 序号体例及位置约定）；
   - **新增模块目录/文档须在 `README.md`「文档索引」登记一行**；
   - 归属不明先问组长再落位；**禁止把产出物散落在仓库根或 services/ 等非文档目录**（历史踩坑：6 份拷问报告曾误落仓库根，见工作日志踩坑 27）。
   - 审 PR 检查项：PR 新增文档按上述归类落位，否则 comment 指出正确位置。
3. **新功能联调测试页（预览机制 · 可删无影响，2026-09-03 固化为强制项）**：凡开发**涉及前后端联动的新功能**，必须按仓库既有预览机制提供**团队联调测试页**（首例模板：Agent Lab，2026-09-03 · PR#26——前端 `AgentLabPreview.vue` + 后端 `app/api/routes/agent_lab.py`，新页按此克隆改造），并满足：
   - **前端走 docs/13 §8 预览工作流**：`apps/web/src/views/preview/` 新增页面 + `views/preview/registry.ts` 登记一行 + `router/preview.ts` 路由一行——dev-only 子树，生产构建 Rollup 整枝剔除（零体积零路由，用户不可见，不进任何用户导航）；
   - **后端 test-only 接口**：与页面配套，`include_in_schema=False`（OpenAPI 契约快照零 diff，CI 对账不受影响）、无表/无迁移/不碰既有路由、**默认关闭**（`*_enabled=False` 时路由不注册 → 404，生产零暴露；配置项注释「生产禁止开启」）；
   - **可删无影响**：删除清单（删哪些文件、哪几行）写入接口文件尾注释；删除后 pytest 全量绿 + 契约快照零 diff + 前端 lint/typecheck/build 绿；
   - 页面内注明依赖开关与开启方式（如 `APP_AGENT_LAB_ENABLED=true`），便于组员直接用；
   - 审 PR 检查项：涉前后端联动功能的 PR，缺联调测试页或删除清单 → comment 要求补（测试页随功能分支合入，验收后无需保留的功能页按删除清单移除并保持门禁绿）。

## 安全

- 禁止提交任何 Key / 密码 / 真实用户数据 / 模型权重 / 原始音频 / 商用音乐；密钥一律走 `.env`（`.env.example` 只放占位符，且默认值需与 `docker-compose.yml` 的回退值一致）。
