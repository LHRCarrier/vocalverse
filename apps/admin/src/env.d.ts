/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_CONSOLE_BASE?: string
  readonly VITE_OPS_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

// 这里**故意不写** `declare module '*.vue'` 通配声明。
//
// 通配声明会让「导入一个根本不存在的 .vue 文件」也通过类型检查（解析成
// `DefineComponent<Record<string, unknown>, …>`），于是 `SongFormModal.vue` 里
// `import LrcEditorModal from './LrcEditorModal.vue'`（文件不存在）能一路绿到
// `pnpm typecheck`；而 `vite build` 也不会报——因为该弹窗当时没有任何路由引用它，
// Rollup 根本不会去解析这个 import。两处门禁同时失效，只有真正接线到页面的那一刻才炸。
// vue-tsc（Volar）自己就能解析 `.vue`，不需要这条 Vue 2 时代的通配声明。
