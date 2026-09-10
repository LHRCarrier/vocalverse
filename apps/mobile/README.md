# apps/mobile · VocalVerse 手机壳（Capacitor）

> 2026-09-10 起为**打包进壳型**（方案 B）：`webDir: "../web/dist"`，Capacitor 以 **`https://localhost`**
> 提供 web（安全上下文 → 手机端录音 `getUserMedia`/`MediaRecorder` 可用，无需装 CA）；Web 的 API 用构建期
> 基址打进包（`VITE_PYTHON_BASE`/`VITE_JAVA_BASE`），经后端 CORS + 混合内容放行连本机后端。
>
> ⚠️ 早期是「远程 URL 型壳」（`server.url` 指向局域网 HTTP）。因 getUserMedia 要求安全上下文，
> 远程 HTTP 在手机上必然不可用；若坚持远程壳需 HTTPS + 手机信任 CA（曾为方案 A，已弃用）。

## 目录

```
apps/mobile/
├── capacitor.config.json   # appId/appName/webDir + androidScheme=https + allowMixedContent（打包壳无 server.url）
├── android/                # Capacitor 8.5.1 生成工程（compileSdk/targetSdk 36）
└── dist/                   # 占位（打包壳不用；cap sync 需要存在）
```

## 手机联调两种连接方式（2026-09-10 定稿）

> 判定标准：真机上「Failed to fetch」时先看后端访问日志有没有手机 IP
> （java `services/java/logs/access_log.*.log`、python `local/dev-logs/python-8000.out.log`），
> 排查顺序详版见 `docs/30-移动端App测试方法.md` §2。

| 方式 | 适用 | 步骤 |
|---|---|---|
| **A · 局域网直连** | 电脑与手机同一 WiFi 且互访正常（默认） | ① `pwsh -File scripts/firewall-phone.ps1`（放行 8000/8080，**管理员**）→ ② `pwsh -File scripts/build-phone.ps1`（API 基址 = 本机局域网 IP）→ ③ `adb install -r …/app-debug.apk` |
| **B · adb 隧道**（localhost） | 手机→电脑直连不通（路由器/热点**客户端隔离**、防火墙拦、或懒得管网络） | ① 手机开「开发人员选项→无线调试」→ `adb pair <IP:配对端口>`（输 6 位码）→ `adb connect <IP:连接端口>`（或用 USB 调试）→ ② `adb reverse tcp:8080 tcp:8080; adb reverse tcp:8000 tcp:8000` → ③ `pwsh -File scripts/build-phone.ps1 -Ip localhost` → ④ `adb install -r …/app-debug.apk` |

**方式 B 原理**：App 页面仍在 `https://localhost`（安全上下文不变），API 改为打手机本机的
`http://localhost:8000/8080`，经 adb 隧道（adb 连接由电脑**主动**建立，不受客户端隔离影响）
转发到电脑后端。CORS 无需改（浏览器按页面源 `https://localhost` 匹配，已在后端白名单）。
注意：adb 断开/重连后需重跑 `adb reverse`；直连重装包前先 `adb reverse --list` 确认隧道在。

## 从零重建 / 日常重打（任何有 SDK 的机器）

```powershell
# 日常（每次改完 web）——一条命令重打（API 基址默认本机局域网 IP；-Ip localhost 为隧道版）
pwsh -File scripts/build-phone.ps1                    # = pnpm build(带基址) + cap copy + assembleDebug
pwsh -File scripts/build-phone.ps1 -Ip localhost      # adb 隧道版

# 从零（无 android/ 工程时）
cd apps/mobile && pnpm install
npx cap init "VocalVerse" "com.vocalverse.app" --web-dir=.
npx cap add android
# 然后同上 build-phone.ps1（或手工：cd ../web; pnpm build; cd ../mobile; npx cap copy android; cd android; .\gradlew.bat assembleDebug）
```

产物：`android\app\build\outputs\apk\debug\app-debug.apk`（≈4.6MB，含 web 产物）。

## 手机安装

```powershell
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
# 或把 APK 传到手机直接安装（允许未知来源）
```

## 关键配置说明

| 项 | 值 | 说明 |
|---|---|---|
| `webDir` | `../web/dist` | 打包的 web 产物（apps/web/dist），`npx cap copy` 同步 |
| `server.androidScheme` | `https` | 打包壳以 `https://localhost` 服务 → 安全上下文（录音可用） |
| `android.allowMixedContent` | `true` | https 页面向 http 后端发请求（混合内容）放行；演示口径，生产应改 https |
| 网络安全配置 | `res/xml/network_security_config.xml` | `cleartextTrafficPermitted=true` 放行明文；仅信任 system CA |
| API 基址 | 构建期 `VITE_PYTHON_BASE`/`VITE_JAVA_BASE` | 写死（局域网 IP 或 `localhost`）；**换网/IP 变必须重建**（`build-phone.ps1 -Ip 新IP`） |
| `RECORD_AUDIO` | AndroidManifest | 录音（getUserMedia）必需权限（Capacitor 音频采集**同时需** `MODIFY_AUDIO_SETTINGS`，两者都已在清单） |
| `MODIFY_AUDIO_SETTINGS` | AndroidManifest | 同上，缺一 → WebView 拒授权 → 报「麦克风被拒绝」 |

## 后端（联调前置）

```powershell
pwsh -File scripts/dev-up.ps1 start        # postgres/redis 容器 + python(0.0.0.0:8000) + java(8080)
pwsh -File scripts/firewall-phone.ps1      # 防火墙端口放行（管理员，幂等）
# 只想单独起 python：pwsh -File scripts/start-python.ps1 [-Detached]（带 APP_ASR_MODEL/HF 环境，防 ASR 脱绑）
```

演示账号：`demoadult` / `demoteen` / `demosenior`，密码 `demo123456`。

## 未做（详见 docs/27）

iOS 平台（需 Mac+证书）、原生录音/推送插件、商店签名（release）、热更新——均为 docs/27 后续切片；
生产形态建议后端 HTTPS/同源以去掉 `allowMixedContent` 与 CORS 白名单。

## 删除清单（整体可删）

本目录整体删除即可（打包壳不依赖前端构建产物入库、不触碰后端；`apps/web` 变更仅 PWA 三文件：
`public/manifest.webmanifest`、`public/icons/*`、`index.html` 的 head 两行）。
