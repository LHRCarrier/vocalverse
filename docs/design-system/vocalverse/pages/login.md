# Login Page Overrides（登录 · /login · v3.1 极简设计语言版）

> **PROJECT:** VocalVerse — 本文件覆盖 MASTER.md 的页面级规则。
> **设计意图（组长 v2→v3 反馈定稿）**：登录页要极简、少文字、有设计感、有记忆点——焦点必须是**设计语言**
> （图形/尺寸/位置传达），不是文字；团队联调入口收为一键演示登录单行。无卡片、无装饰动画。

## 布局（移动优先；桌面居中）

- 全屏浅蓝静态渐变（radial×2 + linear，无动画无波形装饰动画）；
- **品牌焦点（唯一高饱和元素）**：**Phosphor 声波 duotone 160px**（`~icons/ph/wave-sine-duotone`，
  品牌蓝 `#0EA5E9` + drop-shadow 柔光）——"Voice-First"记忆点，替代文字品牌区；
- 字标 `VocalVerse` **24px / 800 / 行高 1.2 / letter-spacing -0.03em**（拉丁收紧规则）→ 一行副标题
  「说得好，唱得准」14px 中灰（全屏文字只有：2 占位词 + 1 按钮词 + 1 行副题 + 1 行演示入口 ≈ <15 词）;
- **表单组**（宽 min(100%,340px)，无卡片无字段标签）：药丸输入 ×2（54px / 圆角 18 / 白 94% 底 /
  占位居中 16px / focus 蓝描边 + 4px 光圈）16px 内距 → **登录按钮**（52px 蓝实心胶囊）32px 距;
- 单行「演示账号登录」（13px 中灰 / 44px 触控高 / 点击 = 填充 demoadult + 自动提交）;
- 错误：内联红字 + 图标（aria-live），不打断输入。

## 无障碍

- input：placeholder + aria-label + autocomplete="username"/"current-password"；允许粘贴；回车提交；
- 按钮三态（loading spinner / 成功绿勾 200ms / 禁用降透明）；focus-visible 蓝描边；
- 字标 24px 拉丁（-0.03em）为唯一 display 使用（32 档本轮保留给后续引导页 hero）。

## 后续（入门流程，样板阶段不实现）

首次登录引导：连续打卡说明 → 语音授权引导 → 入学测试入口（对应现有 `/placement` 路由）。
