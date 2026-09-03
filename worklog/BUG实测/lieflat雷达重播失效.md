# BUG：lieflat 学习报表 · 雷达图点击重播后空白

- **发现**：2026-09-03 · 用户（LHRCarrier）报告：`vv-learning-report.html` 中雷达图点击重播后消失，
  其余图表（F2/F4/L15/流程装饰）点击重播正常。
- **修复**：2026-09-03 · 执行人：LHRCarrier（AI 代工整理）。
- **影响面**：`apps/web/src/assets/lieflat/vv-learning-report.html` 全文件（独立打开 / 画廊 iframe 均受影响）。
  管理端看板（`vv-admin-dashboard.html`）不受影响。

## 复现

1. 打开 `vv-learning-report.html`（双击或 Live Server）；
2. 等待雷达图入场动画完成（滚入视野触发）；
3. 点击雷达图任意位置（点击重播）；
4. 结果：雷达图区域变空白，不再重新绘制；其余图表点击后正常重绘。

## 根因

两份正本的 reveal 机制不同，报表文件把两条路径混用了：

| 正本 | obsReveal | SVG 图重播 | ECharts 图重播 |
|---|---|---|---|
| `basics-porcelain.html`/`lupi-porcelain.html` | `go(): n.innerHTML=''; fn(n)` | 清空后重画 ✔ | 无 ECharts 图 |
| `glance-porcelain.html` | `go(): fn(n)`（不清空） | fn 内自行清空 ✔ | `eReveal`: `getInstanceByDom()→clear()+setOption()` 复用实例 ✔ |

报表文件用了 basics 风格 `obsReveal`（`n.innerHTML=''`）+ glance 风格 `eReveal`：
点击重播时 `innerHTML=''` 先把 ECharts（zrender）挂载在容器里的 canvas DOM 整个拔掉，
`eReveal` 随后拿回**残留实例**执行 `clear()+setOption()` —— 实例仍以为 DOM 在，不会重建 → 空白。
SVG 图擦掉后按 fn 重画，所以正常。

> 看板文件一开始就走的 glance 正本路径（`obsReveal` 无清空 + `eReveal` 复用实例），故无此问题 ——
> 与「其他表都可以」的观察一致。

## 修复

`vv-learning-report.html` 改为 glance-porcelain.html 正本路径：

1. `obsReveal` 的 `go()` 去掉 `n.innerHTML=''`；
2. `eReveal` 保持正本式 `getInstanceByDom(el)||echarts.init(el)` → `clear()` → `setOption()`；
3. 三个 SVG 图（F2 `dayline` / F4 `tickdonut` / L15 `tally`）与装饰弧线 `flow` 的 fn 开头自行
   `s.innerHTML=''`（与 glance 正本内 waffle 等 SVG 图的写法一致）。

## 验证

自动化冒烟（无头 Edge，注入脚本在第 1.5s 自动 `#radar.click()`，`--window-size=1400,3600`
保证全图先入场，`--virtual-time-budget=20000`）：

| 文件 | 点击是否发生 | canvas 数 | svg 元素数(线路/路径/圆/文本) | 结论 |
|---|---|---|---|---|
| 修复前逻辑（仅还原 `n.innerHTML=''`） | ✔（title 带 `CLICKED` 标记） | 0 | 654 | 复现：雷达空白 |
| 修复后 | ✔ | 1 | 654 | 通过：重播正常 |

- 修复前该冒烟必红（canvas 0），修复后通过——测试与缺陷一一对应。
- 前端门禁：`pnpm lint && pnpm typecheck && pnpm test:run && pnpm build` 全绿。
- 内联脚本语法：按 SKILL 自检 7 用 `node --check` 抽检通过。

## 踩坑

- 坑 29（SFC/HTML 双坑之 HTML 侧）：`obsReveal` 清空策略必须与图引擎匹配——**一个文件的共用
  reveal 只能选一条正本路径**；本项目文件里「SVG 图（basics 式）+ ECharts 图（glance 式）」
  并存时必须按 glance 式（fn 自清 + 实例复用）。
- 冒烟脚本自身踩坑：注入的脚本写成了 `<\/script>`（反斜杠转义文本），HTML 不识别其为闭合标签，
  注入脚本从未执行——用 `<title>` 打 `CLICKED` 标记才暴露。判据必须可观测（title/DOM 计数），
  不能只看「没坏」。
