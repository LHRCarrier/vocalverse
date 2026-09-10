# API 响应契约（docs/06 第 7 章）

所有接口（Python 与 Java）统一 envelope：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

- `code = 0`：成功；非 0 为业务错误码（见 `error-codes.md`）
- **错误体统一（J-08 · 2026-09-08）**：Java 错误响应一律 `{code, message, data:null}` envelope——全局 `GlobalExceptionHandler`（`@RestControllerAdvice`）把 `ResponseStatusException` / 校验失败 / 唯一键冲突 / 未匹配路径 / 405 / 兜底异常全部翻译为 Envelope（社区包业务码 4xxxx 仍由 `CommunityExceptionHandler` 先咨询，校验失败 42203 特例）；已知边界：过滤器层 401/403（JwtAuthFilter / ServiceTokenFilter / Security）不经 Advice（docs/18 登记）；Java 侧错误码 → HTTP 映射见 error-codes.md（401→40101、404→40401、409→40904、405→40501、兜底→50002）
- **错误 `data` 的结构化例外（2026-09-10 管理端新增登记）**：上面「错误 data 恒 null」不再是全称命题。管理端控制台（docs/50 §10.4）有 5 个码**必须有结构化 data**，否则前端只能靠正则解析中文提示：
  | code | `data` 形状 | 用途 |
  |---|---|---|
  | 46002 | `{required: string}` | 缺哪个权限码，前端直接展示给管理员去开权限 |
  | 46003 | `{lockedUntil: string}` | 账号被锁定到何时 |
  | 46008 | `{retryAfter: number}` | 登录风控剩余秒数 |
  | 46011 | `{violations: {field, code, message}[]}` | 上架前置校验的字段级原因。**形状以实现为准**：`PublishService.Violation(field, code, message)`——`field` 是表单字段名、`code` 是机器可读标识（如 `lrc_missing`）、`message` 是给人看的中文原因。早期文档写的 `{field, reason}` **不存在** `reason` 字段，前端按它读会渲染成 `· lrc：undefined` |
  | 46015 | `{caseId: number}` | 重复举报命中既有审核单，前端直接跳转 |
  实现侧为 `Envelope.error(int, String, T)` 纯新增重载，原 `error(int, String)` 行为不变（既有 `ErrorEnvelopeTest` 不受影响）。**其余所有错误码的 `data` 仍恒为 `null`**——不要因为有了这个重载就随手塞调试信息，`data` 是对前端的契约，不是日志。
- HTTP 状态码负责传输层错误（404/413/429/5xx），`code` 负责业务语义，两者并存
- **Python 错误体统一（2026-09-10 · P0-5 修复）**：Python 侧 `HTTPException` 一律经全局 `http_error_handler`（`app/main.py`）翻译为 `{code, message, data:null}`；映射**只取已登记码**——400→40001 / 401→40101 / 403→40301 / 404→40401 / 405→40501 / 409→40902 / 410→41001 / 413→41301 / 422→42201 / 429→42901 / 502·503→50301，未登录 4xx 兜底 40001、5xx 兜底 50002；**响应头透传**（429 的 `Retry-After` 必须保留，error-codes.md:28 契约）。
  - 修复前：鉴权/限流等 24 处 `raise HTTPException(...)` 走 FastAPI 默认 handler，返回 `{"detail": ...}` → `40101/42901` 永不出现、前端只能显示 `HTTP 429`（拷问报告 §1 Top 5）。
  - 唱歌评分任务失败：任务态已回带 `code=50003`（算法失败）+ 可读文案，异常细节只进服务端日志（不再回传容器路径）；「任务态丢失」回 `code=50002`。
