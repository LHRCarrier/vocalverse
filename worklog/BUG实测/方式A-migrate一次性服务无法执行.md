# 方式 A `migrate` 一次性服务无法执行 · BUG 实测记录

> 对应模块：方式 A（compose）启动链 `docker compose up -d migrate`（docs/11 S-8 / docs/18 拍板 10）
> 记录规则：**复现过程 / 根因 / 修复过程 / 修复情况 / 踩坑记录**，带时间与负责人。

---

## BUG：`docker compose up -d migrate` → 容器退出码 1，迁移/seed 从未执行

- **发现时间**：2026-09-04（PR#27 方式 A 容器实测时发现；此前被「Python 服务能起」掩盖——迁移失败不阻塞其他服务）
- **负责人**：LHRCarrier（found & fixed）
- **严重级别**：P1（方式 A 全新环境：表结构/演示数据缺失，API 请求全 500；「一键起」名不副实）
- **是否受 PR#27 影响**：否，既有缺陷（compose 自基线即如此，测试/CI 均未覆盖——docker-build 只 build 不 run，migrate 属运行期路径）。

### 复现过程

```powershell
docker compose up -d --build   # 或单独 docker compose up -d migrate
docker compose logs migrate
```

实际结果（修复前，逐层暴露）：
1. `sh: 1: alembic: not found`（命令裸 `alembic`，镜像内依赖在 `.venv/bin`，PATH 不含）；
2. 补 `uv run` 前缀后 → `Traceback ... IndexError: 4`（`app/db/seed.py:25` `Path(__file__).resolve().parents[4]`：容器布局 `/app/app/db/seed.py` 只有 4 级父目录）——**与 PR#27 的 `main.py parents[3]` 同类容器路径假设**；
3. 再补路径防护后 → `FileNotFoundError`（种子数据 `data/seed/scenarios.json` 在仓库根，镜像构建上下文仅 `services/python`，容器内无）。

### 根因分析

| 层 | 根因 |
|---|---|
| ① | `docker-compose.yml` migrate 命令未加 `uv run` 前缀（python-api 的 CMD 有，migrate 漏了） |
| ② | `seed.py` 按「本地仓库布局」硬推根目录（`parents[4]`），容器 `WORKDIR /app` 布局无第 5 级父目录 |
| ③ | seed 数据文件位于仓库根 `data/seed/`，不在服务构建上下文 `services/python` 内，镜像不含、无挂载 |

### 修复过程（2026-09-04 · LHRCarrier）

1. `docker-compose.yml` migrate：`alembic ...` → `uv run alembic ...`、`python -m app.db.seed` → `uv run python -m app.db.seed`；
2. `docker-compose.yml` migrate 增加挂载 `./data/seed:/app/data/seed`（与 `./data/audio` 同约定）；
3. `app/db/seed.py`：`try/except IndexError` 布局感知——本地取 `parents[4]`=仓库根；容器回退 `Path("/app")`（挂载点与之一致）。

### 修复情况（2026-09-04 验证）

| 检查项 | 结果 |
|---|---|
| `docker compose config --quiet`（YAML 解析，AGENTS.md 同款要求） | ✓ 通过 |
| `docker compose build migrate` | ✓ 构建成功 |
| `docker compose up -d migrate` → `docker compose logs migrate` | ✓ `alembic.runtime.migration Context impl PostgresqlImpl` + `[seed] scenarios …/placement_questions …（跳过已存在）`，容器退出码 0 |
| 幂等性 | ✓ 二次运行 seed 跳过已存在（不覆盖管理员编辑） |
| `ruff check` / `format --check` / `pytest tests/db/test_seed_recommend.py tests/test_seed.py` | ✓ 全绿（6 passed） |

### 踩坑记录

1. **migrate 失败不阻塞 compose 其他服务**：`docker compose up -d` 时 migrate 退出码 1 不会标红整个栈——**「健康」不等于「迁移完成」**，全新环境验收需单独看 migrate 日志与表数量；
2. **「容器路径假设」同类坑第三次出现**：`main.py parents[3]`（PR#27 复审 P0）→ `seed.py parents[4]`（本次）→ 教训：凡 `Path(__file__).resolve().parents[N]` 推断仓库根，必须带 IndexError 防护或改用显式配置/环境变量（如 `APP_REPO_ROOT`），并补一次真实容器运行验证（CI build 覆盖不了）；
3. **compose 命令与镜像运行时前缀不一致**：python-api 用 `uv run uvicorn`，migrate 裸调用——凡在镜像里跑项目命令必须 `uv run` 前缀（或激活 venv），此点建议写进 docker-compose 注释。

—— 执行人：LHRCarrier
