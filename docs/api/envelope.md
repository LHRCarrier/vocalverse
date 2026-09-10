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
- HTTP 状态码负责传输层错误（404/413/429/5xx），`code` 负责业务语义，两者并存
- **Python 错误体统一（2026-09-10 · P0-5 修复）**：Python 侧 `HTTPException` 一律经全局 `http_error_handler`（`app/main.py`）翻译为 `{code, message, data:null}`；映射**只取已登记码**——400→40001 / 401→40101 / 403→40301 / 404→40401 / 405→40501 / 409→40902 / 410→41001 / 413→41301 / 422→42201 / 429→42901 / 502·503→50301，未登录 4xx 兜底 40001、5xx 兜底 50002；**响应头透传**（429 的 `Retry-After` 必须保留，error-codes.md:28 契约）。
  - 修复前：鉴权/限流等 24 处 `raise HTTPException(...)` 走 FastAPI 默认 handler，返回 `{"detail": ...}` → `40101/42901` 永不出现、前端只能显示 `HTTP 429`（拷问报告 §1 Top 5）。
  - 唱歌评分任务失败：任务态已回带 `code=50003`（算法失败）+ 可读文案，异常细节只进服务端日志（不再回传容器路径）；「任务态丢失」回 `code=50002`。
- 时间字段一律 UTC ISO-8601
- 分页（offset 型）：`data = { items: [], total, page, page_size }`
- 分页（**keyset 游标例外 · 社区流专用**，2026-09-06 登记）：`data = { items: [], next_cursor, has_more }`——无 `total/page/page_size`（无限长流分页无法也不必要总数）；请求参数 `cursor`（`base64(created_at_iso|id)`）+ `limit ≤ 20`，服务端取 `limit+1` 判 `has_more`；`next_cursor` 为 null 表示到尾

## 端点分组

| 前缀 | 服务 | 说明 |
|---|---|---|
| `/api/v1/*` | Python:8000 | 语音/LLM/推荐热路径（前端直连） |
| `/manage/api/v1/*` | Java:8080 | 管理端（用户/场景/歌曲库/工单）+ **社区 C 端**（community/*）+ 登录发号 |
| `/healthz` `/readyz` | Python | 健康检查 |
| `/actuator/health` | Java | 健康检查 |

## 鉴权

- access JWT：`Authorization: Bearer <token>`，15 分钟
- refresh JWT：httpOnly + SameSite=Lax + Secure cookie，7 天，`POST /manage/api/v1/auth/refresh`
- Java 签发（HS256 共享 secret），Python 验签；Java↔Python 内部调用带 `Authorization: Bearer <service-token>`（2026-09-06 修正：R-17 文档与代码对齐——docs/06/20 旧表述 `X-Service-Token` 以本行为准，见 docs/21 §4）
