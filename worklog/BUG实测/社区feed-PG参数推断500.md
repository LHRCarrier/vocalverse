# BUG：社区 feed 真机 500 —— PG 拒绝未类型化 NULL 参数（JPQL `:param IS NULL`）

> 日期：2026-09-06 · 模块：社区 C 端（`/api/v1/community/posts`）· 影响：S1 真实流首屏必现

## 复现

1. 真机跑全栈（Java 8080 + PG16 + 前端 `/m/home` 社区页首屏）；
2. 登录后社区首页加载 → 空态「加载失败 / HTTP 500」；响应为**裸 Spring 错误体**：
   `{"timestamp":..., "status":500, "error":"Internal Server Error", "path":"/api/v1/community/posts"}`（非 Envelope —— 进入通用 500 通道，非业务错误码）；
3. Java 日志栈：`org.postgresql.util.PSQLException: ERROR: could not determine data type of parameter $3（SQLState 42P18）`，调用链 `CommunityService.feed → PostRepository.feed`。

## 根因

`PostRepository.feed` JPQL 以 `(:domain IS NULL OR p.domain = :domain)` + `(:ts IS NULL OR ...)` 表达「首屏无过滤」——
首屏三参（domain/ts/id）**全为 null** 时，PostgreSQL 无法推断未类型化 NULL 参数的 type（42P18），
H2（单测环境）宽松容忍、PG（生产）直接拒绝。**H2 单测全绿 ≠ PG 兼容**是这轮真正的坑。

## 修复

（`services/java/.../community/PostRepository.java` + `PostCommentRepository.java` + `CommunityService.java`）
- feed/评论分页改 **JPA Criteria**（`JpaSpecificationExecutor` 默认方法）：Java 侧判空动态拼谓词，
  SQL 不再出现 `:param IS NULL`（未类型化 NULL 参数为 0）；
- 排序由 Pageable 携带（feed：`Sort DESC(createdAt, id)`；评论：ASC），语义与 keyset 游标一致；
- 顺带修复同轮发现的潜错：作者档案批量取用 `findByUserIdIn(authorIds)`（原先 `findAllById` 按 profile **PK**
  查 user_id，仅因演示种子 PK==user_id 未暴露）。

## 验证

- 8080/8081 真 PG 复测：feed（10 条 = 8 内容帖 + 2 历史打卡卡）、领域过滤（news=2）、双页游标翻页去重 10/10、
  打卡卡字段（overall/practice_count/date）全部正确；
- 全链路冒烟：发帖 → 点赞 → 评论 → 支持（不可取消）→ 软删 → 作者可见/他人 40402 均符合设计；
- `mvn verify` 29 全绿（H2 单测兼作 Criteria 路径回归）；前端 65 例不影响。

## 踩坑

1. **H2 与 PG 的 NULL 参数语义差异**：JPQL/原生 SQL 里凡是「参数可能是 null」的 `IS NULL` 判断，
   H2 能跑、PG 报 42P18——单测环境必须覆盖真 PG（或按此案把「参数判空」移到 Java 层，统一隐患清零）；
2. **仓库层「一参两义」**：`findAllById` 只认 PK，社区作者 id 是 `users.id`——跨表取档案务必用语义明确
   的派生方法名（`findByUserIdIn`）防隐性错配；
3. Java 启动 11s 内端口已监听但 context 未就绪：冒烟脚本需先等
   `Started VocalverseApplication` 日志特征串（本次误判 500/403 一次）。
