# VocalVerse 设计系统 MASTER（app 端 · Soft UI Evolution + Voice-First）

> 生成工具：ui-ux-pro-max skill（`--design-system` 推理）输出已按项目拍板修正。
> 唯一真相源：`docs/31-移动端UI重设计（Soft UI Evolution）.md`（人类可读），本文件为分层检索用机器副本。
> 页面覆盖：`pages/home.md`（今日首页）、`pages/login.md`（登录/入门）。构建页面时先读本文件，再读对应 page 文件（存在则其规则覆盖本文件）。

## 定位

大众英语学习产品（全年龄学习者在用：adult / teen / senior demo）的 AI 发音教练 app。
**不是程序员工具、不是夜店风、不是少儿玩具**——亲切、可信、有温度；视觉本身要传递信息。

## 设计风格

- **主体**：Soft UI Evolution——柔和双投影（柔而不糊）、大圆角、轻盈层次、克制用色
- **元素层**：Voice-First Multimodal——语音波形可视化、聆听脉冲（listening pulse）、说话动画
- **动效层**：Micro-interactions——50-100ms 按压反馈、成功/错误即时反馈、spring 主交互

## 色彩 Token（浅色模式；深色后续版本另行验证）

| Role | Hex | 语义（UI 即信息） |
|---|---|---|
| `--s-primary` | `#0EA5E9` | 学习蓝：可点/进行中/专注状态（唯一"行动"色） |
| `--s-primary-deep` | `#0284C7` | 按压态/文字级蓝（AA 对比度） |
| `--s-primary-soft` | `#E0F2FE` | 浅蓝底：选中态/图标底/标签底 |
| `--s-secondary` | `#38BDF8` | hover/渐变辅色 |
| `--s-accent` | `#FBBF24` | 微笑黄：打卡/激励/奖励（一律配深墨文字 `#0C4A6E`） |
| `--s-success` | `#22C55E` | 成绩/完成/成功 |
| `--s-success-deep` | `#15803D` | 文字级绿（AA） |
| `--s-warning` | `#F59E0B` | 待提升/提示 |
| `--s-error` | `#EF4444` | 错误/危险（`--s-error-deep #DC2626` 文字级） |
| `--s-score` | `#FB923C` | 评分轨迹/图表强调 |
| `--s-listening` | `#6B8FAF` | 语音元素层：聆听态（波形/脉冲） |
| `--s-speaking` | `#22C55E` | 语音元素层：说话态 |
| `--s-voice-accent` | `#9B8FBB` | 语音元素层：柔和点缀紫（图形专用） |
| `--s-bg` | `#F0F9FF` | 页面底（浅天蓝调） |
| `--s-bg-2` | `#E8F2F8` | 分区底/轨道 |
| `--s-card` | `#FFFFFF` | 卡片 |
| `--s-text` | `#0C4A6E` | 主墨（深藏蓝，白底 ≥7:1） |
| `--s-text-2` | `#475569` | 次级文字 |
| `--s-text-3` | `#94A3B8` | 弱化文字（仅非关键） |
| `--s-border` | `#DCEFFB` | 分隔/描边（浅蓝灰） |

## 圆角 / 阴影 / 间距

- 圆角：card `20px` · inner `14px` · chip `10px` · pill `999px`（宁大勿小）
- 阴影（仅两档）：`--s-shadow-card: 0 2px 10px rgba(12,74,110,.06), 0 8px 28px rgba(12,74,110,.08)`
  `--s-shadow-float: 0 12px 32px rgba(12,74,110,.14)`（Tab 栏/浮层）
- 间距：4/8/12/16/20/24/32/40（8px 节奏）；区块间距 28-32px；卡片内边距 20-24px

## 字体（呼吸感）

- Display：**Varela Round**（标题/数字，圆润友善）· Body：**Nunito Sans**（正文高可读）
- 中文回退：PingFang SC / Microsoft YaHei；无外网时回退系统栈（不阻塞，演示机可离线）
- 字级表：display 28/1.2 · h1 24/1.3 · h2 20/1.35 · h3 17 · body 16/1.6 · caption 13/1.5 ·
  stat 32/1.1（数字带 tabular-nums）· metric 22（统计卡）
- 行高 ≥1.6；段落 measure ≤34ch；标题与正文间距 ≥8px；同屏字级 ≤4 档

## 交互反馈（硬规则：每次交互必有反馈）

1. 三态齐全：default / press（60ms 内 `scale(0.97)` + 阴影收缩）/ disabled（降透明 + 语义禁用）
2. 时长分层：press 60ms · micro 120-150ms · standard 200-240ms `cubic-bezier(0.22,1,0.36,1)` ·
   主 CTA spring `cubic-bezier(0.34,1.56,0.64,1)` ≤400ms
3. 反馈类型：按压变形/按钮状态切换/加载 spinner（>300ms 必出）/成功出现（200ms 内 绿勾+缩放 float in）/
   错误 inline 提示（aria-live）
4. 只动 transform / opacity / box-shadow（丝滑：无 layout thrash，保持 60fps）；波形层 `will-change: transform`
5. `prefers-reduced-motion: reduce` → 动效全部降级（瞬时完成，保留状态语义）

## 触控与布局（app 端）

- 触控目标 ≥48dp（Android WebView 按 48dp）+ 相邻目标间距 ≥8dp
- Tab 栏 ≤5 项（4 项 + 中央主按钮）；`padding-bottom: env(safe-area-inset-bottom)`
- 内容滚动区避开固定 Tab 栏（底部留白 ≥120px + safe area）
- 开发验证：375px 断点 · 横屏不塌 · 文本缩放 200% 不裁切

## 反模式（Avoid）

Emoji 当图标（用统一 SVG 家族）· 大面积毛玻璃/纯色渐变闪烁 · 默认深色 · 同屏 >3 种语义色混用
· 仪表面板式堆数据 · 无按压反馈的按钮 · 进度信息只用颜色（必须用数值/图形双通道）

## 交付前检查（voice-first 语音页必过）

- [ ] 对比度：正文 ≥4.5:1（白底对 `--s-text-2` 同样达标）
- [ ] 触控 ≥48dp；点按 60ms 内有视觉反馈
- [ ] reduced-motion 下状态仍可读（不丢失语义）
- [ ] 波形/脉冲动画不干扰文字阅读；聆听/说话/处理三态有文字或颜色双通道提示
- [ ] 表单：autocomplete 兼容（username / current-password）、允许粘贴
