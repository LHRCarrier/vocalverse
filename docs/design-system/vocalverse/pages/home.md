# Home Page Overrides（今日首页 · /m/home）

> **PROJECT:** VocalVerse — 本文件覆盖 MASTER.md 的页面级规则。
> **Info Architecture（UI 即信息）：** 问候（身份）→ 打卡（激励）→ 今日任务（行动）→ 数据（成绩）→ 记录（轨迹）。
> 每屏 ≤1 个主行动按钮（「开始今日练习」）；其余全是"可看不可抢"。

## 布局

- 页面底 `--s-bg`，无大块渐变；卡片白底 + `--s-shadow-card`
- 顶部问候区：标题 display 28px；副文案 caption 13px；头像 44px 圆形（primary-soft 底 + 深蓝首字母）
- 打卡徽章：黄 accent pill（深墨文字）——唯一黄色元素，专表"激励"
- 今日任务卡（主区）：**primary 浅蓝底 `--s-primary-soft`** 区别于白卡（视觉焦点=今天的行动）；
  标题 h2 20px；步骤行用勾选 + 删除线表达完成度（双通道：图标+文字）；主 CTA primary 实心胶囊，spring 按压
- 统计卡（metric 22px 数字 + caption 标签）：3 列，数字 tabular-nums；平均分用 success 绿（成绩=绿），
  连续天数用黄色 star（激励=黄）——颜色即语义，不靠装饰
- 分段控件：全宽 56px，白底胶囊轨道，选中项 primary 底白字；**滑块用 translateX 过渡（150ms）不重排**
- 最近练习列表：行高 ≥72px（44pt 触控 + 8dp 间距）；图标块 44px 圆角 14（每行一种语义底色，
  但不超 3 种颜色循环）；右侧分值 17px semibold + 状态徽章（success/star/neutral 三变体）
- 底部留白 140px + safe-area（Tab 栏高度）

## 交互

- 分段切换 150ms 滑块微动；列表行按压 60ms scale(0.98) + 底色变 `--s-bg-2`
- 「开始今日练习」→ `/m/chat`（真会话）；会话卡点击跳转；所有可点元素 cursor:pointer
- 空状态：primary-soft 圆形图标底 + 文案（不画大插画）

## 数据口径

统计/打卡/最近练习为 M3 演示帧数据（页面内注明）；问候名、CTA 跳转为真实数据链路。
