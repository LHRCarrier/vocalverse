# 登录偶发 40904「数据冲突」：同毫秒双登录撞 refresh token 唯一键

> 归档日期：2026-09-10 · 发现人：组长（手机端实测复现）· 分支：feat/novel-reading-main

## 复现

手机（MobileWebView → http://192.168.125.6:5173）登录页输入 `xiaoqing` + 密码 → 点 Sign In，
页面底部红字：**「数据冲突：唯一键或约束（重复提交/并发写入）」**（错误码 40904，Java 侧返回）。
同类操作偶发（复现概率与「同一毫秒内两次登录/刷新」时序相关，双击/WebView 双请求更易触发）。

## 根因

`AuthController.issue()`（登录/刷新共用）：

```java
String access = jwt.generateAccessToken(userId, role);
String refresh = jwt.generateAccessToken(userId, role) + "-" + System.currentTimeMillis();
```

- `JwtService.generateAccessToken` 的 payload 仅 `{sub, role, iat, exp}`（**无 jti/随机字段**，
  JJWT 时间戳秒级精度）→ **同一秒内**两次调用产出**相同令牌**；
- refresh = 相同令牌 + "-" + **毫秒** → **同一毫秒**内两次登录/刷新即产出相同字符串
  → `SHA-256` 相同 → 撞 `refresh_tokens.token_hash` 唯一键 `uq_refresh_tokens_token_hash`
  → `DataIntegrityViolationException` → `GlobalExceptionHandler`（J-08 接线）→ **409/40904**。

即：这是并发竞态（同一毫秒双请求），与账号无关；密码正确与否在 401 分支、不会走到落库，
故报 40904 说明 xiaoqing 当时密码正确——纯 token 碰撞所致。

## 修复

- `AuthController.buildRefreshToken(jwtToken, nowMillis)`：追加 **UUID 随机因子**
  （`jwtToken + "-" + nowMillis + "-" + UUID.randomUUID()`）；refresh 为不透明字符串、
  服务端只存 SHA-256，格式变更零兼容影响；抽为 package-private 纯静态便于确定性测试。
- **回归测试** `RefreshTokenUniquenessTest`：相同输入连续两次构造 → 断言 token 不同
  （修复前：同输入必同串 → 红；修复后：UUID 因子保证 → 绿）。零时序依赖、确定性失败。

## 验证

| 项 | 结果 |
|---|---|
| `mvn -Dtest=RefreshTokenUniquenessTest,AuthFlowTest test` | ✅ 6 passed（1 新回归 + 5 AuthFlow） |
| `mvn spotless:check` | ✅ 通过 |
| 真机链路冒烟：连续两次 `POST /auth/login`（demoadult） | ✅ 均 code=0；refreshToken 互不相同且含 `-\d+-<uuid>` 后缀 |
| 手机端 | 重新登录 xiaoqing → 正常进入（等待用户确认；若仍 40904 请清缓存重试） |

## 踩坑

1. **同一毫秒双请求是真实可行的**（双击 Sign In、WebView 双拉、`/auth/refresh` 并发兜底重试）——
   凡「去重键」必须不可预测随机源，**不能复用一个无随机字段的签名令牌 + 时间戳拼串**；
2. 40904 映射面比「注册撞用户名」宽得多：任何 `DataIntegrityViolationException` 都会显示
   「数据冲突」——排查时先看 Java 日志异常栈（本次即从栈定位到 uq_refresh_tokens_token_hash）；
3. 本地重启 Java 需从根 `.env` 注入 `JWT_SECRET`/`SERVICE_TOKEN`（Maven 子进程不读 .env，
   dev-up.ps1 有 setdefault 注入逻辑——手动起服务时容易漏，直接报 P0-9 fail-fast）。
