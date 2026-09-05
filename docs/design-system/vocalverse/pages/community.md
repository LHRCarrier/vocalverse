# Community Page Overrides（社区主页 · /m/home · 2026-09-05 组长拍板版）

> **PROJECT:** VocalVerse — 本文件覆盖 MASTER.md 的页面级规则（页面级优先，docs/31 §5 收尾统一迁移 token 时并线）。
> **设计意图（组长拍板 2026-09-05）**：英语社区主页 = X 式结构复刻（顶栏 + 领域文字标签 + 混合信息流 + 互动行），
> 用 uic 纸面语言（`u-*` 类，`mobile-uic.css`）；**结构参考 = docs/34 §4/§5（Fwitter 组件粒度与交互），
> 只借结构/交互，不搬 Fwitter/X 视觉**（docs/34 §6 反借鉴清单）。
> **本页状态（2026-09-05）**：演示帧（8 条演示数据；点赞本地交互；分享/评论/投币展示；领域 Tab 过滤）。

## 页面结构（已拍板，本次不改变）

1. X 式顶栏：左头像（**点击 → X 式账户抽屉**：用户卡 + 你的资料/消息/设置与隐私 + 退出登录）/ 中「社区」Logo / 右加好友（演示 toast）——随滚动移出屏幕，非 sticky；
2. 领域文字标签行：为你推荐▾（全量混排）/ 新闻稿 / 教学分享 / 海外生活；激活 = 加粗墨色、下细分隔线；
3. 混合信息流：帖子图文卡 / 视频封面卡（播放钮 + 时长角标 + 标签渐变块）；
4. 互动行（X 式）：评论 / 点赞 / 投币 / 分享（点赞可交互，其余展示）；
5. 底部留言「内容为演示数据…M3」。

## 组件拆分（docs/34 §4 · 本次改造）

| 组件 | 职责 | 对应 Fwitter | 说明 |
|---|---|---|---|
| `MobilePostCard.vue` | 帖子卡容器 | `tweet.dart` | 头部作者行 + 标题 + 摘要 + 媒体 + 互动行；props=post，emit=toggle-like |
| `MobilePostMedia.vue` | 配图/视频封面 | `tweetImage.dart` | 渐变块 + 播放钮（视频）/ 时长角标 / 标签；无配图不渲染（v-if 在 Card） |
| `MobilePostActions.vue` | 互动行 | `tweetIconsRow.dart` | 4 项 + `fmt` 千位缩写（1240→1.2k）；点赞为 button（aria-pressed） |

- 类型与演示数据从视图移出：`src/types/community.ts`（CommunityPost/PostMedia/PostStats/Tab）+
  `src/data/community-demo.ts`（8 条演示数据 + 标签）——M3 换真实接口时只动数据源（docs/34 §7.2）；
- 视图 `MobileHomeView.vue` 只保留：顶栏/标签行/状态分支/演示注记/toast。

## 状态规范（docs/34 §5 P0 · 本次新增）

| 状态 | 规则 |
|---|---|
| 点赞默认 | 图标+数字（sub 色）；`aria-pressed=false` |
| 点赞按压 | `:active` 60ms `scale(0.94)`（transform only，docs/31 硬规则 4） |
| 点赞激活 | `is-liked`（红）+ 图标 pop 动画（240ms scale 1→1.28→1，仅一次）+ 计数随状态 ±1（双通道：颜色+数值+aria-pressed） |
| 加载态 | 骨架卡 ×3（`u-comm-skel__*`：头像圆块 + 两行 + 媒体块；opacity 呼吸 1.2s 循环）；`prefers-reduced-motion` 关闭；**M3 接入真实流时 >300ms 才显示**（docs/31 硬规则 3） |
| 空态 | 居中：info 图标（u-weak 圆底）+「该领域暂无内容」+ 副文案 + 刷新按钮（`u-comm-empty__*`）；出现条件（M3）= 当前领域无帖子 |
| 失败态 | M3 接入时复用空态结构 + 错误文案（`role=status` + aria-live）；本次仅预留分支 |

## 无障碍

- 点赞按钮：`aria-pressed` + `aria-label`（取消点赞/点赞）；信息流卡片 `aria-label="<作者> 的动态"`；
- 顶栏 icon-only 按钮 `title` + `aria-label`（既有，保留）；
- 骨架区 `aria-busy="true"` + `aria-label="动态加载中"`。

## 交互边界（2026-09-05 组长升级拍板：互动全交互 · 演示帧级，本地不落库）

- **评论**：点击 → 底部评论面板（`MobileCommentsSheet`，复用 u-sheet 体系）：标题摘要 + 演示评论列表 + 发表输入条（enter/发送钮）；
  发送 → 追加「你 · 刚刚」评论 + 计数 +1；**嵌套评论楼 = M3**（docs/34 §5 P1）；
