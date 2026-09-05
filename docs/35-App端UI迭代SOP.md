# docs/35 · App 端 UI 迭代 SOP（人工反馈驱动 · 2026-09-05 定稿）

> 状态：**定稿（组内执行规范）**。与 docs/33 的关系：33 = 单次 UI 修改 SOP（流程骨架，必须主流程）；
> **本文 = 2026-09-05 全天高密度 UI 迭代沉淀的完整执行细则**（硬性设计规则 + 验证体系 + 踩坑红榜），
> 新 UI 任务按 33 走主流程，细则与边界以本文为准。
> 适用范围：apps/web 移动端（/m/* 全部页面、全局组件、设计系统规格）。

---

## 0. 迭代六步循环（全天验证有效，照此执行）

**反馈 → 归类 → 决策先写 → 实现 → 门禁+截图自检 → 规格/日志/分 commit**

1. **收集反馈**：组长/组员截图或文字 → 逐条归类（删除类 / 修改类 / 新增类 / 不动的；守住 docs/33 铁律 3）；
2. **决策先写**：设计改定（含 1~3 轮澄清）先落处 `docs/design-system/vocalverse/pages/*.md`（页面级优先于 MASTER）
   或 `docs/31`；**含糊就追问，禁止按猜测实现**（今天 8 个拍板轮全部来自组长一句澄清）；
3. **实现**：组件化 + 局部改样；**不动已通过验收的视觉**（只改反馈点）；
4. **门禁**：`pnpm lint && pnpm typecheck && pnpm test:run && pnpm build` 全绿；
5. **自检（必做，见 §2）**：Playwright 截图 + 坐标实测 + 状态覆盖；
6. **归位**：规格同步（README 索引登记）→ 工作日志置顶（**UI/设计记录 → `worklog/安卓开发日志.md`**，署名按 docs/04）→
   分 commit（code / test / docs / worklog 严格分开，Conventional Commits 中文正文）。

## 1. 硬性设计规则（定稿 RED LINE，新增页面/组件必须符合）

| # | 规则 | 具体值 |
|---|---|---|
| 1 | **顶栏图标统一 tabler**（`~icons/tabler/*`）无底 icon-only | 内容区图标 20px + 44px 触控区；hover 墨色/active 缩放；**禁止自绘 MobileIcon 进顶栏/底栏**（内容区可用，1.5px 圆头） |
| 2 | **头像固定最左侧第一位** | 顶栏左侧 = 头像（36px）→ 离开钮（如有）→ 标题（grid 三列 `1fr auto 1fr` 真居中）→ 右侧 actions |
| 3 | **离开钮 = tabler `logout` scaleX(-1) 镜像**（门+箭头朝左） | 34px 与头像同级；**项目无 ← 语言**；语义 = 离开当前页（学习组功能页 → /m/learn；报告页 router.back()） |
| 4 | **底栏双场景分组** | 社区组（🏠/🔍/＋📝/📚学习出口/✉️）· 学习组（🏠出口/☕/📖中央/🎵/💬）；5 位对称（左右各 2 + 中央正位）；沉浸页（/m/compose）无底栏；新增页面归属写 TabBar `group` computed |
| 5 | **唯一入口原则** | 一屏内同一功能只能有一个入口（顶栏/底栏/页内不重复）；重复入口删除（已清：口语「选择场景/自由对话」、练习首页全卡） |
| 6 | **全局件只挂 App.vue** | 账户抽屉（ui store drawerOpen）· 全局 toast（ui store showToast）· 底栏；**页面禁止自建 toast/抽屉** |
| 7 | **等级/经验与社交联动同一数据源** | `stores/progress.ts`（xp + 等级表 + addXp）；展示面 = 学习页画像卡/我的档案卡/抽屉/社区帖子 meta/私信列表·会话头，全部 `progress`/`level` 字段驱动 |
| 8 | 标题中文 0 字距；触控 ≥44px；过渡只动 transform/opacity/box-shadow；`prefers-reduced-motion` 全降级 | 沿用 docs/31 硬规则 3/4 |

## 2. 验证体系（自检必做，缺一不可）

### 2.1 Playwright 截图（390×844 @2x → `local/ui-check/`，gitignored）

- **零后端 mock 鉴权**（本机无 Java 时）：
  ```js
  await page.addInitScript(() => { localStorage.setItem('vv_token','t'); localStorage.setItem('vv_refresh','r') })
  await page.route('**/manage/auth/refresh', r => r.fulfill({ status:200, contentType:'application/json',
    body: JSON.stringify({ code:0, message:'ok', data:{ accessToken:'t', refreshToken:'r', expiresIn:3600, userId:1 } }) }))
  await page.route('**/manage/auth/me', r => r.fulfill({ ...同上, data:{ userId:1, username:'demoadult', nickname:'演示用户', level:'L3' } }))
  ```
- **环境**：playwright 装临时目录（`$env:TEMP\vv-ui-check`，**脚本复制到该目录运行**——ESM 解析就近）；版本匹配本机浏览器缓存
  （chromium-1223 ↔ **playwright@1.60.0**，`npm i playwright@1.60.0` 后直接跑，零下载）；
- **跑前必杀 5173**：`Get-NetTCPConnection -LocalPort 5173 -State Listen` → `Stop-Process`——残留旧 vite 进程会提供**陈旧 CSS**
  （今天顶栏「无样式崩溃」就是它，不是代码问题）；
- **状态覆盖**：默认/按压(:active)/激活/空态/滚动到底部/交互后（发表评论、投币金、自动回复等）；真机后端形态（AI 回复/评分）由组长复验。

### 2.2 坐标实测（布局问题必须实测，禁止目测）

```js
const info = await page.evaluate(() => ({
  page: document.querySelector('.u-fc-page')?.getBoundingClientRect(),
  bar: document.querySelector('.u-fc-bar')?.getBoundingClientRect(),
  tab: document.querySelector('.u-tabbar')?.getBoundingClientRect(),
}))
```
判断：内容 bottom (< tab top 留 ≥10px)；容器 bottom ≤ 视口高。**典型陷阱**：100dvh 容器若是顶栏后的流元素
→ 页面总高超视口（今天 u-fc-page 超 66px，输入条落进 tab 区）。

### 2.3 测试断言注意（今天实战）

- **@vue/test-utils 不支持 `hasText`**（Playwright 才有）→ `findAll(...)[i]` 或 `find(b => b.text().includes(...))`；
- 组件用 pinia store（TopBar/Drawer/Learn/Messages…）→ 测试 `beforeEach(() => setActivePinia(createPinia()))`；
- 断言别写反初始态（收藏星初始 true → 点击是取消）；`v-for` 卡点按视图访问需 flushPromises；
- 改 props/删函数后检查未使用 import（lint no-unused-vars）。

## 3. 踩坑红榜（今日实战，全部有教训）

1. **CSS 类名不得跨语义复用**：`.u-chat`（气泡行）vs 私信会话容器（height:100dvh 后定义覆盖）→ 气泡行被撑成整屏白卡；
   教训：同名类名 + 后定义覆盖 = 常规陷阱；**类名带页面/语义前缀**（u-chat-page 等）；冲突应靠「有气泡状态的全页面冒烟截图」抓；
2. **git checkout -- 回滚该文件全部未提交改动**（包括本轮新增字段）——改了 interface 又回滚 = 静默丢字段；
3. **PowerShell 写文件**：`Get-Content + Set-Content -NoNewline` 会把行数组压成一行——这类批量改一律用 edit 工具或显式 `-join "`n"`；
4. **eslint --fix** 会自动改 textarea 自闭合等——跑完看 diff；
5. **残留进程**：vite/dev server 杀干净再自检（见 §2.1）；同样的坑存在于任何本地端口服务；
6. 门禁 `ERR_PNPM_NO_IMPORTER_MANIFEST_FOUND` = 在仓库根跑了 pnpm——**一律 `apps/web` 目录**；
7. 中文文件名/路径在 git 显示为转义序列——message/commit 用中文无碍。

## 4. 文档与日志归位（新人必背）

| 产出物 | 去向 |
|---|---|
| 页面/组件设计改定 | `docs/design-system/vocalverse/pages/*.md`（页面级优先优先）+ `docs/31`（唯一真相源） |
| 参考/调研 | `docs/3x` 编号文档 + `docs/34`（X 复刻参考书） |
| 参考源素材 | `local/uiverse/`、`local/ui-check/`（均 gitignored） |
| 日志 | **UI/设计记录 → `worklog/安卓开发日志.md`**（App 线专用；主线日志只放 Web/后端/全局事项） |
| 署名 | 执行人按 docs/04 登记；AI 代工 = 「组长 LHRCarrier（AI 代工整理）」 |

## 5. 名词与结构备忘（当前移动端全貌）

- **双场景**：社区（浸 · 社区/搜索/私信）+ 学习（练+唱 · 场景对话/笔记/唱吧/自由对话）；两首页互切 = 底栏出口；
- **学习页画像焦点**：Duolingo 式 LV 徽章 + 金色经验条 + 速览/趋势（M3 讯飞词级数据替换演示帧）；
- **等级联动**：完成练习 +XP（场景回合 +15 / 自由回合 +5，演示规则）→ `progress` store → 全 app LV 展示；
- **沉浸页**：/m/compose（发帖，无底栏）；其余一切页面属于社区组或学习组。
