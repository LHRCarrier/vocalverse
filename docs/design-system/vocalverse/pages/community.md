# Community Page Overrides（社区主页 · /m/home · 2026-09-05 组长拍板版）

> **PROJECT:** VocalVerse — 本文件覆盖 MASTER.md 的页面级规则（页面级优先，docs/31 §5 收尾统一迁移 token 时并线）。
> **设计意图（组长拍板 2026-09-05）**：英语社区主页 = X 式结构复刻（顶栏 + 领域文字标签 + 混合信息流 + 互动行），
> 用 uic 纸面语言（`u-*` 类，`mobile-uic.css`）；**结构参考 = docs/34 §4/§5（Fwitter 组件粒度与交互），
> 只借结构/交互，不搬 Fwitter/X 视觉**（docs/34 §6 反借鉴清单）。
> **本页状态（2026-09-05）**：演示帧（8 条演示数据；点赞本地交互；分享/评论/投币展示；领域 Tab 过滤）。

## 页面结构（已拍板，本次不改变）

1. X 式顶栏：左头像 / 中「社区」Logo / 右加好友（演示 toast）——随滚动移出屏幕，非 sticky；
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

## 交互边界（组长明示，不可越界）

- 分享/评论/投币**仍为展示**（不追加交互）；
- 点赞**本地交互不落库**（演示帧）；M3 接真实流（docs/10 注记：sessions/attempts JOIN 派生 + post_likes）时
  **只换数据源，组件层不返工**（docs/34 §7）；
- 分页游标/下拉刷新/新帖提示条 = **M3 与真实流一起落**（docs/34 §5-1），pinia store 届时新增，本页不改。

## 后续（M3）

- 分页/刷新/新帖提示 → `useCommunityFeed`（pinia）；
- 评论楼（嵌套 + 引用帖灰卡）、帖子操作 bottom sheet（docs/34 §5 P1）；
- 社区页 token 随 docs/31 §5 收尾统一迁移（`u-*` → `s-*`），本页视觉基线以现有 uic 纸面语言为准。
