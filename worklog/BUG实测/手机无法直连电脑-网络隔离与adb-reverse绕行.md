# 手机无法直连电脑（net::ERR_CONNECTION_TIMED_OUT）：客户端隔离 + adb reverse 绕行

> 归档日期：2026-09-10 · 发现人：组长手机实测全链路诊断 · 模块：网络环境（路由器/热点）+ App 联调方式

## 复现

打包壳手机登录 → 「Failed to fetch」。此前所有软件层修复（CORS/防火墙/基址）完成后仍失败。
最终用 CDP 直连手机 WebView（`adb forward → webview_devtools_remote_<pid>`）抓到铁证：

```
REQ   OPTIONS http://192.168.0.104:8080/auth/login        ← 请求确实发出（混合内容仅为 warning，未拦截）
FAILED errorText=net::ERR_CONNECTION_TIMED_OUT            ← TCP 握手超时（SYN 无响应）
```

## 根因（两层叠加）

1. **手机出站被策往蜂窝**：`ip route` 显示 `main` 表无默认路由、`ip rule` 各蜂窝网表带默认路由，
   `dumpsys connectivity` 激活网络为 MOBILE——App 出站包走蜂窝 → 局域网 IP 不可路由 → 超时。
   `adb shell svc data disable` 后手机切回 WiFi（VALIDATED、默认路由经 wlan0）。
2. **客户端隔离（最终根因）**：切回 WiFi 后，**手机→网关通（0% 丢包）、手机→本机 ICMP/TCP 全部不通、
   电脑→手机通（4ms）**——单向互访被断，是路由器/热点的**客户端隔离（AP isolation）**特征。
   之前 App 曾能收到 python 响应（401/200）→ 隔离是**随后被开启或间歇出现**的环境变化，
   早上联调时不存在（远程壳 + 代理同源，且当时互访正常）。

## 修复（绕行 · adb reverse）

客户端隔离挡住了「手机主动连电脑」，但 **adb 连接是电脑主动发起的**（走既有连接不受隔离影响）→
用 `adb reverse` 让手机 `localhost` 反向转发到电脑端口：

```powershell
adb reverse tcp:8080 tcp:8080
adb reverse tcp:8000 tcp:8000
```

App 侧配合：重新以 **`localhost` 为 API 基址**打包（`scripts/build-phone.ps1 -Ip localhost`）——
页面源仍为 `https://localhost`（安全上下文不变），API 打到手机本机 `http://localhost:8000/8080`
→ 经 adb 隧道到达电脑后端。CORS 无需改（浏览器按**页面源** `https://localhost` 匹配，已在名单）。

## 验证

| 项 | 结果 |
|---|---|
| 手机 → 网关 ping | ✅ 0% 丢包（链路本身正常） |
| 手机 → 本机 ping / nc 8000 / nc 8080 | ❌ 全部超时（直连被隔离） |
| 机器 → 手机 ping | ✅ 4ms（对称性被破坏 = 隔离特征） |
| 手机 → `127.0.0.1:8080`（adb reverse 后 nc） | ✅ 通（隧道生效） |
| 手机 App 登录（localhost 基址 + 隧道） | ✅ 200 / code=0，进入 `/m/home` |

## 踩坑

1. **「ping 通」≠「TCP 通」**：手机→本机 ICMP 不通而 TCP 也不通，但机器→手机 ICMP 通——
   单向证据链是判定隔离的关键；只测一个方向会得出错误结论。
2. **本机侧一切正常 ≠ 手机侧正常**：防火墙/CORS/后端日志来自机器视角；手机视角必须用
   CDP（WebView DevTools）或访问日志兜底，本次最终靠 CDP 的 `loadingFailed.errorText` 一锤定音。
3. **诊断 WebView 的姿势**：`adb forward tcp:9223 localabstract:webview_devtools_remote_<pid>`
   → `http://127.0.0.1:9223/json/list` → CDP `Network.enable`，比 logcat 可靠
   （App 捕获错误不 console.error，logcat 里什么都看不到）。
4. **环境类问题改代码无用**：遇到「手机连不上」先定位是环境（隔离/防火墙/网络）还是代码
   （可照本档案的递归排查：CDP 抓网络 → 后端访问日志 → 防火墙 → 网络）。
5. `local/cors-test/`（gitignored）保留了三份诊断工具：headless Chrome 跨域实弹页、
   https 静态服务脚本、CDP 抓包脚本（capture-cdp.mjs），复现路径可重跑。
