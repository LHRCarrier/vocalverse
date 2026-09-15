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
| **B · adb 隧道**（localhost） | 手机→电脑直连不通（路由器/热点**客户端隔离**、防火墙拦、或懒得管网络） | ① 手机开「开发人员选项→无线调试」→ `adb pair <IP:配对端口>`（输 6 位码）→ `adb connect <IP:连接端口>`（或用 USB 调试）→ ② `pwsh -File scripts/phone-reconnect.ps1`（自动补 reverse 8080/8000 + 隧道自检，见 §换环境重连）→ ③ `pwsh -File scripts/build-phone.ps1 -Ip localhost` → ④ `adb install -r …/app-debug.apk` |

**方式 B 原理**：App 页面仍在 `https://localhost`（安全上下文不变），API 改为打手机本机的
`http://localhost:8000/8080`，经 adb 隧道（adb 连接由电脑**主动**建立，不受客户端隔离影响）
转发到电脑后端。CORS 无需改（浏览器按页面源 `https://localhost` 匹配，已在后端白名单）。
注意：adb 断开/重连后需重跑 `adb reverse`；直连重装包前先 `adb reverse --list` 确认隧道在。

## 换环境后重新连接 + 测试（标准步骤，2026-09-11 定稿）

> 触发场景：换 WiFi/回宿舍/重启手机/**重启电脑**/锁屏久了 adb 掉线/换热点——**每换一次环境都走一遍**。
> 核心事实：`adb reverse` 转发**随 adb 连接存在**，断连即被清空；无线调试的**连接端口会轮换**；
> 壳内 API 基址是**构建期写死**的。三者是「换环境后 App 又 `Failed to fetch`」的全部常见成因。

### 第 0 步 · 后端（每次开机都要）

```powershell
cd F:\WorkingL\vocalverse
pwsh -File scripts/dev-up.ps1 start     # postgres/redis + python(:8000) + java(:8080) + vite(:5173)
pwsh -File scripts/dev-up.ps1 status    # 期望三端 LISTENING 且 health=True
```

### 第 1 步 · 连手机 + 补隧道（一条命令）

```powershell
pwsh -File scripts/phone-reconnect.ps1                        # 手机已在线时直接复用并补转发
pwsh -File scripts/phone-reconnect.ps1 -Ip <无线调试页的IP>     # adb 也掉了：自动扫端口找回
pwsh -File scripts/phone-reconnect.ps1 -ConnectPort 41835     # 已知端口，跳过扫描
```

脚本会：清 `offline` 残留条目 →（必要时）mDNS/扫端口找回连接 → 去重（避免 `more than one device`）
→ 打印机型 → 补 `adb reverse tcp:8080/8000` → **从手机侧 curl 自检**并打印两个 200。

手动等价步骤（脚本不可用时）：

```powershell
adb devices -l                              # 必须是 <序列号> device；offline 先 adb disconnect <序列号>
adb reverse tcp:8080 tcp:8080; adb reverse tcp:8000 tcp:8000
adb reverse --list                          # 期望看到 host-xx tcp:8080/8000
adb shell "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8000/readyz"          # 期望 200
adb shell "curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8080/actuator/health" # 期望 200
```

### 第 2 步 · 判断要不要重打包

| 情况 | 动作 |
|---|---|
| 手机上的包是**隧道版**（`-Ip localhost`）且本地后端端口没变 | **不用重打**，补完转发就能用 |
| 装的是**直连版**（`-Ip <电脑IP>`）而电脑 IP 变了 / 换到客户端隔离的网络 | 改用隧道版：`pwsh -File scripts/build-phone.ps1 -Ip localhost` → `adb install -r …app-debug.apk` |
| 改了 `apps/web` 代码 | 必须重打（壳内是构建产物，无 HMR）：同上再 `adb install -r` |

怎么确认手机上装的是哪版（读装机包里的基址，不用猜；手机侧 shell 不展开 `*`，所以先列名再取）：

```powershell
$apk = (adb shell pm path com.vocalverse.app) -replace 'package:',''
adb shell "f=`$(unzip -l $apk | awk '/assets\/public\/assets\/index-.*\.js/{print `$4; exit}'); unzip -p $apk `"`$f`" | grep -o -E 'https?://[a-zA-Z0-9.:_-]+' | sort -u"
# 期望（隧道版）: http://localhost:8000 / http://localhost:8080
# 直连版会打出 http://<电脑IP>:8000 / :8080 —— 那就得改 -Ip localhost 重打
```

> 说明：`$apk` 由 PowerShell 展开，`$f`/`$4` 要留给手机侧 shell，故写作 `` `$f `` / `` `$4 ``；
> 手机侧 shell **不展开 `*`**，所以要 `unzip -l` 先列名再 `unzip -p` 取文件（上面这条已验证可直接跑）。

### 第 3 步 · 验证 App（三层，逐层加严）

1. **页面起得来**：手机打开 App → 登录页无红字。
2. **接口通**：登录（`demoadult` / `demo123456`）→ 进得去 `/m/home`；同时看后端日志有没有**来自隧道的请求**
   （java `services/java/logs/access_log.*.log` 来源 `127.0.0.1`，python `local/dev-logs/python-8000.out.log`）。
3. **要更硬的证据**（页面报错但看不到原因时，比 logcat 可靠）——用 WebView DevTools：

   ```powershell
   adb shell "cat /proc/net/unix | grep webview_devtools"        # 取 <pid>
   adb forward tcp:9223 localabstract:webview_devtools_remote_<pid>
   curl http://127.0.0.1:9223/json/list                           # 拿页面 URL/标题
   node local/cdp-eval.mjs "({url:location.href, title:document.title})"   # 在真机页面里求值
   ```

   `local/cdp-eval.mjs` 可注入脚本做端到端验证（例：填账号点登录后看 `location.href` 是否变成 `/m/home`）。

### 第 4 步 · 常见失败速查

| 症状 | 成因 | 处置 |
|---|---|---|
| App 红字 `Failed to fetch` | ① `adb reverse` 被清空；② 包是直连版而手机连不上电脑 | 先跑 `phone-reconnect.ps1`；仍不行就读包内基址（第 2 步）并改隧道版 |
| `adb connect` 报 `10061`（积极拒绝） | 无线调试**端口轮换**了，你用的是旧号 | 回手机「无线调试」页抄新端口，或让脚本扫端口找回 |
| `adb connect` 报 `10060`（超时） | 手机息屏打盹 / 掉出 WLAN | 叫醒手机、停在无线调试页，再跑脚本（脚本会按轮重试 + ICMP 预检） |
| `adb: more than one device/emulator` | 同一设备有 IP 直连 + mDNS 两条记录 | 脚本会自动去重；手动：`adb disconnect <多余条目>` |
| 手机能连 8000 但连不上 8080 | 本机安全软件/防火墙按**程序**拦 java（火绒网络控制、`OpenJDK Platform binary` Block 规则） | 隧道版不受影响；要修直连版就给当前 JDK 路径放行（需管理员，改系统安全配置前先确认） |
| 电脑 `dev-up status` 里 vite 是 down | `apps/web` 依赖树不完整（`.bin` 为空） | `cd apps/web; pnpm install` 后重跑 `dev-up.ps1 start` |


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
