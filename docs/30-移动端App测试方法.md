# 30 · 移动端 App 测试方法（VocalVerse 手机壳）

> 对象：`apps/mobile`（Capacitor 8 远程 URL 型壳，2026-09-04 交付）+ `apps/web` 移动端真形态页面（`/m/home` `/m/chat/:sceneId` `/m/report`）。
> 依据：docs/06 §6 测试策略、docs/27 §8 真机实测表、docs/singing/22-轴线E Q6 八约束、AGENTS.md（门禁/联调页/红线）。
> 核心思想（与 docs/29 §4.2 MobileGym 调研一致）：**功能测试尽量读结构化状态断言（URL/接口响应/DOM 数据），避免截图目测**；视觉验收用「原型基线并排比对」。

---

## 1. 测试分层总览

| 层 | 测什么 | 谁执行/自动化度 | 入口 |
|---|---|---|---|
| L0 静态与单测 | lint/typecheck/vitest、Python/Java CI | 全自动（PR 门禁） | `apps/web` 四连绿等 |
| L1 Web 功能联调 | 登录/首页/对话/报告（Web = App 内容真源） | 全自动可 + 手工 | 浏览器 / Playwright 冒烟 |
| L2 壳专项 | APK 构建、配置烘焙、安装、清网访问、权限 | 半自动（脚本 + 手工） | gradlew / adb |
| L3 真机/模拟器 | 八约束、蓝牙麦、录音链路、手感 | 手工（必须真人过） | docs/27 §8 实测表 |
| L4 体验与兼容 | 机型/内核矩阵、弱网、横竖屏、字体 | 手工 | 本表 §6 |
| L5 商店预检 | 名称/图标/权限文案/隐私/合规 | 手工 + 文档 | §7 |

**优先级原则**：App 是壳、内容是 Web → **L1 通过覆盖了功能正确性的 ~90%**；L2/L3 只盯「WebView 环境差异」；任何版本变更先跑 L0/L1，再 L2/L3。

---

## 2. 测试环境准备（一次，5 分钟）

```powershell
# ① 全栈（必须 healthy）
docker compose up -d
docker compose ps            # 5 个服务 Up(healthy)：postgres/redis/python/java/web
Invoke-WebRequest http://localhost:8088/readyz   # code=0, data.status=ready

# ② 局域网 IP（DHCP 可能变；手机与电脑同一 WiFi）
(Get-NetIPConfiguration | ? { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up'
  -and $_.NetAdapter.InterfaceDescription -notmatch 'vEthernet|VMware|Virtual|Hyper-V|WSL' }
  | % { $_.IPv4Address.IPAddress })
#   若 IP 变化：改 apps/mobile/capacitor.config.json 的 server.url → npx cap sync android
#   → cd android → .\gradlew.bat assembleDebug（build 缓存命中约 30s）

# ③ 装 APK（真机）或模拟器
adb install -r apps/mobile/android/app/build/outputs/apk/debug/app-debug.apk
# 模拟器（带窗口）：& "$env:LOCALAPPDATA\Android\Sdk\emulator\emulator.exe" -avd vocalverse
```

演示账号：`demoadult` / `demoteen` / `demosenior`，密码 `demo123456`（M2 seed）。

> ⚠️ 模拟器注意：NAT 对宿主 LAN IP 偶发不可达 → 用 Chrome 开 `http://10.0.2.2:8088`（宿主机别名）验证同一份产物；真机走 WiFi 直连不受限。

---

## 3. L0 · 自动化门禁（每次改代码后必跑）

```powershell
# 前端（apps/web）
pnpm lint && pnpm typecheck && pnpm test:run && pnpm build
# Python / Java（未触及则跳过；触及按 CI 同款）
# services/python: uv run ruff check . && uv run ruff format --check . && uv run pytest -q
# services/java:  mvnw -B verify
# 契约：改后端契约须 pnpm gen:api 后 git diff 为空（快照零 diff）
```

全绿后才允许进入 L1 手工/半自动。

## 4. L1 · Web 功能联调（浏览器即 App 内容）

> 桌面浏览器打开 `http://<局域网IP>:8088/m/home`（480px 居中容器模拟手机宽度）；或 DevTools 设备模式切 390×844。

| # | 用例 | 步骤 | 期望 |
|---|---|---|---|
| W1 | 登录 | `/login` → demoadult/demo123456 → 登 | 进入 `/m/home`，问候含「成年中级」 |
| W2 | 首页演示帧 | 观察 | 问候/打卡/统计/分段/三张会话卡（Coffee Shop 86.4 / Perfect Night 88.1 / Job Interview 79.8）与 `ui-concept-design/assets/app-home.png` **逐项一致**（图标块分色、字级、间距） |
| W3 | 对话开场 | `/m/chat` | Round 0/N、AI 开场气泡 + TTS 播放；8s 无录音出现救援提示卡 |
| W4 | 录音太短 | 点录 <1s 即停 | 提示「录音太短（x.x s）」，**不推进回合** |
| W5 | 完整回合 | 录 ~3s 停止 | SSE：字幕流 + 音频队列播放 + 覆盖度 +2 chips；回合数 +1 |
| W6 | 收尾 | 打满 N 轮（或超时收尾） | session_end → 跳 `/m/report?reportId=…`，真实报告渲染（coverage/建议） |
| W7 | 报告演示帧 | `/m/report`（无 reportId） | 深紫卡 92.4 + 四维 93/91/88/100% + 逐句 95/88/81，与 `app-report.png` 一致 |
| W8 | token 过期 | 停留 15min 后操作 | 静默 refresh 或回登录页；不出现裸 401 页 |
| W9 | 服务不可达 | `docker compose stop web python-api` | 页面给可操作错误提示（ApiError 文案），不白屏 |
| W10 | PWA | 手机 Chrome 菜单「添加到主屏幕」 | 图标/名称正确，standalone 全屏 |

