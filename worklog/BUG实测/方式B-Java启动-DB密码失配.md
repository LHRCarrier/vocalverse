# 方式 B Java 启动失败（DB 密码失配）· BUG 实测记录

> 对应模块：方式 B 本地开发（`mvn spring-boot:run`，端口 8080）→ `services/java` + postgres 容器
> 记录规则：**复现过程 / 根因 / 修复过程 / 修复情况 / 踩坑记录**，带时间与负责人（与 `VocalVerse工作日志.md` 同约定）。

---

## BUG：`spring-boot:run` 报 `Process terminated with exit code: 1`，日志尾部仅见 Hibernate `Unable to determine Dialect without JDBC metadata`

- **发现/复现时间**：2026-09-04（组长代码合并后，本机首次跑方式 B）
- **负责人**：Faust-sudo（与组长 LHRCarrier 排查：结论为本地 .env/DB 状态漂移，非代码问题）
- **严重级别**：P1（Java 端完全起不来，方式 B 三端缺一）
- **是否受合并影响**：**否**。迁移已是最新（`alembic_version=0005`，26 表），与本次失败无关；玄学误判「合并组长代码没跑迁移」的排查耗时约一次启动。

### 复现过程（2026-09-04 16:27 首次 · 16:31 复现确认）

```powershell
# docker compose ps 显示 postgres/redis 均 healthy；端口 8080 空闲
cd services/java
mvn spring-boot:run
```

实际结果：启动约 10s 后退出，Maven 汇总（与用户所见完全一致）：

```
[ERROR] Failed to execute goal org.springframework.boot:spring-boot-maven-plugin:3.3.5:run
        (default-cli) on project vocalverse-java-api: Process terminated with exit code: 1
```

关键日志（`-e` 才看得到，普通输出只有 Hibernate 表象）：

```
FATAL: password authentication failed for user "vocalverse"
org.hibernate.HibernateException: Unable to determine Dialect without JDBC metadata
```

### 根因分析

| 事实 | 值 |
|---|---|
| Java 默认 DB 密码（`application.yml` `${DB_PASSWORD:vocalverse-dev}`） | `vocalverse-dev` |
| 本机 postgres 容器**实际**密码（`docker inspect` + scram 实测） | `change-me-db-password`（09-01 16:16 容器初始化时从根 `.env` 带入） |
| `services/python/.env` 的连接串（Python 端据此能连） | `change-me-db-password` |
| 当前 shell 是否设了 `DB_PASSWORD` | 没有 → Java 走默认值 |

链路：Hikari 建连被拒（`password authentication failed`）→ Hibernate 拿不到 JDBC metadata → 抛 `Unable to determine Dialect` → 应用退出码 1 → spring-boot-maven-plugin 报 `Process terminated with exit code: 1`。

**本质**：本机 `.env` 沿用旧版 `.env.example` 的占位符 `change-me-db-password`（09-01 17:59 已把 `.env.example` 对齐为 `vocalverse-dev`，见工作日志踩坑 21——「**默认值必须与 compose 回退一致，且改密码三处同步**」），三处同步漏了 Java（Java 连的是同一库却没拿到新密码）。

**为何看起来像「没跑迁移」**：Hibernate 连接失败时抛的是「拿不到 metadata」而非「密码错误」，SQL 异常被 `SqlExceptionHelper` 打到 WARN 级，`-e` 之前只见 Dialect 错——误导为 schema/迁移问题。迁移缺失的症状是「**应用能启动、请求时 500**」，与本次「启动即退」完全不同。

### 修复过程（2026-09-04）

1. **改库密码（零数据丢失，秒级）**：
   ```sql
   ALTER USER vocalverse PASSWORD 'vocalverse-dev';
   ```
2. **根 `.env`**：`POSTGRES_PASSWORD=change-me-db-password` → `vocalverse-dev`；顺带把残留占位 `JWT_SECRET=change-me-please-use-64-char-random` → `vocalverse-dev-jwt-secret-0123456789abcdef`（对齐 `.env.example`/Java 默认；否则方式 A 的 compose 注入 `APP_JWT_SECRET` 会与 Java 验签失配——工作日志坑 2 翻版）。`SERVICE_TOKEN` 已一致，未动。
3. **`services/python/.env`**：`APP_DATABASE_URL` 密码同步为 `vocalverse-dev`（该文件注释也同步更新）。
4. **`services/java/.env.example`**：把残留的 `DB_PASSWORD=change-me-db-password`、`JWT_SECRET=change-me-please-use-64-char-random` 对齐为约定值，并补「方式 B 需手动导出环境变量、compose 下由根 .env 注入」的说明。
5. **README FAQ**：新增一行区分「漏起依赖（`JdbcEnvironmentInitiator` 无 auth 字样）」与「密码失配（含 `password authentication failed`，退出码 1）」。

### 修复情况（2026-09-04 16:37 验证）

| 检查项 | 结果 |
|---|---|
| scram 实测：`vocalverse-dev` 可连 / 旧密码被拒 | ✓ / ✓ |
| `mvn spring-boot:run` 重新启动 | ✓ `Started VocalverseApplication in 8.505s`（Java 24.0.2） |
| `GET /actuator/health` | ✓ `UP` |
| `GET /api/v1/ping` | ✓ `{"code":0,...,"status":"alive"}` |
| DemoSeeder | ✓ 演示账号就绪 |
| 迁移再核对 | ✓ `alembic_version=0005`（head），26 表——无需迁移 |

### 踩坑记录

1. **「启动即退・退出码 1」先查「能不能连上库」，别先怀疑迁移/代码合并**：Hibernate 连库失败抛 `Unable to determine Dialect` 纯属表象（metadata 拿不到）；真因在更多 `-e` 看 SQL 异常（`password authentication failed`）。迁移缺表的症状一定在**启动之后**的请求期，启动期失败与迁移无关。
2. **三端密码同步口径要含 Java**：仓库既有约定「三处同步：compose / services/python/.env / 根 .env」成立前提是 Java 用**默认值**（`vocalverse-dev`）或 `DB_PASSWORD` 环境变量——而 Java 的 `application.yml` 默认值本身也是约定的一部分，任何一处改动都必须回看它。
3. **`.env` 编码陷阱**：本机根 `.env` 是 **GBK 编码**（非 UTF-8，含中文注释），用 UTF-8 的编辑器/脚本直接重写会把注释变乱码；改值时按原编码读写（`[Text.Encoding]::GetEncoding(936)` 解码→替换→写回），或只改 ASCII 值行。`services/python/.env` 是 UTF-8 无此问题（两文件同构，只是历史来源不同）。
4. **compose 的 `POSTGRES_PASSWORD` 只在容器首次初始化时生效**：改 `.env` 后老容器不会换密码（`docker inspect` 的 env 与实际口令可能不一致——我们靠 `ALTER USER` + scram 实测才定论，别信 env 变量猜端到端行为）。
5. **排查次序沉淀**：凡「Java/Python 连不上 PG」→ ①`docker compose ps` healthy？②库口令实测（容器内信任连接不算数，要走 scram：`docker exec ... psql -h <容器IP>` 或宿主机客户端）③与 Java 默认值对表；三步都过再怀疑迁移/schema。
