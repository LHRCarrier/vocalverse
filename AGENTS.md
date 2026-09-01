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
- BUG 实测归档 `worklog/BUG实测/`，每条含 复现 / 根因 / 修复 / 验证 / 踩坑。
- 新增错误码先在 `docs/api/error-codes.md` 登记再用。

## 安全

- 禁止提交任何 Key / 密码 / 真实用户数据 / 模型权重 / 原始音频 / 商用音乐；密钥一律走 `.env`（`.env.example` 只放占位符，且默认值需与 `docker-compose.yml` 的回退值一致）。
