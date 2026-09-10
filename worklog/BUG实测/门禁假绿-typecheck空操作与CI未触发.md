# BUG：门禁假绿——`pnpm typecheck` 是恒绿空操作 + 前端/Java CI 无自动触发

- **发现**：2026-09-10 · 唱歌模块七路拷问（E 路：测试质量与门禁有效性）；主代理**对照实验**复核（本次）。
- **修复**：2026-09-10 · 执行人：AI 代签（正式署名待组长确认）。
- **影响面**：**全仓前端**（不限唱歌模块）——团队提交前门禁与 CI「Typecheck」步骤、以及所有以"typecheck 全绿"为依据的验证结论（含本项目 2026-09-10 多条 worklog 记录）；`java-ci`/`frontend-ci` 在 `main` 上的自动验证面。

## 复现

```powershell
cd apps/web
npx vue-tsc --noEmit --listFiles | Measure-Object -Line   # → 0 行，exit 0（一个文件都没检查）
npx vue-tsc --noEmit -p tsconfig.app.json --listFiles | Measure-Object -Line  # → 2257 文件
```

**对照实验（主代理执行，2026-09-10）**：向 `src/api/sing.ts` 注入一行类型错
`const __typecheck_probe: number = 'definitely-not-a-number'` 后：

| 命令 | 结果 |
|---|---|
| `npx vue-tsc --noEmit`（= 旧 `pnpm typecheck`） | **exit 0 / 输出 0 行**（完全没看见类型错） |
| `npx vue-tsc -b`（= `pnpm build` 的第一段） | **exit 2**：`src/api/sing.ts(205,7): error TS2322: Type 'string' is not assignable to type 'number'` + `TS6133` |

（探针已移除，`vue-tsc -b` 复跑 exit 0，工作树干净。）

CI 侧：`frontend-ci.yml` / `java-ci.yml` 的 `on:` 只有 `pull_request(paths:…)` + `workflow_dispatch`，**无 `push`**（python-ci 有 `push: branches:[main]`）；且唱歌模块所在分支 `feat/sing-m3` 未推送（`git ls-remote --heads origin` 无该分支）→ `gh run list` 显示 frontend-ci 自 **2026-09-07（PR #31）** 起再无自动运行。

## 根因

1. **命令错一层**：`apps/web/package.json` 的 `typecheck` 是 `vue-tsc --noEmit`，而根 `tsconfig.json` 是 **solution 配置**（`{"files": [], "references": [app, node]}`）——非 `-b` 模式下 `files: []` 即"没有输入文件"，TypeScript 正常退出（不报错也不检查）。真正跟 references 的是 `vue-tsc -b`（`pnpm build` 用的），所以 build 反而成了唯一的类型门禁。
2. **归因偏轻**：当日 worklog「踩坑②」把同一现象解释为"typecheck 不构建 project references（所以没查出测试夹具缺字段）"——真实情况更强：它**任何文件都不查**；按旧归因去修（例如只补 vitest 配置）不会触及根因。
3. **CI 触发面缺口**：本仓 `pull_request` 触发不可靠（历史已登记），python-ci 用 `push(main)` 兜底，而 frontend-ci/java-ci 没补 → `main` 上的前端/Java 代码**零自动验证**；本模块又在未推送分支上，等于"本地自测 + 人工 review"。

## 修复

1. `apps/web/package.json`：
   ```json
   "typecheck": "vue-tsc --noEmit -p tsconfig.app.json && vue-tsc --noEmit -p tsconfig.node.json"
   ```
   选型说明：**不用** `vue-tsc -b`（会写 `*.tsbuildinfo`/产物，且已由 `build` 覆盖），改显式两个 project + `--noEmit`（无副作用、覆盖 app + node 与 build 同面）。
   验证副作用：改动前后 `tsconfig.app.tsbuildinfo` mtime 未变（未被改写）。
2. `.github/workflows/frontend-ci.yml` 与 `java-ci.yml`：补 `push: branches: [main]`（paths 与各自 pull_request 一致），与 `python-ci.yml:10-14` 对齐；并在 frontend-ci 的 Typecheck 步骤加注释，写明"本步首次成为真实门禁，若突然红先查历史类型错，不要改回空操作"。
3. 依 AGENTS.md「改 `.github/workflows/*.yml` 后必须本地 `yaml.safe_load` 解析」：5 个工作流全部解析通过（含 trigger 键核对）。
4. **未做（需人操作）**：推送 `feat/sing-m3` / 开 PR —— 需要写权限与组长确认（见"遗留"）。

## 验证

| 项 | 结果 |
|---|---|
| 新 `pnpm typecheck` 于干净工作树 | ✅ exit 0 |
| 注入类型错后新 `pnpm typecheck` | ✅ **exit 2 + TS2322/TS6133**（红线成立） |
| 同一注入下旧命令（对照） | ❌ exit 0 / 0 行（证明修的是"空操作"） |
| 移除探针后复跑 | ✅ exit 0；`grep __gate_probe` = 0；`git diff --numstat` 仅收藏相关 6 hunks |
| 前端全量门禁（lint / typecheck(新) / test:run / build / check-bundle.mjs） | ✅ 163 passed + bundle exit 0 |
| 5 个 workflow `yaml.safe_load` | ✅ 全部 OK（frontend-ci/java-ci 已含 push） |

## 踩坑

1. **"门禁存在"≠"门禁生效"**：任何门禁都应能回答"它检查了什么、漏什么"（本例用 `--listFiles` 一次问清）；命令语义变了（tsconfig 由单工程改 solution）而脚本没跟着改，就会出现永久假绿。
2. **同一条现象，归因深浅决定修不修**：把"没查出测试夹具"写成"盲区"，看起来像次要问题；写成"永远不检查任何文件"，才是必须当天修的 P0。
3. **仅 `pull_request` 触发的 CI 在"PR 触发不可靠"的仓库等于没有 CI**：兜底触发（`push(main)`）应与已修复的 python-ci 一致。
4. **改 workflow 必须本地解析 YAML**（AGENTS.md 硬性要求）：未加引号的标量里出现 `": "` 会让整份工作流非法且**静默不执行**。

## 遗留

1. **推送分支 / 开 PR**（需组长或具备写权限者执行）：否则新门禁只在本地与后续 `main` 上生效，本模块的历史代码仍未过 CI。
2. 本项只修"空操作"与"触发面"；**覆盖盲区**（错误分支、状态机窗口、mock 与真件差异等 E 路 P1 清单）仍待按 `local/唱歌模块全链路拷问报告-2026-09-10.md` §4-E/§6 逐条补测。

—— 执行人：AI 代签（正式署名待组长确认），2026-09-10
