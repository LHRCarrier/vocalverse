# Login Page Overrides（登录 · /login · v5.2 复刻定稿版）

> **PROJECT:** VocalVerse — 本文件覆盖 MASTER.md 的页面级规则。
> **设计意图（组长最终拍板）**：登录页 = **uiverse @JohnnyCSilva/bad-cheetah-74 精准复刻**（MIT，保留版权声明；
> `local/uiverse/bad-cheetah-74.*` 存原版代码）。结构/样式/图标/配色 1:1 照搬，仅产品接线不同。

## 复刻规格（改值 = 偏离原版，禁止）

- 背景 `#f0f0f0`；白卡 `.form`（padding 30 · 圆角 20 · 宽 min(450px,100%) · 系统字体栈
  `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif`）
- 字段行 `.inputForm`：**1.5px #ECEDEC 边 · 圆角 10 · 高 50 · 左 padding 10**；focus-within → **1.5px #2D79F3**（0.2s）
- 图标：用户名 = **用户图标（Tabler user，20px，#151717）**；密码 = 原版锁图标（512 viewBox 原样）；
  标签：原版无字段 label（图标+占位已传达信息）
- 占位/文案（**全部英文**）："Enter your Username" / "Enter your Password" · "Remember me"（radio 原版）·
  "Forgot password?"（蓝 #2D79F3 500）· "Sign In"（**炭黑 #151717** · 高 50 · 圆角 10 · margin 20/10）·
  "Don't have an account? Sign Up" · "Or With" · Google/Apple 原版图标 + `.btn`（白底 1px #EDEDEF，hover 蓝边）
- 输入框 `.input`：flex:1 边框无 · `appearance:none` · focus 无 outline（框线由 `.inputForm:focus-within` 表达）

## 产品接线（视觉零影响）

- Sign In → 真实登录（aauth store；成功 200ms 绿勾后跳转 `/m/home`）
- **Sign Up → 一键演示账号**（demoadult/demo123456 自动填充并登录 —— 团队联调入口）
- Forgot password? / Google / Apple → 英文占位提示（2.4s 自动消失）

## 无障碍

- 输入 aria-label（Username/Password）+ autocomplete（username / current-password）；label 关联 id（vv-email/vv-password）；
- 错误 `.error-line` 内联红字 role=alert aria-live；Sign In disabled 态降透明。

## 后续（入门流程，样板阶段不实现）

首次登录引导：连续打卡说明 → 语音授权引导 → 入学测试入口（对应现有 `/placement` 路由）。
