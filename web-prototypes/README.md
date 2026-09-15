# web-prototypes · VocalVerse Web 静态原型合集

> **静态归档目录，不是产品代码。** 这里存放 VocalVerse Web 端的原型页面（早于/并行于 `apps/web` 的设计稿），
> 供评审、对照、答辩取材用；**不参与任何门禁**——没有根级 lint/typecheck/test/build 覆盖本目录，
> CI 中只有 `secret-scan`（全仓 trufflehog）会扫到它。
>
> 产品实现以 `apps/web` 为准；本目录只做视觉与交互对照，**不保证与产品代码逐像素一致**，改动也不要求同步回产品。

---

## 一、页面清单（根目录 9 个整站页面）

| 文件 | 页面 | 说明 |
|---|---|---|
| `index.html` | 首页 Landing | 全屏视频 Hero + 品牌导航 + 大标题 + 「今日练习」输入卡；单页内联样式，仅外链 `css/footer.css` |
| `about.html` | About | 手绘线稿插画 + 品牌叙事 + 联系按钮（`js/contact.js` 悬停展开/点击复制邮箱） |
| `community.html` | Community | 社区主页原型（帖子流 + 滚动展开区 `css/scroll-expand.css`） |
| `practice.html` | AI Oral Practice | 口语陪练页（LLM 场景角色扮演 + 语音识别卖点） |
| `recommend.html` | Personalized Learning | 个性化学习路径/推荐内容页 |
| `report.html` | Learning Report | 学习报告页（`css/report.css` + `js/report-interactions.js`，借鉴参考图的信息结构） |
| `sing.html` | English Song Singing | 英文歌跟唱页 |
| `stats.html` | Visual Reports | 数据可视化报告页 |
| `showcase.html` | Design Showcase | 设计展示页（组件/动效陈列） |

> 除 `index.html` 外的页面共用一套壳：`css/styles.css`（Tailwind v4 编译产物）+ `css/site-nav.css` /
> `css/nav-reveal.css` / `css/gooey-nav.css`（胶囊导航，含 GooeyNav 气泡动效）+ `css/footer.css`，
> 由 `common.js` 在非首页注入全屏视频背景、`js/footer.js` 注入统一页脚。

## 二、子目录

```
web-prototypes/
├── *.html                   # 上表 9 个整站页面
├── styles.css               # index 等页共用的编译后样式（含 Tailwind 产物 + 手写覆盖）
├── common.js / nav.js       # 页面壳：背景视频、移动端菜单、滚动状态
├── reveal.js                # 滚动入场（IntersectionObserver）
├── css/                     # 分页样式：styles / report / gooey-nav / nav-reveal / site-nav /
│                            #           scroll-expand / experience / aero-shards / footer / tailwind.input
├── js/                      # 交互脚本：gooey-nav / scroll-expand / shader-flow / split-text /
│                            #           portrait-morph / stack / report-interactions / showcase-interactions …
├── js/vendor/               # 第三方库（版本与许可见第四节）
└── assets/
    ├── app-screens/         # App 移动端三屏静态稿（home / speaking / report，iPhone 框单文件页面）
    ├── feature-screens/     # 组件六屏展示（输入 / 按钮 / 控件 / 图片卡 / 灯箱 / 弹窗）+ gen.js 生成脚本
    ├── app-screens-iphone.png / feature-*.png   # 上面两组合集的截图
    ├── josh.webp / josh_wave.webp               # 人像素材
    └── linkedin.svg / x.svg                     # 页脚社交图标
```

## 三、本地预览

在**本目录**（`web-prototypes/`，不是仓库根）起一个静态服务即可，页面之间用相对路径互链：

```powershell
cd web-prototypes
python -m http.server 8080     # 或： npx --yes serve .
# 浏览器打开 http://127.0.0.1:8080/index.html
```

直接双击 `file://` 打开多数页面也能看，但剪贴板等安全上下文 API 会降级（`js/contact.js` 已做兜底）。

**外部依赖（需联网，离线时页面仍可打开但会掉素材）**：

| 依赖 | 用在哪 | 备注 |
|---|---|---|
| Google Fonts（Poppins / Geist / Fraunces） | 全部页面 `font-family` | 断网回退系统字体 |
| 两条 CloudFront `.mp4` | `index.html` Hero 背景、`common.js` 非首页背景视频 | **第三方账号托管的演示素材**，随时可能失效；失效只影响背景，不影响页面结构 |
| Unsplash 图 / `images.higgs.ai` webp | 视频封面、滚动展开区配图 | 同上，演示用外链 |
| `cdn.simpleicons.org` | about/showcase 的品牌 logo 墙 | 断网则图标缺失 |

## 四、第三方代码与许可

库文件都原样保留上游版权头；`js/vendor/vgpu.LICENSE` 为 vgpu 许可原文。

| 文件 / 来源 | 版本 | 许可 | 上游 |
|---|---|---|---|
| `js/vendor/gsap.min.js` | 3.13.0 | **GSAP Standard License**（非 MIT） | gsap.com |
| `js/vendor/ScrollTrigger.min.js` | 3.13.0 | 同上 | gsap.com |
| `js/vendor/SplitText.min.js` | 3.13.0 | 同上（原 Club 插件，现纳入标准许可） | gsap.com |
| `js/vendor/lenis.min.js` | 1.3.26 | MIT | darkroom.engineering/lenis |
| `js/vendor/matter.min.js` | 0.20.0 | MIT | brm.io/matter-js |
| `js/vendor/vgpu.js`（`@vgpu/core` 构建产物） | — | MIT（Vercel, Inc.） | vercel-labs/vgpu |
| `styles.css` / `css/tailwind.input.css` | Tailwind v4.3.3 | MIT | tailwindcss.com |
| `js/gooey-nav.js` + `css/gooey-nav.css` | — | 移植改造自 React Bits 的 GooeyNav（React→原生 JS） | reactbits.dev（文件头逐条列了与上游的差异） |

`css/report.css` 标注的「Learning Report / FLUENCY FEATURES 参考图」仅作**信息结构与版式对照**，
不包含第三方代码或素材文件。

## 五、维护约定

- 本目录是**归档快照**：新增/删除页面无需改任何 workflow、无需过 `apps/web` 门禁；
- 产品内可交互的概念预览页在 `apps/web/src/views/preview/`（UIC 概念三页 `uic-*`，dev-only 子树），
  与本目录各自演进，互不同步；
- 页面文案为原型英文稿，非最终产品文案；
- 归档前请确认不含密钥/真实用户数据（红线见仓库根 `README.md` 与 `AGENTS.md`）。
