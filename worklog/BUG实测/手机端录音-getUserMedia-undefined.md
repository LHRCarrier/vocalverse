# 手机端点麦克风报错：Cannot read properties of undefined (reading 'getUserMedia')

> 归档日期：2026-09-10 · 发现人：组长手机实测 · 模块：`apps/web` 录音（`audio/recorder.ts`）+ 壳（`apps/mobile`）

## 复现

手机（Capacitor 壳，`server.url=http://192.168.0.104:5173`）进 `/m/chat` 点麦克风 → 页面红字
`Cannot read properties of undefined (reading 'getUserMedia')`；同一份代码桌面 `localhost:5173` 完全正常。

## 根因

`audio/recorder.ts::start()` 直接 `await navigator.mediaDevices.getUserMedia({ audio: true })`，
**没有对 `navigator.mediaDevices` 是否为 undefined 做防护**。

而 `navigator.mediaDevices` 只在**安全上下文**暴露：`https://`、`http://localhost`、`http://127.0.0.1`、
`file://`。手机端经 **HTTP 局域网 IP**（`http://192.168.0.104:5173`）加载 → 非安全上下文 →
`navigator.mediaDevices` 为 `undefined` → `.getUserMedia(...)` 抛原生 `TypeError`。

桌面是 `localhost:5173`（浏览器视为安全上下文）→ 正常。这也是「远程 URL 型壳」的固有约束：
**壳内 `server.url` 指向局域网 HTTP 时，任何 getUserMedia/录音类功能在手机上必然不可用**，
与浏览器端无关（真机 Chrome 开同一 HTTP 地址也一样）。

## 修复（防护，非根治）

- `recorder.ts`：`supported` 改为 `typeof MediaRecorder !== 'undefined' && !!navigator.mediaDevices?.getUserMedia`；
  `start()` 在调用前判 `navigator.mediaDevices?.getUserMedia`，缺失时抛友好 `RecorderError`（视图经
  `micErrorMessage` 展示中文提示「录音需在安全环境（HTTPS 或 localhost）使用」），不再抛原生 TypeError。
- 壳 `AndroidManifest.xml` 补 `android.permission.RECORD_AUDIO`（此前只有 INTERNET——即使安全上下文，
  WebView 的 onPermissionRequest 也拿不到麦克风）。二者是**录音能用的必要条件**，但**不足够**：
  非安全上下文这个前提不解决，手机上录音仍不可用。

## 根治（2026-09-10 已落地 · 方案 B）

组长先选 A（HTTPS + 手机装 CA），嫌麻烦后改 **B（打包进壳）**：

- `capacitor.config.json`：`webDir="../web/dist"`、`server.androidScheme="https"`、`android.allowMixedContent=true`，去掉 `server.url` → Capacitor 以 **`https://localhost`** 提供打包 web（**浏览器自带安全上下文**，无需装 CA）→ `getUserMedia`/`MediaRecorder` 可用；
- web 以 `VITE_PYTHON_BASE=http://<IP>:8000`、`VITE_JAVA_BASE=http://<IP>:8080` 重建，API 打到本机后端（构建期写死 IP）；
- `network_security_config.xml`：仅信任 system CA + `cleartextTrafficPermitted=true`（https 页调 http 后端的混合内容/明文放行）；
- **后端可被手机访问**：python 改 `--host 0.0.0.0`（原只绑 127.0.0.1，手机连不到）；java 8080 已绑 `::`。
- 代价：**无 HMR**（改 web 需 `pnpm build`+`cap copy`+`assembleDebug`+重装）；API 基址写死 IP（换网需重建）。

**追加（组长手机实测 B 后，2026-09-10）**：录音提示「麦克风被拒绝，请在浏览器地址栏的权限设置里允许麦克风后重试」——根因：Capacitor `BridgeWebChromeClient.onPermissionRequest` 对 `AUDIO_CAPTURE` 会**同时**申请 `MODIFY_AUDIO_SETTINGS` + `RECORD_AUDIO`，缺任一 → 权限回调 deny → `request.deny()` → getUserMedia `NotAllowedError`；Manifest 此前只有 `RECORD_AUDIO` → 真机必被拒。修复：Manifest 补 `MODIFY_AUDIO_SETTINGS`（normal 级，安装即授）。验证：`dumpsys package` 两权限均 `granted=true`。

## 验证

- `recorder.test.ts` +2 例：`mediaDevices` 为 undefined 时 `start()` 抛 `RecorderError`（非 TypeError）
  且含「安全环境」文案；`supported` 返回 false。
- 前端 lint / typecheck / test:run（163 passed）/ build / check-bundle 全绿；`gradlew assembleDebug` 含新权限。

## 踩坑

1. **非安全上下文是一个「环境级」硬门槛**：不是代码 bug，改一行防护只是让报错友好，不影响「能不能用」。
   要真用起来必须先让上下文变安全（HTTPS 或 localhost）。
2. **权限与安全上下文是两回事**：`RECORD_AUDIO` 缺失会以权限错误出现；`mediaDevices` 缺失以 TypeError 出现。
   这次是后者（TypeError），说明还没走到权限层。
3. 远程 URL 型壳（README 里明示）与 getUserMedia 天生冲突；若录音是核心能力，长期应往 B（打包/`https://localhost`）走。
