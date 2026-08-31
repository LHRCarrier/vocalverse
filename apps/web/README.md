# VocalVerse Web（Vue 3 + TypeScript strict + Vite 6 + pnpm）

## 本地开发（Windows）

```powershell
# 前置：Node 22 LTS（.nvmrc）+ pnpm 9
cd apps/web
pnpm install
pnpm dev                       # http://localhost:5173（代理到 Python:8000 / Java:8080）
```

## 检查

```powershell
pnpm lint          # ESLint 9 flat config
pnpm typecheck     # vue-tsc --noEmit
pnpm test:run      # vitest
pnpm build         # vue-tsc -b && vite build
```

## 契约维护（docs/06 §7）

- 后端（Python/Java）契约变更后，**一步刷新**：`.\scripts\refresh-openapi.ps1`（前提：Python:8000、Java:8080 均已启动；Java 也可不启服务，用 `CONTRACT_SNAPSHOT_GENERATE=1` 跑 ContractSnapshotTest 重写快照）
- 产物链（均入库）：`src/api/specs/python-openapi.json` + `java-openapi.json`（契约快照）→ `src/api/generated/python-api.d.ts` + `java-api.d.ts`（openapi-typescript 生成，`pnpm gen:api`）
- **CI 三关卡**：python-ci 校验「Python 快照 == 后端 OpenAPI」；java-ci 校验「Java 快照 == springdoc 实时渲染」（ContractSnapshotTest，跑在 `mvn verify`）；frontend-ci 校验「生成文件 == 快照（重跑 `pnpm gen:api` 后零 diff）」——任一漂移即红，改契约必须重新生成并提交全链
- 前端 DTO 类型一律从 `src/api/generated/*.d.ts` 导入（`client.ts` 的 `ApiSchemas`），不手写

## UI 与动效（docs/13）

- 组件库：**naive-ui**（只经 `src/styles/theme.ts` themeOverrides 定制，不改组件）；布局工具类：**UnoCSS**（uno.config.ts，品牌色走 tokens）；设计 token 唯一来源：`src/styles/tokens.ts`
- 配色：B 多邻国活力（绿主色 + 柠檬黄激励 + 橙评分），本期仅浅色模式
- 动效：P5.js 仅品牌记忆点（登录页声波 `useP5Wave`、M2 录音波纹），动态 import + 失败降级；**不用 Three.js**（docs/06 §9.2 2D 数字人拍板）
- 图表：M3 报表用 ECharts（按需注册、懒加载）；唱歌"逐句音准对齐图"用 D3 深度定制（仅此一处）
- 路由：全部页面路由已预置（`src/router/index.ts`，占位页收敛未实现页面）；排版参考 docs/13 §3

## 关键约定（docs/06）

- 录音：`src/audio/recorder.ts`（MediaRecorder → WebM/opus，≤60s/20MB，录完再传）
- 流式：`src/audio/sse.ts`（SSE；音频为时间轴权威、文本为字幕）
- API：`src/api/client.ts` 统一 envelope `{code, message, data}` 解析；错误码见 `docs/api/error-codes.md`
- 埋点：M3 接入 `track(event, payload)`（事件表见 docs/06 9.1）