**结构化断言辅助**（推荐）：F12 Console 执行
`document.querySelectorAll('.u-task').length` / `document.body.innerText` 核对渲染，替代目测。

## 5. L2 · 壳专项（半自动）

| # | 用例 | 步骤 | 期望 |
|---|---|---|---|
| A1 | APK 构建 | `cd apps/mobile/android; .\gradlew.bat assembleDebug` | BUILD SUCCESSFUL；产物 ≈4MB |
| A2 | 配置烘焙 | `Get-Content apps/mobile/android/app/src/main/assets/capacitor.config.json` | `server.url` = 当前局域网 IP + `cleartext:true` |
| A3 | 安装启动 | `adb install -r …; am start -n com.vocalverse.app/.MainActivity` | WebView 加载首页，无 `ERR_*` |
| A4 | 明文访问 | 同上（HTTP 局域网） | Android 9+ 能加载（Manifest `usesCleartextTraffic=true` 生效） |
| A5 | 权限 | 首次点录音 | 弹麦克风授权；拒绝后中文引导（八约束 #6） |
| A6 | 卸载重装 | `adb uninstall` + 重装 | 正常；旧会话/缓存清理 |
| A7 | 版本更新 | 改 server.url → sync → 重打 | 新配置生效（无需应用商店发版） |

## 6. L3/L4 · 真机与体验（手工 · 按 docs/27 §8 实测表）

| # | 项 | 设备 | 通过标准 |
|---|---|---|---|
| B1 | 手势内开麦 | iOS+And | 点击录音同步 start；无「权限不弹/失败」 |
| B2 | HTTPS/安全上下文 | iOS+And | 生产 HTTPS；明文仅演示环境（已标注） |
| B3 | AudioContext resume | iOS | 拿到流即 resume，无静音流 |
| B4 | 增益不可调 | iOS | 「请靠近麦克风」提示存在；不做增益 UI |
| B5 | 切后台/锁屏断录音 | iOS+And | 已采 chunks 保存 +「已截断」提示（当前实现走向：不静默丢） |
| B6 | 权限拒绝引导 | And（国产 ROM 从严） | 中文引导 + 设置入口指引 |
| B7 | 自动播放受限 | iOS（静音键/专注模式） | 手势后 play；NotAllowed 有兜底 |
| B8 | 安装入口 | And（Chrome）/ iOS | 安卓：安装弹窗；iOS：「添加到主屏幕」引导文案 |
| **B9** | **蓝牙耳麦录音**（专项） | iOS+And 各 ≥1 | 跟读/对话录到音频且评分链路可用；不达标 → 走 docs/27 §11 回退（有线/就近），记录型号 |
| B10 | 长录音/连续会话 | 中端机 | 无内存崩溃；上传播放正常 |
| B11 | 内存/热重启 | 反复进出 30 次 | 无泄漏崩溃（结合 `adb shell dumpsys meminfo` 抽查） |
| B12 | 内核版本矩阵 | 华为/小米/OPPO/vivo 各 ≥1、iOS ≥2 台 | 关键路径（W1-W6）全过；差异记录到实测表 |

## 7. L5 · 商店预检（Android 首发）

- [ ] 应用名/图标：`com.vocalverse.app`，图标「V」；名称说明与壳一致
- [ ] 权限声明：RECORD_AUDIO（麦克风，口语练习用）；POST_NOTIFICATIONS 后续推送时补
- [ ] 隐私政策/使用条款：Terms Feed 生成 + Notion 自有 URL（docs/27 §9 清单）
- [ ] 未成年人口径 + AI 生成内容备案评估（docs/27 §9 清单）
- [ ] 测试账号说明留给体验审核；不采集真实用户数据（docs/06 §9.7）
- [ ] **纯套壳风险**：Google Play 4.2 / iOS 4.2 最低功能 —— 优先国内安卓渠道；原生价值点（推送/崩溃上报）为 P1 攻坚项（docs/27 §11）

## 8. 回归与交付判定（DoD）

| 检查 | 命令/动作 | 通过条件 |
|---|---|---|
| 门禁 | §3 全量 | 全绿；契约快照零 diff |
| 关键路径 | W1-W6（真机或模拟器） | 100% 通过 |
| 八约束 | §6 B1-B12 | 全打点 + 豁免项注明理由（真实证据、不假绿） |
| 视觉基线 | 三页截图 vs 原型 PNG 并排 | 逐项一致；差异记录 |
| 工作记录 | worklog/安卓开发日志.md 置顶 + 署名 | 有记录（执行人：组长） |
| 回退 | 壳整体删除或 Web 回退 | 删除清单（apps/mobile/README.md）可执行 |

## 9. 已知缺口（登记，勿当作通过）

1. **麦克风→评分闭环**：模拟器 `-no-audio` 无法测；**必须真机** B9 专项；
2. Release 签名包未做（目前仅 debug）；
3. iOS 平台未构建（无 Mac）；iOS 约束（B1-B8）暂以 WebView=WKWebView 视角手工推理 + 真机补测；
4. E2E 自动化（Playwright/CDP 冒烟脚本）为 P2 沉淀项，当前零散脚本在 `local/cdp-*.mjs`；
5. 统计/打卡/分数为原型演示帧，功能数据 M3 接入后按「值替换、视觉不动」原则做，并回归 W2/W7。

---

*文档依据：docs/27 §8 实测表、docs/29 §4.2（确定性断言理念）、docs/22 轴线E Q6；执行人：组长。*
