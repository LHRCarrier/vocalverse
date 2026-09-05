# apps/mobile · VocalVerse 手机壳（Capacitor）

> 2026 今日交付形态：**远程 URL 型壳**——Android WebView 直接加载局域网内全栈地址
> `http://192.168.1.3:8088`（docker compose 一键栈，nginx 同源反代 `/api/v1` 与 `/manage`；IP 以实际局域网为准）。
> 无需在前端构建产物装入壳内；壳与 Web 应用解耦、后端零改动。

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
npx cap init "VocalVerse" "com.vocalverse.app" --web-dir=dist
# 修改 capacitor.config.json：server.url = 全栈访问地址（真机与后端起在同一局域网）
npx cap add android
npx cap sync android
cd android
.\gradlew.bat assembleDebug
# 产物：android\app\build\outputs\apk\debug\app-debug.apk
```

## 真机安装

```powershell
# 方式 1：adb（需开启开发者模式 + USB 调试）
adb install -r android\app\build\outputs\apk\debug\app-debug.apk
# 方式 2：把 APK 传到手机直接安装（允许未知来源）
```

## 关键配置说明

| 项 | 值 | 说明 |
|---|---|---|
| `server.url` | `http://<局域网IP>:8088` | 改为你环境实际 IP；`localhost` 在手机上不成立 |
| `server.cleartext` | `true` | 允许 HTTP 明文（内网演示；上生产 HTTPS 后应移除并改 `false`） |
| `android.allowMixedContent` | `true` | 同上，演示用 |
| AndroidManifest | `usesCleartextTraffic=true` | Android 9+ 默认禁明文，已显式放开 |

## 演示账号（M2 seed）

`demoadult` / `demoteen` / `demosenior`，密码 `demo123456`（Fake 链路：无密钥时评分/TTS/LLM 走 stub）。

## 未做（详见 docs/27）

iOS 平台（需 Mac+证书）、原生录音/推送插件、商店签名（release）、热更新——均为 docs/27 后续切片。

## 删除清单（整体可删）

本目录整体删除即可（`server.url` 型壳不依赖前端构建、不触碰后端；`apps/web` 变更仅 PWA 三文件：`public/manifest.webmanifest`、`public/icons/*`、`index.html` 的 head 两行）。
