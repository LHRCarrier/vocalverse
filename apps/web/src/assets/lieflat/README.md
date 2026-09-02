# lieflat 资产（VocalVerse 表盘美化 · 预览版）

本目录收录按 [lieflat-charts](https://github.com/larashero3-dotcom/lieflat-charts) 技能（`SKILL.md` /
`catalog.md` / `report-catalog.md`）为 VocalVerse 表盘数据生成的单文件 HTML 高保真预览。

## 文件

| 文件 | 模式 | 体系 × 色板 | 内容 |
|---|---|---|---|
| `vv-admin-dashboard.html` | 图表模式 | Glance 系 × PORCELAIN | 四指标 KPI 卡 + 5 图（G8 / G3 / G4 / G13 / G14），口径 docs/06 §9.1 |
| `vv-learning-report.html` | 报告模式 | R09 骨架 × PORCELAIN | 数据故事仪表盘：4 图（雷达 / F2 / F4 / L15）+ 右栏 6 KPI 卡 |

> 两份交付各自锁定一种色彩系统（PORCELAIN，`color-presets.js` 正本），未新增色值。
> 全部为演示数据（与 `AdminDashboardPreview.vue` 的演示值同源），接入真实接口后替换数据即可。

## 选型审计记录（SKILL 自检 10 / 12 / 13）

**管理端看板**（用户明确要求表盘 → Glance 系入场，SKILL 第零节 4）：

- 淘汰 Lupi Editorial / Lupi Basics（F1–F17）：看板读者是运营/老师，阅读任务是 <10s 扫出结论
  （SKILL 三节：Glance = 周报 / dashboard / 三秒快读）；Lupi 语法（逐记录、发丝线、30s 细读）
  与监控场景冲突；四指标 + 构成 + 热度均为「提前聚合好的结论」，无逐记录需要摊开。
- 逐图候选与淘汰：趋势（双序列）G8 双区 vs F2/F3（单序列，不承载投入/产出对照）；
  场景排行 G3 粗柱 vs F1 Rung Bars（F1 单位可数 = 年报语境，看板用不上单位分解）；
  构成 G4 Dot Waffle vs F4 Tick Donut / L14 Hundred Field（快读语境 waffle 优先，F4/L14 归报表）；
  水平分布 G13 Big Slice（占比×强度双编码）vs G2 Petal Rose（花瓣皮只适用近似等分，
  L1 18% / L2 34% 宽窄悬殊，会互相遮蔽）；
  时段热度 G14 Single Axis vs F10 Dot Heat（同数据形状，看板取 Glance 单轴版）。

**用户端学习报表**（报告模式 → report-catalog 选型）：

- R09 数据故事仪表盘（1080 / 4 图 + KPI / Porcelain / 仅字体联网）✅ 锁定；
  淘汰 R12 周报速览（需 Chart.js + ECharts CDN，依赖最重）、R03 年度数据海报（Wire，无 KPI
  快照槽位）、R05 影响力故事（2 图低密度，装不下多维分析）、R11 研究简报卡（600×1000 定尺太窄）。
- 页内图型：雷达 = SKILL §7 例外（不重构雷达，ECharts 原生 + porcelain 换肤）；
  F2 Hairline Line（30 天逐日总分）vs L3 Barcode Lollipop（90 天级，数据只有 30 天）；
  F4 Tick Donut（细读构成）vs G4 Waffle（快读）——报告语境取 F4；
  L15 Ballot Tally（易错语言点多选百分比，各选项独立 0–100，唯一诚实编码）。

## 许可与合规（⚠️ 必须读）

- 上游仓库 **PolyForm Noncommercial License 1.0.0**：仅限**非商业用途**。
- 本项目（实训/教学项目）以非商业用途使用；若未来商用，须向作者申请商业许可或改用自绘。
- 上游模板截图/样式仅作结构与配色参照；产品配色（PORCELAIN 色值）为上游开源分发。
- 单文件交付依赖：在线字体（Google Fonts）+ ECharts / Chart.js CDN，离线打开时图表缺字体/CDN。

## 说明

- 预览入口：`apps/web` 开发环境 → 前端预览画廊 → «Lieflat 表盘»（`/preview/lieflat`）。
- 渲染机制：`src/components/LieflatChart.vue`（sandbox iframe + srcdoc + 高度桥接）。
- 上游仓库镜像（只用于对照，不入库）：本地 `%TEMP%\lieflat-charts`。
