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
- HTTP 状态码负责传输层错误（404/413/429/5xx），`code` 负责业务语义，两者并存
- 时间字段一律 UTC ISO-8601
- 分页：`data = { items: [], total, page, page_size }`

## 端点分组

| 前缀 | 服务 | 说明 |
|---|---|---|
| `/api/v1/*` | Python:8000 | 语音/LLM/推荐热路径（前端直连） |
| `/manage/api/v1/*` | Java:8080 | 管理端（用户/场景/歌曲库/工单）+ 登录发号 |
| `/healthz` `/readyz` | Python | 健康检查 |
| `/actuator/health` | Java | 健康检查 |

## 鉴权

- access JWT：`Authorization: Bearer <token>`，15 分钟
- refresh JWT：httpOnly + SameSite=Lax + Secure cookie，7 天，`POST /manage/api/v1/auth/refresh`
- Java 签发（HS256 共享 secret），Python 验签；Java↔Python 内部调用带 `X-Service-Token` 头
