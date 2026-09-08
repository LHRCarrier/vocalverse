# apps/mobile · VocalVerse 手机壳（Capacitor）

> 2026-09-10 起改为**打包进壳型**（方案 B）：`webDir: "../web/dist"`，Capacitor 以 **`https://localhost`**
> 提供 web（安全上下文 → 手机端录音 `getUserMedia`/`MediaRecorder` 可用，无需装 CA）；Web 的 API 用构建期
> 环境变量指到本机后端（`VITE_PYTHON_BASE=http://<局域网IP>:8000`、`VITE_JAVA_BASE=http://<局域网IP>:8080`），
> 经 `allowMixedContent` + 网络安全配置放行明文。
>
> ⚠️ 早期是「远程 URL 型壳」（`server.url` 指向局域网 HTTP）。因 getUserMedia 要求安全上下文，
> 远程 HTTP 在手机上必然不可用；若坚持远程壳，需 HTTPS + 手机信任 CA（曾为方案 A，已弃用）。

## 目录

```
apps/mobile/
├── capacitor.config.json   # appId/appName/webDir + server.url（局域网 IP + cleartext）
├── android/                # Capacitor 8.5.1 生成工程（compileSdk/targetSdk 36）
└── dist/                   # 占位（远程 URL 型不用；cap sync 需要存在）
```

## 从零重建（任何有 SDK 的机器）

```powershell
cd apps/mobile
pnpm install
# ① 先构建 Web（API 基址指向本机后端；桌面/localhost 开发可省略这两行环境变量）
cd ../web
$env:VITE_PYTHON_BASE='http://<局域网IP>:8000'
$env:VITE_JAVA_BASE='http://<局域网IP>:8080'
pnpm build        # 产物 apps/web/dist
cd ../mobile
# ② 初始化 Capacitor（androidScheme https = 打包壳走 https://localhost 安全上下文）
npx cap init "VocalVerse" "com.vocalverse.app" --web-dir=.
npx cap add android
npx cap copy android
cd android
.\gradlew.bat assembleDebug
# 产物：android\app\build\outputs\apk\debug\app-debug.apk
```

## 手机安装

```powershell
# 方式 1：adb（需开发者模式 + USB 调试）
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
# 方式 2：把 APK 传到手机直接安装（允许未知来源）
```

## 关键配置说明

| 项 | 值 | 说明 |
|---|---|---|
| `webDir` | `../web/dist` | 打包的 web 产物（apps/web/dist），`npx cap copy` 同步 |
| `server.androidScheme` | `https` | 打包壳以 `https://localhost` 服务 → 安全上下文（录音可用） |
| `android.allowMixedContent` | `true` | https 页面向 http 后端发请求（混合内容）放行；演示口径，生产应改 https |
| 网络安全配置 | `res/xml/network_security_config.xml` | `cleartextTrafficPermitted=true` 放行明文；仅信任 system CA |
| API 基址 | 构建期 `VITE_PYTHON_BASE`/`VITE_JAVA_BASE` | 写死局域网 IP；换网/IP 变需重新 `pnpm build` + `cap copy` |
| `RECORD_AUDIO` | AndroidManifest | 录音（getUserMedia）必需权限 |

## 演示账号（M2 seed）

`demoadult` / `demoteen` / `demosenior`，密码 `demo123456`（Fake 链路：无密钥时评分/TTS/LLM 走 stub）。

## 未做（详见 docs/27）

iOS 平台（需 Mac+证书）、原生录音/推送插件、商店签名（release）、热更新——均为 docs/27 后续切片。

## 删除清单（整体可删）

本目录整体删除即可（`server.url` 型壳不依赖前端构建、不触碰后端；`apps/web` 变更仅 PWA 三文件：`public/manifest.webmanifest`、`public/icons/*`、`index.html` 的 head 两行）。