- **投币**：button toggle——已投币 = `--u-star` 星黄 + pop + 计数 ±1（与点赞同交互语言）；M3 对齐真实投币模型（累积/余额/扣减）；
- **分享**：`navigator.share` 可用 → 系统分享面板（成功 toast「已分享」）；不可用 → `clipboard.writeText(演示链接)` + toast「链接已复制」；
  均失败 → toast「复制失败，请手动复制」；**分享计数 = 转发数语义，点击不加计**；
- 点赞：is-liked 红 + aria-pressed + pop（既有）；四个操作全部为 button，`aria-label` 齐全；
- M3 接真实流（docs/10 注记：sessions/attempts JOIN 派生 + post_likes/comments/coins）时**只换数据源，组件层不返工**（docs/34 §7）；
- 分页游标/下拉刷新/新帖提示条 = M3 真实流（docs/34 §5-1），pinia store 届时新增，本页不改。

## 后续（M3）

- 分页/刷新/新帖提示 → `useCommunityFeed`（pinia）；
- 评论楼（嵌套 + 引用帖灰卡）、帖子操作 bottom sheet（docs/34 §5 P1）；
- 社区页 token 随 docs/31 §5 收尾统一迁移（`u-*` → `s-*`），本页视觉基线以现有 uic 纸面语言为准。

## 导航（2026-09-05 组长拍板 4：底部 tab 全局化 + ＋发帖 + 搜索 tab）

- **底部 Tab 栏全局挂载**（App.vue，组件内按路由显隐——X 式二级页无底部栏）：

| 显示 | 隐藏（二级页） |
|---|---|
| `/m/home` 社区 · `/m/search` 搜索 · `/m/chat` 口语（含 `/:sceneId`）· `/m/sing` 唱吧 · `/m/messages` 私信 | 会话 `/m/messages/:id` · 报告 · 我的 · 自由对话 |

- **6 位布局**：社区 / **搜索**（放大镜 tab → 搜索页）/ **＋发帖**（中央主行动，X 同语义）/ 口语 / 唱吧 / 私信；
- **搜索页 `MobileSearchView`**（演示帧）：大搜索条（放大镜+清除）+ 分类标签行（帖子/用户/教程，X 式）+ 历史/热门 chips（点击回填）；
  结果源 = 社区演示帖 + 演示用户/教程；M3 接真实搜索索引，词汇速记「划词即查」预留挂点（docs/34 §3）；
- **发帖页 `MobileComposeView`**（演示帧）：X compose 同款——顶栏右「发帖」蓝胶囊（空内容禁用）+ 正文文本域（280 字计数）+
  工具行（图片/视频/话题/表情 → 演示 toast）；发布 = toast + 回社区；M3 接真实发布（帖子+视频双形态入流）；
- 口语页底部 dock 随全局 tab 栏上移 56px（`.u-chat-dock { bottom: 56px }`）；

> 本节承接拍板 3 的「统一顶栏 + 全局抽屉 + 全局 toast」，与此共存：

- **统一顶栏 `MobileTopBar`**（每个移动页面都有）：**grid 三列 `1fr auto 1fr`（标题真居中，不受左右宽度影响）**；
  左 = 返回（二级页）+ **全局头像**（点击开账户抽屉）；中 = 页面标题（X 式居中，中文 0 字距）；
  右侧 = 按页面功能放 1~2 个**无底 icon-only Tabler 线性图标**（与底部 tab 同源：20px 图标 + 44px 触控区，
  Grok 对照定稿 2026-09-05）：

| 页面 | 标题 | 右侧扩展按钮 |
|---|---|---|
| 社区 `/m/home` | 社区 | 加好友（演示 toast）· **写消息**（→ /m/messages） |
| 私信列表 `/m/messages` | 私信 | 新消息（演示 toast）· 私信设置（演示 toast） |
| 会话 `/m/messages/:id` | 对方名 | 返回 · 会话信息（演示 toast） |
| 我的 `/m/me` | 我的 | 分享档案（系统分享/复制）· 设置（滚到页内设置区） |
| 唱吧 `/m/sing` | 唱吧 | 分享歌曲（系统分享/复制） |
| 报告 `/m/report` | 评分报告 | 返回 · 分享报告 |
| 口语 `/m/chat` | 口语 | 返回 · 选择场景（打开场景弹层） |
| 自由对话 `/m/free-chat` | 自由对话 | 返回 · 设置（→ /m/me） |

- **账户抽屉 App 级挂载**（App.vue）：任意页面头像可开；菜单 = 你的资料（/m/me）/ 消息（/m/messages）/
  设置与隐私（/m/me）/ 红色退出登录；「我的」入口 = 抽屉（底部 tab 已让位给私信）；
- **全局 toast**（ui store + App.vue 挂载）：页面不再自建 toast；
- M3：真实消息流/好友流/私信设置/会话信息等功能替换演示动作。
