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

## 关键约定（docs/06）

- 录音：`src/audio/recorder.ts`（MediaRecorder → WebM/opus，≤60s/20MB，录完再传）
- 流式：`src/audio/sse.ts`（SSE；音频为时间轴权威、文本为字幕）
- API：`src/api/client.ts` 统一 envelope `{code, message, data}` 解析；错误码见 `docs/api/error-codes.md`
- 埋点：M3 接入 `track(event, payload)`（事件表见 docs/06 9.1）
