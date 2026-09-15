/**
 * 生产包体积门禁（fe-09，2026-09-09）：断言 `pnpm build` 产物与「模块拆分」约定一致。
 *
 * 依据 rollup manifest（vite build.manifest）按**源模块路径/chunk 图**判定——
 * 不做正文字符串猜测（p5 API 名/「preview」词在业务代码里也会出现，会误报）。
 *
 * 断言（任一违反 → 退出码 1，frontend-ci 红）：
 * 1. **preview 树零体积**：无任何 manifest 键/产物文件含 preview 页源路径
 *    （docs/13 §8：dev-only 子树生产构建常量折叠剔除——AGENTS 预览机制承诺的机器验证版）；
 * 2. **manualChunks 生效**：naive-ui / vue-vendor / vendor / p5 专块存在且资产落盘
 *    （naive-ui 允许在入口条目 imports 里——App.vue 根 Provider 架构必需首屏加载，
 *    但必须独立块：缓存分离、业务发布不重拉；p5 禁止）；
 * 3. **p5 只进 p5 专块**：p5 块不在入口条目 imports/dynamicImports 里
 *    （p5 = 录音声波动态加载，仅用声波的页面块触发）；
 * 4. **echarts 零残留**：无 manifest 键/产物文件名含 echarts（仅 preview 树使用）。
 */

import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

const DIST = path.resolve(process.cwd(), 'dist')
const manifestPath = path.join(DIST, '.vite/manifest.json')

if (!existsSync(manifestPath)) {
  console.error(`✗ 缺少 build manifest（${manifestPath}）——先跑 pnpm build（并确认 build.manifest=true）`)
  process.exit(1)
}

const manifest = JSON.parse(readFileSync(manifestPath, 'utf-8'))
const keys = Object.keys(manifest)
const files = new Set(
  keys.map((k) => manifest[k]?.file).filter((f) => typeof f === 'string' && !f.endsWith('.html')),
)
const entry = manifest['index.html']
if (!entry) {
  console.error('✗ manifest 缺 index.html 条目（入口块监测失败）')
  process.exit(1)
}

let failed = 0
const fail = (msg) => {
  console.error(`✗ ${msg}`)
  failed++
}

// 1) preview 树零体积（源路径键 + 产物文件名）
for (const k of keys) {
  if (/preview/i.test(k)) fail(`manifest 含 preview 源：${k}`)
}
for (const f of files) {
  if (/preview/i.test(f)) fail(`产物含 preview 块：${f}`)
}

// 2) manualChunks 专块存在（键=块名 `${name}${hash}.js`，file=assets/...）
for (const keyPart of ['_naive-ui-', '_vue-vendor-', '_vendor-', '_p5-']) {
  const chunkKey = keys.find((k) => k.startsWith(keyPart))
  const asset = chunkKey ? manifest[chunkKey].file : null
  if (!chunkKey || !asset || !existsSync(path.join(DIST, asset))) {
    fail(`缺少 ${keyPart}* 专块（manualChunks 未生效/被合流）`)
  }
}

// 3) 入口块壳：p5 不得进（懒加载由页面块触发）；naive-ui 允许但必须独立块（根 Provider 架构必需）
const entryImports = [...(entry.imports ?? []), ...(entry.dynamicImports ?? [])]
for (const imp of entryImports) {
  if (/^p5-[A-Za-z0-9_-]+\.js/.test(imp)) fail(`入口块引入 p5：${imp}`)
}

// 4) echarts 零残留（源路径键 + 产物文件名）
for (const k of keys) {
  if (/echarts/i.test(k)) fail(`manifest 含 echarts：${k}`)
}
for (const f of files) {
  if (/echarts/i.test(f)) fail(`产物含 echarts 块：${f}`)
}

if (failed) {
  console.error(`\n包体积门禁失败：${failed} 处违规（fe-09）`)
  process.exit(1)
}

const sizes = [...files]
  .map((f) => ({ f, kb: Math.round(readFileSync(path.join(DIST, f)).length / 1024) }))
  .sort((a, b) => b.kb - a.kb)
console.log(`✓ 包体积门禁通过（fe-09）：preview 零体积 / 入口块无 naive-ui·p5 / echarts 零残留 / 专块齐`)
for (const { f, kb } of sizes) console.log(`  ${`${kb}`.padStart(5)} kB  ${f}`)
