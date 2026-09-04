# Login Page Overrides（登录/入门 · /login）

> **PROJECT:** VocalVerse — 本文件覆盖 MASTER.md 的页面级规则。

## 布局

- 移动优先：全屏浅天蓝渐变底（`--s-bg` → `#E8F2F8`，柔和不闪），下方 voice-first 波形装饰
  （`--s-listening` 色，60% 透明，`will-change`）；桌面端卡片收窄居中 `max-width: 400px`
- 品牌区：圆形 logo 底（primary 实心白字 "VocalVerse"/ 或三线波形 SVG）+ 产品名 h1 24px + 标语 caption
- 表单卡：白色 card 20px 圆角，内边距 28px；字段标签 14px semibold，输入框 52px（≥44pt）圆角 14px，
  边框 `--s-border`，focus 2px primary ring（45.5% 外发光），**autocomplete="username"/"current-password"**
- 登录按钮：全宽 52px primary 胶囊，loading 时 spinner + 禁用，submit 后跳转
- 演示账号行：3 个 pill 芯片（primary-soft 底/深蓝字），点击填充账号（**附带触觉反馈**：120ms 缩放 +
  勾选闪烁），密码统一 `demo123456`；整行 caption 说明
- 错误提示：内联红字 + 图标（aria-live="polite"），卡片顶部 200ms 内出现，不打断输入焦点

## 交互

- 输入框 focus 状态明显（非仅颜色）；回车提交；粘贴允许；密码管理器兼容
- 按钮 60ms 按压变形；加载 >300ms 出 spinner；成功登录后主 CTA 变绿勾 200ms 再跳转（丝滑反馈）
- reduced-motion：波形静态化，跳转直接完成

## 后续（入门流程，样板阶段不实现）

首次登录引导：连续打卡说明 → 语音授权引导 → 入学测试入口（对应现有 `/placement` 路由）。
