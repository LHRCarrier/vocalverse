# BUG：错误码契约虚设（40101/42901/50003 永不出现）+ 内部异常原文回传

- **发现**：2026-09-10 · 唱歌模块七路拷问（C 路契约对账 + B 路口径探针 + G 路安全复核，三路交叉）。
- **修复**：2026-09-10 · 执行人：AI 代签（正式署名待组长确认）· 组长拍板：**方案 A（全局 handler + 50003 落地）**。
- **影响面**：**全仓 Python 端点**的错误响应形状（24 处 `raise HTTPException`）+ 唱歌评分失败态文案/字段。修复前：前端按 `code` 分派的逻辑**全部失效**（`client.ts` 拿到 `body.code === undefined` → `ApiError(-1, 'HTTP 429')`），用户看到 `HTTP 429` 而非「今日跟唱次数已达上限（每小时 5 次）」；失败态还会把容器绝对路径（`/app/data/audio/<sha1>.webm`）等内部串回传客户端。

## 复现

```powershell
# ① 401（无令牌）——修复前
curl.exe -s http://localhost:8000/api/v1/songs
# {"detail":"missing bearer token"}          ← 非 envelope、无 code
# ② 429（第 6 次唱歌上传）——修复前
# {"detail":"rate limited (sing)"}           ← 前端只显示 HTTP 429
# ③ 唱歌评分失败（删掉素材/转码失败）——修复前
# 任务态 error = "audio file missing: /app/data/audio/xxxx.webm"（内部路径直出）
```

代码事实：`app/core/auth.py:66/70/73`、`app/core/ratelimit.py:69`、`app/defense.py`/`placement.py`/`audio.py` 等共 **24 处** `raise HTTPException(...)`，而 `app/main.py` 只注册了 `BizError` 与 `RequestValidationError` 两个 handler → FastAPI 默认 handler 返回 `{"detail": ...}`。`docs/api/error-codes.md` 里 `40101/42901/50003` 三个码**全仓零 raise**（grep 0 命中）→ 表 = 代码全集的前提不成立。

## 根因

1. **两套错误通道并存**：业务层用 `BizError`（→ envelope），框架层用 `HTTPException`（→ `{"detail"}`），后者没有 handler 兜底；
2. **前端契约建立在 code 上**：`apps/web/src/api/sing.ts` 的 `42901` 文案分支、`client.ts` 的 `body.code ?? -1` 都假设 envelope 恒成立 → 该假设被 HTTPException 路径打破；
3. **失败态无码**：唱歌任务失败把 `str(exc)` 直接写进任务态 → 前端只能字符串匹配（且泄露内部信息，G-#12）。

## 修复

1. **`app/main.py` 新增全局 `http_error_handler`**：`HTTPException` → `{code, message, data:null}`；
   映射**只用已登记码**（不新增码）：400→40001 / 401→40101 / 403→40301 / 404→40401 / 405→40501 / 409→40902 / 410→41001 / 413→41301 / 422→42201 / 429→42901 / 502·503→50301；未登记 4xx 兜底 40001、5xx 兜底 50002；
   **响应头透传**（`Retry-After` 是 42901 的契约字段，`error-codes.md:28`）。
   依据：docs/api/envelope.md（统一 envelope，本次补 Python 段）、docs/api/error-codes.md（登记纪律：先登记后使用，本 handler 零新增码）、docs/21 §1.1 例外登记。
2. **唱歌失败态码化**（`app/sing/service.py`）：`_run_attempt` 异常 → 任务态 `code=50003` + `error="评分失败，请重试"`，异常细节只进 `logger.exception`（不再回传客户端）；「任务态丢失」→ `code=50002` + 中文文案（原文英文串 `task lost (server restarted); please retry` 直出用户）。
3. **前端按码映射**（`apps/web/src/api/sing.ts`）：新增 `singFailureMessage({code, error})`——50003→「评分失败：算法侧异常（已记录），可重试或反馈」、50002→「服务暂时异常，请稍后重试」、无码回退服务端文案；`singErrorMessage` 同步补 50003/50002；`SingAttemptStatus` DTO 增 `code?: number | null`；组合式 `poll()` 的 failed 分支改用 `singFailureMessage`。
4. **测试搬迁**（顺带解门禁）：三个纯映射函数的用例从 `composables/__tests__/sing.test.ts` 迁至 `api/__tests__/sing-messages.test.ts`（API 层纯函数归 API 测试，且原文件已触 `max-lines 350`——**lint 抓到了，门禁有效**）。

## 验证

| 项 | 结果 |
|---|---|
| `tests/test_http_envelope.py`（新增 4 例）：401 无令牌 body 为 envelope 且 `code=40101` 三键齐全；defense 的 HTTPException(404) → `40401`；**429 → `42901` 且保留 `Retry-After: 3600`**；BizError/HTTPException 两路径同形状 | ✅ 绿（**修复前必失败**：旧 body 为 `{"detail": ...}`、无 code） |
| `test_worker_failure_no_fake_scores`（更新）：失败态 `code==50003`、`error=="评分失败，请重试"`、**异常原文不得回传** | ✅ 绿（修复前：无 code、error 含 "pipeline crash"） |
| `api/__tests__/sing-messages.test.ts`（13 例，含 50003/50002 映射与"不透出内部原文"） | ✅ 绿 |
| 全量 Python `pytest -q` | **449 passed**（445 + 4）；`ruff check`/`format --check` 全绿 |
| 契约快照 vs `app.openapi()` | ✅ 零 diff（异常 handler 不进 OpenAPI） |
| 全量前端 `lint` / `typecheck` / `test:run` **169 passed** / `build` / `check-bundle.mjs` | ✅ 全绿 |

## 踩坑

1. **"契约表 = 代码全集"必须有发出点对账**：三个码在表里躺了很久、无人发现零 raise——**登记不等于实现**；对账脚本应按"表 → grep raise 点"双向校验（本轮已在 error-codes.md 头部补发出点说明）。
2. **默认框架行为会悄悄破坏自己的契约**：FastAPI 默认 `{"detail"}` 与项目 envelope 冲突，任何"业务层统一 + 框架层不管"的设计都要显式兜底 handler。
3. **429 必须透传 `Retry-After`**：把异常转 envelope 时若丢掉 headers，前端就拿不到重试秒数——映射表好写、**头透传容易漏**，测试专门钉住。
4. **异常原文回传是双重问题**：既泄露内部路径，又逼前端做字符串匹配；正确做法是"对外码 + 可读文案，细节进日志"。
5. **`max-lines` 门禁在这轮真的拦下了我**：新增 4 个用例即触发 356/350 → 顺势把 API 层纯函数用例迁到 `api/__tests__/`（结构更合理）。这是门禁有效的正例（对照 P0-0 的空操作 typecheck）。

—— 执行人：AI 代签（正式署名待组长确认），2026-09-10
