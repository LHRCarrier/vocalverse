# 打包壳登录失败：Python（语音/LLM）服务不可达（HTTP 200，/manage/auth/login）

> 归档日期：2026-09-10 · 发现人：组长手机实测（方案 B 打包壳）· 模块：`apps/web` `stores/auth.ts`

## 复现

方案 B 打包壳（页面来自 `https://localhost`）点击登录 → 红字
`Python（语音/LLM）服务不可达（HTTP 200，/manage/auth/login）——请确认对应后端已启动`；
`dev-up status` 显示后端都在跑。

## 根因

`stores/auth.ts` 的 **Java 端点把 base 硬编码成 `'/manage'`**（login/register/forgot/fetchMe/refresh/logout 共 6 处），
**没有走 `client.ts` 的 `JAVA_BASE`**（构建期可用 `VITE_JAVA_BASE` 指定）。

- 导入壳模式：虽然构建时已把 `VITE_JAVA_BASE` 写成 `http://192.168.0.104:8080`，但 `auth.ts` 用的是
  **字面量 `'/manage'`**，于是登录 URL = `'/manage/auth/login'`（**相对路径**）→ 落在 Capacitor 本地服务器的
  `https://localhost/manage/auth/login` → 返回 index.html（HTTP 200、非 JSON）→ `client.ts` 的 `resp.json()` 抛错
  → 报「服务不可达」。
- **开发时为什么没事**：Vite 代理把 `/manage` 改写转发到 Java 8080；打包壳里没有这个代理，相对路径就到不了 Java。
- 附带：`client.ts` 的「谁不可达」判定 `base === JAVA_BASE`，而 auth 传的是字面量 `'/manage'` ≠ JAVA_BASE
  → 把**登录（Java）**误标成「Python」。

## 修复

- `stores/auth.ts`：6 处硬编码 `'/manage'` → `JAVA_BASE`（默认仍为 `'/manage'`，开发者与导入壳均正确）；
- `client.ts`：`who` 判定改为 `base === JAVA_BASE || path.startsWith('/manage')`（/manage 路径归 Java，标签正确）。

## 验证

- `stores/__tests__/auth.test.ts`：mock 补 `JAVA_BASE:'/manage'`（否则 `import JAVA_BASE` 报 mock 无导出）；6 例通过。
- 构建产物含绝对基址（`index-*.js` 内 `const ne="http://192.168.0.104:8000", K="http://192.168.0.104:8080"`）；
  壳内 bundle（`assets/public/assets/index-*.js`）同样含绝对 JAVA 基址。
- 本机 `http://192.168.0.104:8080/auth/login` 实测 code=0（登录通）、`8000/api/v1/reading/books` 200。
- 前端 lint/typecheck/test:run（163 passed）/build/check-bundle 全绿。

## 踩坑

1. **任何相对 API 基址在导入壳里都会落到 `https://localhost`（Capacitor 本地服务器）**，返回 HTML 200 而不是 5xx，
   所以错误是「服务不可达（HTTP 200）」而不是 4xx/5xx——看到 200 + 非 JSON 时先想到「相对路径没转到后端」。
2. **`who` 标签与真实服务不一致时要怀疑有硬编码 base**：`base === JAVA_BASE` 判不出来，因为字面量 ≠ 变量。
3. 导入壳后所有端点都要核对**是否有绕过 `JAVA_BASE/PYTHON_BASE` 的字面量 base**（本处是 `auth.ts` 6 处，
   其余 `community.ts`/`client.ts` 都正确引用了 `JAVA_BASE`）。
