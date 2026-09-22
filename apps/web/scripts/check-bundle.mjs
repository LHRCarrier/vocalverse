/**
 * 生产包体积门禁（fe-09，2026-09-09）：断言 `pnpm build` 产物与「模块拆分」约定一致。
 *
 * 依据 rollup manifest（vite build.manifest）按**源模块路径/chunk 图**判定——
 * 不做正文字符串猜测（p5 API 名/「preview」词在业务代码里也会出现，会误报）。
 *
 * 断言（任一违反 → 退出码 1，frontend-ci 红）：
 * 1. **preview 树零体积**：无任何 manifest 键/产物文件含 preview 页源路径
 *    （docs/13 §8：dev-only 子树生产构建常量折叠剔除——AGENTS 预览机制承诺的机器验证版）；
 * 2. **manualChunks 生效**：naive-ui / vue-vendor / vendor 专块存在且资产落盘
 *    （naive-ui 允许在入口条目 imports 里——App.vue 根 Provider 架构必需首屏加载，
 *    但必须独立块：缓存分离、业务发布不重拉）；
 * 3. **p5 零残留**（2026-09-21 酒馆迁移）：p5 唯一使用方（场景对话录音声波
 *    useP5Wave）随模块删除，依赖同步移除——无 manifest 键/产物文件名含 p5；
 * 4. **echarts 懒加载边界**（2026-09-21 docs/53 P2 修订）：`/stats` 报表页是首个消费者，
 *    echarts 允许存在，但必须①**不在入口静态依赖图内**（仅 dynamic import 到达）、
 *    ② 单块 ≤ 500KB（超预算即拒绝——报表页是低频页，不该把首屏或带宽拖下水）。
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
for (const keyPart of ['_naive-ui-', '_vue-vendor-', '_vendor-']) {
  const chunkKey = keys.find((k) => k.startsWith(keyPart))
  const asset = chunkKey ? manifest[chunkKey].file : null
  if (!chunkKey || !asset || !existsSync(path.join(DIST, asset))) {
    fail(`缺少 ${keyPart}* 专块（manualChunks 未生效/被合流）`)
  }
}

// 3) p5 零残留（2026-09-21：唯一使用方随场景对话删除；源路径键 + 产物文件名）
for (const k of keys) {
  if (/p5/i.test(k)) fail(`manifest 含 p5：${k}`)
}
for (const f of files) {
  if (/-p5-[A-Za-z0-9_-]+\.js$/.test(f)) fail(`产物含 p5 块：${f}`)
}

// 4) echarts：允许懒加载块，但不得进入口静态依赖图；且单块 ≤ 500KB
const ECHARTS_BUDGET_KB = 500
const staticGraph = new Set()
const queue = [entry]
while (queue.length) {
  const node = queue.shift()
  const key = typeof node === 'string' ? node : null
  if (!key || staticGraph.has(key)) continue
  staticGraph.add(key)
  for (const dep of manifest[key]?.imports ?? []) queue.push(dep)
}
for (const k of staticGraph) {
  if (/echarts/i.test(k) || /echarts/i.test(manifest[k]?.file ?? '')) {
    fail(`echarts 进了入口静态依赖图：${k}（必须只经 dynamic import 到达）`)
  }
}
const echartsKeys = keys.filter((k) => /echarts/i.test(k) || /echarts/i.test(manifest[k]?.file ?? ''))
if (echartsKeys.length === 0) {
  fail('未找到 echarts 块（/stats 报表页应经 useECharts 懒加载 echarts；若已移除请同步本门禁）')
} else {
  for (const k of echartsKeys) {
    const file = manifest[k]?.file
    if (!file || !existsSync(path.join(DIST, file))) continue
    const kb = Math.round(readFileSync(path.join(DIST, file)).length / 1024)
    if (kb > ECHARTS_BUDGET_KB) fail(`echarts 块超预算：${file} = ${kb}KB > ${ECHARTS_BUDGET_KB}KB`)
  }
}

if (failed) {
  console.error(`\n包体积门禁失败：${failed} 处违规（fe-09）`)
  process.exit(1)
}

const sizes = [...files]
  .map((f) => ({ f, kb: Math.round(readFileSync(path.join(DIST, f)).length / 1024) }))
  .sort((a, b) => b.kb - a.kb)
console.log(`✓ 包体积门禁通过（fe-09）：preview 零体积 / p5 零残留 / echarts 懒加载边界 / 专块齐`)
for (const { f, kb } of sizes) console.log(`  ${`${kb}`.padStart(5)} kB  ${f}`)
