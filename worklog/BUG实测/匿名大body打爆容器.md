# BUG：匿名大 body 可打爆容器（multipart 解析早于鉴权 + 无总量上限）

- **发现**：2026-09-10 · 唱歌模块七路拷问（G 路：安全/隐私/性能/资源）；主代理读 FastAPI/Starlette 源码复核 + 端到端判别实测。
- **修复**：2026-09-10 · 执行人：AI 代签（正式署名待组长确认）· 组长拍板**方案 A（应用中间件 + nginx 纵深防御）**。
- **影响面**：**全部 Python 端点**的请求体上限（不止唱歌）；修复前**匿名**请求即可让 8000 端口把任意大小数据落盘/读内存（`mem_limit 2g` + 宿主 bind mount）→ uvicorn 被打死（连带 SSE 与评分全断）。**严重级：本地/内网 P1，公网 P0**（暴露面取决于部署；修复成本低，按 P0 处理）。

## 复现

```
匿名 POST /api/v1/sessions/{id}/audio（或任意端点）携带 22MB body
```
- 修复前：服务**先解析完 22MB**（Starlette >1MB 落临时盘，`formparsers.py:147`），之后才跑到鉴权依赖 → 实测 422/401 之前已付出完整 IO/内存代价（本仓库实测：22MB 打到 `/api/v1/events` → **422 `json_invalid`**，即 body 已被完整读取解析）。
- 修复后：**路由前**即 413 `{"code":41301,...}` envelope，body **完全未被读取**。

## 根因

1. **FastAPI 的执行顺序**：`get_request_handler` 里 `body = await request.form()`（`.venv/.../fastapi/routing.py:430`）**先于** `solve_dependencies(...)`（`:481`）→ 鉴权/限流等依赖在 body 解析之后才跑。
2. **Starlette 无总量上限**：multipart part 超过 1MB 即 spool 到临时盘，且不限单 part/整包大小（只限 part 数量 `max_files=1000`）。
3. **应用层校验位置太晚**：`sing/service.py` 的 20MB 校验发生在 `await audio.read()` 之后（读完整包再判），`audio.py` 的 `_read_bounded` 同理是"读完再判"。
4. 结果：匿名请求即构成资源耗尽向量（容器 `--limit-concurrency 10` 是唯一全局闸，10 并发 × 任意大 body 可瞬间打满内存/磁盘）。

## 修复

1. **应用层护栏** `app/core/body_limit.py`（纯 ASGI，可单测）：
   - ① `Content-Length` 已声明 → 超限立即 413（**不读 body**）；
   - ② 分块/未声明/声明值撒谎 → 包 `receive` 计数护栏，累计超限即中断并 413；
   - 响应体为统一 envelope `{"code":41301,...}`；若下游已开始响应则不抢发 413（避免双响应）。
   - 注册于 `app/main.py`：上限 = `max_upload_bytes`(20MB) **+ 1MB**（multipart 封装余量，避免合规上传被边界拒绝）。
   - 依据：docs/06 §8（≤20MB 口径 + 本次新增"双层护栏"条）、docs/api/error-codes.md:22（41301）、docs/api/envelope.md。
2. **边缘层** `apps/web/nginx.conf`：`client_max_body_size` 20m → **21m**（同上余量）+ `error_page 413 → @err413` 返回 JSON envelope（nginx 默认 HTML 错误页会让前端只看到 `HTTP 413`）。
   - 说明：nginx 原本就配了 `client_max_body_size 20m`（拷问报告 G-#1 的建议已部分存在），真缺的是**应用层**（vite dev / 容器内网等不经 nginx 的入口无保护）。
3. **保留业务校验**：`sing/service.py` 的 20MB/180s 校验不动（纵深防御第三层，且给出 41302 等精确码）。

## 验证

| 项 | 结果 |
|---|---|
| 单元（假 ASGI scope/receive/send，7 例）：声明超限→立即 413 且**内层 app 零调用**；限内放行；**分块无 Content-Length 累计超限→413**；**伪造偏小的 Content-Length 仍被拦**；websocket scope 直通 | ✅ 7 passed |
| 端到端：22MB body → `/api/v1/events` → **413 + envelope 41301**（早于鉴权/校验） | ✅ 绿 |
| 回归护栏：正常体积请求（events 埋点）仍 200/code=0 | ✅ 绿 |
| **修复前必失败**：临时移除 `app.add_middleware(BodySizeLimitMiddleware, ...)` 注册后复跑端到端用例 | ❌ 红：`AssertionError: assert 422 == 413`（修复前 22MB 被完整解析后返回 `json_invalid`） |
| nginx 语法：`docker run --rm --add-host python-api:127.0.0.1 --add-host java-api:127.0.0.1 -v apps/web/nginx.conf:/etc/nginx/conf.d/default.conf:ro nginx:1.27-alpine nginx -t` | ✅ `syntax is ok` / `test is successful`（与运行中的 web 容器同基镜像） |
| 全量 Python `ruff check`/`format --check`/`pytest -q` | ✅ 全绿 **456 passed**（449 + 7） |

> 测试装置踩坑：初版单测的假内层 app **不读 body** → 分块用例假绿（护栏只在读取时计数）；改成"读完 body"后才真正生效。**这同时说明**：护栏对"不读 body 的端点"无副作用（无需要即无计数）。

## 踩坑

1. **"校验放在 handler 里"挡不住解析开销**：凡是"读完整包再判大小"的写法，都在攻击者可控的资源消耗之后——**上限必须在读之前**（本处用 `Content-Length` + 接收计数两层）。
2. **伪造/缺失 `Content-Length` 必须兜住**：只信声明值 = 只防君子（分块传输与撒谎头都能绕过），故必须同时有接收层计数。
3. **改造异常路径要防"双响应"**：中间件若在下游已发响应头后再补 413，会破坏连接语义；本实现用 `started` 标志位退化处理。
4. **两侧上限要留封装余量**：应用层 20MB 限制的是**音频文件**，multipart 封装天然多出若干字节 → 应用与 nginx 都取 "20MB + 1MB"，否则"刚好合规"的上传会被边界/护栏拒掉。
5. **边缘错误页也要 envelope**：nginx 默认 413 是 HTML，前端只解析 JSON → 用户看到 `HTTP 413`；`error_page 413` 回 JSON 才与 `docs/api/envelope.md` 一致。

—— 执行人：AI 代签（正式署名待组长确认），2026-09-10
