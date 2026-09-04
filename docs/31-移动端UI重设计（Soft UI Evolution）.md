# docs/31 · 移动端 App UI 重设计（Soft UI Evolution + Voice-First）

> 状态：样板阶段（首页 + 登录已按本文件落地；其余页面按序重制）
> 依据：文档 `docs/13`（前端设计系统总纲）的 app 端落地方案；设计智能出自 ui-ux-pro-max skill
> （`search.py --design-system` 推理 + 项目拍板修正），机器副本见 `docs/design-system/vocalverse/`。
> **本文件是 app 端设计的唯一真相源**；页面级规则以 `docs/design-system/vocalverse/pages/*.md` 为准。
> **v3.1 修订（对抗评审 + B 站视频稿参考 + 组长注释图定稿）**：单字体 Plus Jakarta Sans（不再双族）；
> 字级 6 档 12/14/16/20/24/32（每屏 ≤4）；间距 4 档 8/16/24/32；负字距/紧行高仅限拉丁大字（中文 0 字距/1.25）；
> 深蓝渐变焦点卡（#1D4ED8→#172554）+ 白色 CTA；灰轨 + 白浮起 pill 选中（材质派）+ 加粗双信号；
> 列表图标块中性化；统计数字封顶 24；白卡 1px 描边；图标 Tabler（ph 服务深色卡/大图形），接入见 docs/32。

---

## 1. 决策背景

- 现状：app 端 UI（`/m/*` 五页）为 v2「纸面米白 + 炭黑 + 手绘线稿」框架，观感停留在原型阶段；
- 目标：面向大众英语学习者的正式产品观感——**亲切、可信、有温度**，同时把"语音练习"这一产品本质视觉化；
- 排除方向（用户明确）：夜店深色风（Dark OLED）、程序员极简风（Minimalism & Swiss / Inter）；
- 拍板方向：**Soft UI Evolution（柔和进化）+ Voice-First Multimodal 元素层 + Micro-interactions 动效层**。

## 2. 四条硬规则（用户要求，落地为规则）

| # | 要求 | 落地规则 |
|---|---|---|
| 1 | UI 设计本身就在传递信息 | 语义色 = 信息（蓝=行动/进行中、黄=激励/打卡、绿=成绩/成功、红=错误）；颜色绝不单通道传信息（数值/图形/文字双通道）；每屏 ≤3 种语义色；每屏 ≤1 个主行动按钮；数字排版有层级（stat 32px / metric 22px）、tabular-nums |
| 2 | 字体排版有呼吸感 | 8px 间距节奏；行高 ≥1.6；段落 measure ≤34ch；正文 16px、弱化 ≤14px（不用 12px 以下的"内容级"文字）；同屏字级 ≤4 档；区块间距 28-32px；卡片内边距 20-24px |
| 3 | 每次交互都有反馈 | 三态（default/press/disabled）齐全；press 60ms `scale(0.97)`；加载 >300ms 出 spinner；成功 200ms float-in 反馈；错误 aria-live 内联提示；可点元素全部 cursor:pointer |
| 4 | app 端丝滑 | 只动 transform/opacity/box-shadow（无 layout thrash）；时长分层（60/120-150/200-240/spring ≤400ms）；波形层 will-change；`prefers-reduced-motion` 全降级；触控 ≥48dp、相邻 ≥8dp；safe-area 底部留白 |

## 3. 设计 Token（CSS 变量，`apps/web/src/styles/mobile-soft.css`）

完整 token 表见 `docs/design-system/vocalverse/MASTER.md` §色彩/圆角阴影/字体；要点：

- `--s-primary #0EA5E9`（学习蓝，唯一行动色）· `--s-accent #FBBF24`（微笑黄，配深墨文字）· `--s-success #22C55E`（成绩/成功）
- 背景 `--s-bg #F0F9FF` · 卡片白 · 主墨 `--s-text #0C4A6E`（白底 ≥7:1）· 边框 `--s-border #DCEFFB`
- 圆角 card 20 / inner 14 / chip 10 / pill 999；阴影仅两档（card 软双层 / float 浮动）
- 字体 Display **Varela Round** + Body **Nunito Sans**（Google Fonts 可选加载，断网回退系统栈；中文回退 PingFang/雅黑）

## 4. 组件规范（v1 样板已实现）

| 组件 | 规范要点 |
|---|---|
| 手机容器 `.s-phone` | max-width 480px 居中；min-height 100dvh；无外框模型 |
| 页面 `.s-page` | 底部留白 140px + env(safe-area-inset-bottom) |
| 主按钮 `.s-btn--primary` | 52px 胶囊 primary 实心；press 60ms scale(0.97)+阴影收缩；disabled 降透明 |
| 次按钮/芯片 `.s-chip` | primary-soft 底深蓝字；点击 120ms 缩放反馈 |
| Tab 栏 `.s-tabbar` | 悬浮白胶囊（float 阴影）；4 项 + 中央主按钮（spring 弹起）；激活项图标+文字变 primary，内容淡入 150ms |
| 分段控件 `.s-segment` | 56px 白胶囊轨道，选中滑块 translateX 150ms 过渡（不重排）；aria tablist |
| 任务卡 `.s-plan` | primary-soft 底（今日行动焦点）；完成步骤勾+删除线；主 CTA spring |
| 统计卡 `.s-stats` | 3 列 metric 22px；成绩绿/激励黄按语义着色 |
| 列表行 `.s-row` | ≥72px 高；图标块 44px 圆角 14；press 60ms + 底色切换 |
| 徽章 `.s-badge` | success/star/neutral 三变体；只表状态不重复数值 |

## 5. 页面落地顺序

1. **样板（已完成）**：`MobileTabBar` → `MobileHomeView`（今日首页）→ `LoginView`（登录，v2 极简版：无卡片/无演示文案堆砌/一键演示登录，见 pages/login.md）
2. 验收后铺开：`MobileSpeakingView`（口语）→ `MobileSingView`（唱吧）→ `MobileReportView`（报告）→ `MobileMeView`（我的）
3. 收尾：删除旧样式 `mobile-uic.css`（及未再引用的 MobileArt/MobileIcon 组件按需保留），旧 u-* 类全部下线；
   全局 `tokens.ts` / `theme.ts` / `uno.config.ts` 按新 token 收敛（Web 端视觉联动，另行评估）

## 6. 验收清单（样板）

- 375px 视口无横向滚动；触控目标 ≥48dp；文本缩放 200% 不裁切
- reduced-motion 下所有状态可读/语义完整
- 登录表单 autocomplete 生效、可粘贴、回车提交；demo 芯片点击有填充+反馈
- 首页数据区标注「M3 演示帧」；CTA 真实跳转 `/m/chat`
- 门禁：`pnpm lint && pnpm typecheck && pnpm test:run && pnpm build` 全绿

## 7. 反模式清单（评审用）

Emoji 图标 · 大面积毛玻璃/渐变闪烁 · 默认深色 · >3 种语义色同屏 · 仪表盘堆数据 · 无反馈按钮 · 颜色单通道状态
