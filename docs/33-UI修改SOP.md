# docs/33 · App 端 UI 修改 SOP（标准作业流程）

> 适用：VocalVerse **app 端（/m/* 五页 + 登录）任何 UI 修改**。2026-09-08 定稿（由本轮 UI 反复迭代沉淀）。
> 目的：让 UI 修改「一次到位」——先对齐参考源与组长审美，再动手；做完必须自检、留档、进对日志。

---

## 0. 铁律（先记住，再动手）

1. **先看参考，再谈设计**：组长给的参考（B 站视频《10分钟讲解所有UI/UX概念》、带注释参考图、uiverse 元素链接）是**唯一审美权威**；不确定时先把参考看全、把话听全，**不要先动手再猜**。
2. **文字能省则省**：UI 用设计语言（图标/形状/颜色/层级/对齐）传达信息；字段 label 可去则去；面向用户的文案用英文时按参考原文（如登录页复刻）。
3. **不擅自推翻已认可的部分**：只改反馈点，保留下来的视觉原封不动（本次对话页 = 组员认可后只做细节修正）。
4. **配色/造型取参考基因**：别自创审美——uiverse 元素的配色是数据（色板普查），照基因而非想象。

## 1. 收集与还原反馈

- 逐条列出组长/用户反馈 → 归类：**删除类 / 修改类 / 新增类 / 不动的**（守住第 3 条）；
- 说不清的（如"差远了"）→ 追问到具体（页面/元素/色值），可请对方提供截图标注或参考链接；
- 参考源抓取：Playwright（有头过 Cloudflare）→ 元素详情页 `<textarea>/<pre>` 取 HTML+CSS，预览 iframe 取渲染代码；全局许可（MIT/ISC…）与版权声明入档 `local/uiverse/`。

## 2. 设计决策（动代码前先写）

- 把「参考基因 → 本页落点」映射写清楚（如：炭黑=主按钮、蓝 #2D79F3=交互/选中、细灰边=卡片）；
- **风格基调一旦（组长拍板）就统一**：登录页验收后 = 「白卡细边 clean 语言」，后续页面全按此语言推进，不再回旧风格（旧样式随收尾下线）；
- 涉及**契约**（如 SSE 加事件）：双端（`app/practice/events.py` ↔ `src/audio/sse-types.ts`）+ 契约文档（docs/14）+ 测试同步，无契约盲区。

## 3. 实现

- 代码/测试/文档分 commit；组件与样式文件命名与归属清晰（s- 前缀设计系统样式 / u- 旧样式过渡期并存，收尾统一下线）；
- 图标统一走 unplugin-icons（tabler 主 / ph 深色卡大图形），自绘件仅品牌插画（经组长认可）；新增图标进 `MobileIcon.vue` 时按 1.5px 圆头风格。

## 4. 自检（必做，含截图）

| 项 | 做法 |
|---|---|
| 视觉自检 | Playwright 390×844（deviceScaleFactor 2）全页截图；**有真实后端时走真实链路**（登录→页面→交互态） |
| 交互态 | 额外截 focus/按压/loading/错误态（本次 focus 蓝框线就是靠焦点截图验证的） |
| 对比 | 与参考图/元素并排比对（存 `local/ui-check/`，gitignored） |
| 门禁 | 前端 `pnpm lint && pnpm typecheck && pnpm test:run && pnpm build`；改后端再加 `uv run ruff check . && ruff format --check . && pytest -q`；改契约快照必对账 |

## 5. 文档与日志（放对地方！）

- 设计规格 → `docs/design-system/vocalverse/`（MASTER + pages/*，页面级覆盖优先于 MASTER）+ `docs/31`（唯一真相源）+ README 文档索引登记；
- 调研/选型 → `docs/32` 等编号文档 + 素材库 `docs/assets/`；
- **日志 → `worklog/安卓开发日志.md`（App/UI 线专用）**，主线日志只放 Web/后端/全局事项——**UI 记录不进主线日志**（2026-09-08 组长指正）；
- 署名：执行人按 docs/04 登记（组长 LHRCarrier 的 AI 代工作业 = 「组长 LHRCarrier（AI 代工整理）」）。

## 6. 提交

- Conventional Commits；**代码 / 测试 / 文档 / worklog 分开 commit**；
- 旧视觉被替换时**先留基线 commit 再改**（回滚对照点）；
- 收尾项：旧样式（mobile-uic.css 等）替换完成后整体下线，并把未引用组件（ArtWave/ArtCalendar 等）一并删除。

## 7. 常见翻车点（踩坑清单）

- 用户说"不错"的**页面不要整套重做**——重做过度 = 返工（对话页教训）；
- 别凭想象选配色：从参考元素做**色板普查**（hex 频次统计）再定；
- uiverse 搜索页/API 有 Cloudflare → 用有头浏览器；元素代码在 `<textarea>`/`<pre>`（idle 状态下 HTML 可能为空，需点代码 Tab 或从 SSR 源码取）；
- @iconify-json/phosphor 不存在，正确包名 `@iconify-json/ph`；Lucide 许可为 **ISC 非 MIT**；
- 中文标题禁用负字距；统计数字 ≤24 不抢 display 档。
