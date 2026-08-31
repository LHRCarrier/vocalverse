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

- 后端（Python）契约变更后，**一步刷新**：`.\scripts\refresh-openapi.ps1`（前提：Python 服务已起在 8000）
- 产物链（均入库）：`src/api/specs/python-openapi.json`（契约快照）→ `src/api/generated/python-api.d.ts`（openapi-typescript 生成，`pnpm gen:api`）
- **CI 双关卡**：python-ci 校验「快照 == 后端 OpenAPI」；frontend-ci 校验「生成文件 == 快照（重跑 `pnpm gen:api` 后零 diff）」——任一漂移即红，改契约必须重新生成并提交全链
- 前端 DTO 类型一律从 `src/api/generated/python-api.d.ts` 导入（`client.ts` 的 `ApiSchemas`），不手写

## 关键约定（docs/06）

- 录音：`src/audio/recorder.ts`（MediaRecorder → WebM/opus，≤60s/20MB，录完再传）
- 流式：`src/audio/sse.ts`（SSE；音频为时间轴权威、文本为字幕）
- API：`src/api/client.ts` 统一 envelope `{code, message, data}` 解析；错误码见 `docs/api/error-codes.md`
- 埋点：M3 接入 `track(event, payload)`（事件表见 docs/06 9.1）