- 时间字段一律 UTC ISO-8601
- 时间字段一律 UTC ISO-8601（**控制台例外**：`/api/v1/console/**` 出参带 offset，便于运维/审核在本地时区直接判读时间线，docs/50 §10.1）
- 分页（offset 型）：`data = { items: [], total, page, page_size }`
- 分页（**keyset 游标例外 · 社区流专用**，2026-09-06 登记）：`data = { items: [], next_cursor, has_more }`——无 `total/page/page_size`（无限长流分页无法也不必要总数）；请求参数 `cursor`（`base64(created_at_iso|id)`）+ `limit ≤ 20`，服务端取 `limit+1` 判 `has_more`；`next_cursor` 为 null 表示到尾
- **流式例外（SSE，2026-09-10 补登记）**：响应为 `text/event-stream` 事件帧、**不是 envelope**——Python 侧 `POST /api/v1/sessions/{id}/turns`、`POST /api/v1/reading/chapters/{id}/tts/prepare`；**Java 侧 `GET /api/v1/community/messages/stream`**（私信 IM · docs/49 §3，`@Hidden` 不进 OpenAPI 契约）。统一事件名与 `since` 续传语义见 docs/21 §1.1 例外 ⑤

## 端点分组

| 前缀 | 服务 | 说明 |
|---|---|---|
| `/api/v1/*` | Python:8000 | 语音/LLM/推荐热路径（前端直连） |
| `/api/v1/console/**` | **Python:8000** | **管理端控制台 · 运维域 + 书籍/媒体**（docs/50 §3.2：与 Java 侧**子路径不重叠**） |
| `/manage/api/v1/*` | Java:8080 | 管理端（用户/场景/歌曲库/工单）+ **社区 C 端**（community/*）+ 登录发号 |
| `/manage/api/v1/console/**` | **Java:8080** | **管理端控制台 · 身份/RBAC/审计/审核/内容**（独立身份体系，见下方「控制台鉴权」） |
| `/healthz` `/readyz` | Python | 健康检查 |
| `/actuator/health` | Java | 健康检查 |

> ⚠️ **控制台为什么横跨两个服务**：不是分层失误，而是**按数据归属方分服务**——每个服务只暴露自己拥有（写）的数据，避免 Java 读写 Python 的表（破坏 docs/06 §10 写方矩阵，docs/50 §3.2）。控制台 SPA 是组合层。

## 鉴权

- access JWT：`Authorization: Bearer <token>`，15 分钟
- refresh JWT：httpOnly + SameSite=Lax + Secure cookie，7 天，`POST /manage/api/v1/auth/refresh`
- Java 签发（HS256 共享 secret），Python 验签；Java↔Python 内部调用带 `Authorization: Bearer <service-token>`（2026-09-06 修正：R-17 文档与代码对齐——docs/06/20 旧表述 `X-Service-Token` 以本行为准，见 docs/21 §4）

## 控制台鉴权（2026-09-10 新增 · docs/50 §4.1）

管理端控制台**不用**上面的 App 令牌体系，而是独立身份 + 独立令牌：

| 项 | App | 控制台 |
|---|---|---|
| 身份来源 | `users` | **`admin_users`**（与 `users` 无外键、无字段共享） |
| access TTL | 15min（代码实测 3600s，见 docs/50 §15.2 G-11） | **900s** |
| refresh | JWT（30 天，按 sha256 查库） | **不透明随机串**（32B hex，sha256 存 `admin_sessions`，12h，一次性轮换） |
| 令牌 claim | 无 `aud` | `aud=vocalverse-console` / `typ=console-access` / `iss=vocalverse-java` / `role` / `perms` / `epo`(token_epoch) |
| 失效语义 | 到期为止 | **停用/降权/改密即 bump `token_epoch` → 下一请求生效**（不等 TTL） |

> 🔒 **跨令牌必须双向拒绝**（docs/51 P0-A/B 裁决）：App 令牌访问控制台 → 拒；**控制台令牌访问 App 端点 → 也必须拒**。
> 实现方式：App 侧过滤器只拒绝**携带外来 `aud`** 的令牌（既有 App 令牌**没有** `aud` claim，因此本改动对在线用户零影响——给 App 令牌补 `aud` 会让全体在线用户强制登出，因为 `AuthController` 复用 access token 作 refresh，**禁止**这么做）。
> Python 侧 `app/core/auth.py` 原实现只验签 + exp，必须补 `aud/typ/iss` 三闸（docs/51 P0-B）。
