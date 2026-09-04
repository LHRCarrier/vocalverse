# ui-lib-reference · 图标库/UI 库选型参考素材

> 用途：VocalVerse app 端设计系统（docs/31）的**图标/组件基座选型**参考素材库。
> 调研报告：`docs/32-图标库与UI库调研与选型.md`（完整对照表与结论）。
> 资源性质：**参考 + 素材**（许可合规样本）；实际接入按 docs/32 结论走 `unplugin-icons` 编译期内联（无需拷贝本目录 SVG 进源代码）。

## 目录

```
├── iconify-tabler.json   # @iconify-json/tabler 1.2.38（完整数据集，接入依赖）
├── iconify-ph.json       # @iconify-json/ph 1.2.2（Phosphor 在 Iconify 的正确包名！）
├── iconify-lucide.json   # @iconify-json/lucide（数据集）
├── MANIFEST.json         # 48 个样本：文件/所属库/许可/来源（逐项可追溯）
├── licenses/             # 各库许可原文（随包分发时须附）
└── svg/
    ├── tabler/           # 主选：25 个语义样本（line + filled 双形态）
    ├── ph/               # 备选（深色卡/大图形）：12 个 fill/duotone 样本
    └── lucide/           # 对比（极简基准）：11 个 line 样本（home 在 lucide 名为 house）
```

## 选型结论（速览）

| 用途 | 库 | 许可 | 接入 |
|---|---|---|---|
| 全 app 图标基调 | **Tabler Icons** | MIT | `unplugin-icons` + `@iconify-json/tabler` |
| 深色卡/大图形/实心强调 | **Phosphor**（fill/duotone） | MIT | `unplugin-icons` + `@iconify-json/ph`（⚠️ 不是 @iconify-json/phosphor，那个包不存在） |
| 对比/未来替换基准 | Lucide | **ISC**（不是 MIT） | `unplugin-icons` + `@iconify-json/lucide` |
| 组件基座 | reka-ui + cva + 自研 s- token | MIT | 见 docs/32 §2 |
| 动效 | VueUse + Motion for Vue（增强） | MIT | 排除 GSAP |

## 许可合规（分发/打包前核对）

1. `licenses/` 内文本随包附上（Tabler MIT · Phosphor MIT · Lucide **ISC** · unplugin-icons MIT）；
2. Iconify 是聚合平台：**必须逐集核验** `@iconify-json/*` 的 license 字段，本目录三份数据集已各自对应；
3. 生产环境只用 MIT/ISC 明文且可自由再分发的库（Tabler/Phosphor/Lucide）；回避付费（Streamline）、
   Apple 专有（SF Symbols）、附加条款（Untitled UI / Hugeicons 免署名与不可再分发）、
   自定义许可（`@remixicon/vue` 为 Remix Icon License 1.0）；
4. 商标类图标（GitHub/Google 等）仅作功能示意，不作产品品牌元素。

## 样本核查（视觉自检）

开 `svg/tabler/`：line 图标统一 2px 圆头圆角描边（`stroke-width=2, stroke-linecap/linejoin=round`）；
`star-filled`/`trophy-filled` 等 filled 变体同库同风格——正是「线为主、个别场合实心」的切换方式。
`svg/ph/` 的 `wave-sine-duotone`（双色氛围）可直接用在深蓝渐变焦点卡/登录页大图形。
