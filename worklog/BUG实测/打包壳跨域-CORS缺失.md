# 打包壳跨域请求全被拦（python 405 / java None）：CORS 从未配置

> 归档日期：2026-09-10 · 发现人：组长手机实测（方案 B 打包壳）· 模块：`services/python` + `services/java`

## 复现

方案 B 打包壳（页面源 `https://localhost`）登录 → 前端「Failed to fetch」；
`services/java/logs/access_log.*.log` 手机 IP 无任何请求；python 访问日志出现手机 IP 的
`OPTIONS /api/v1/events → 405`。

## 根因

打包壳页面源 `https://localhost`、API 打到本机后端 `http://192.168.0.104:8000/8080` —— **跨域混合内容**。
浏览器对非简单请求（POST + `Content-Type: application/json`）先发 **CORS 预检（OPTIONS）**；
而两个后端**从未配置 CORS**：

- **python 没配**：FastAPI 无 `CORSMiddleware` → 预检被路由当普通 OPTIONS → 405；
- **java 没配**：Spring Security 无 `.cors()`，预检被安全链/路由拦截；
- **开发/容器为什么没事**：dev 靠 Vite 代理同源转发；容器靠 nginx 同源反代——同源请求不涉及 CORS，
  所以这个问题从未暴露，直到打包壳直连后端。

## 修复

- python `app/main.py`：`app.add_middleware(CORSMiddleware, ...)`——精确 origins 列表
  （含 `https://localhost`），`allow_credentials=True`；
- java `SecurityConfig`：`.cors(Customizer.withDefaults())` + `CorsConfigurationSource` bean（同名单）；
- 后续（同批发现）：`auth.ts` 6 处 Java 端点基址硬编码 `'/manage'`（不走 `JAVA_BASE`，打包壳直连失效）
  → 已修；`openSseFetch` 相对 URL 未加 `PYTHON_BASE`（打包壳打到 `https://localhost` 本地服务器）
  → 已修。两处同属「开发靠代理、打包壳必须绝对地址」类。

## 验证

| 项 | 结果 |
|---|---|
| `OPTIONS /auth/login`（Origin=https://localhost） | 200 + `Access-Control-Allow-Origin: https://localhost` + `Allow-Credentials: true` |
| `POST /auth/login`（带 Origin） | 200 + code=0（真实 Chromium 跨域登录成功，非简单 curl） |
| python 预检 | 200 + 完整 CORS 头 |
| 后端门禁 | python `pytest 370 passed` + ruff 全绿；java `mvn spring-boot:run` 编译运行正常 |

## 踩坑

1. **CORS 与「安全上下文」是两回事**：打包壳解决 getUserMedia 靠 `https://localhost`（安全上下文），
   但页面发起跨域 API 仍需后端 CORS——两个条件独立，缺一不可。
2. **`allow_credentials=True` ⇒ `allow_origins` 禁止 `["*"]`**：必须精确列来源（含 `https://localhost`）。
3. **预检判定**：手敲 `OPTIONS`（不带 `Access-Control-Request-Method`）会被当普通请求 → route 405；
   真实浏览器预检必带该头，测试时别用裸 OPTIONS 误判。
4. **本机测试 ≠ 手机测试的充分条件**：本机（回环/局域网直连）绕过防火墙且无浏览器 CORS 拦截，
   机器侧全通不代表手机侧通（本轮后续两个坑都符合——详见另两份档案）。
5. **排查顺序**：手机侧「Failed to fetch」先看后端访问日志有没有手机 IP——
   没有 = 网络/防火墙；有但预检 405 = CORS；有且 401 = 认证/参数。
