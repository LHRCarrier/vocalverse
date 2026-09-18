/* ===== Showcase 页交互增强 =====
 * 只服务 showcase.html，沿用站点既有的动效语言与交互约定：
 *  - 与 js/report-interactions.js 同为「页面级交互」脚本，单文件自洽；
 *  - 手机框渲染与 js/footer.js 同思路：数据 → 模板 → 注入，避免 9 份 SVG 手抄；
 *  - 滚动进度用时间戳节流，不引入第三方库；
 *  - 图片放大浮层复用站点浮层套路：浅色遮罩 + 白卡 r-24 + 幽灵按钮；
 *  - 锚点跳转交给 js/main.js 里已接好的 Lenis 平滑滚动，这里不重复接管；
 *  - 全量尊重 prefers-reduced-motion：减弱动效时不做位移/缩放/倾斜。
 * ============================================================ */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var root = document.documentElement;

  /* ============================================================
     零、手机框渲染
     机身几何与 React 版 Iphone 组件完全一致：
       PHONE 433×882 / SCREEN 21.25,19.25 + 389.5×843.5 / r 55.75
     屏幕内容两种模式：
       · img —— 真实运行中的 app（Vue 前端）在 390×844 @2x 下的截图，当前默认
       · src —— 活页面 iframe（保留：本地单文件页面仍可直接装进来）
     说明文字走站点令牌渲染，因此深浅主题都会跟着变 —— 这是换成活框的主要收益。
     ============================================================ */
  var PHONE_W = 433, PHONE_H = 882;
  var SCREEN_X = 21.25, SCREEN_Y = 19.25;
  /* 屏幕区尺寸与圆角：路径里已按数值写死，这里留作几何参照（与 CSS 的 .uc-phone__screen 对应）*/
  var SCREEN_W = 389.5, SCREEN_H = 843.5, SCREEN_R = 55.75;

  /* 屏幕内容：VocalVerse 移动端真实界面（截图来自运行中的 app，390×844 @2x）。
     早期这里是设计系统自带的通用样例（app-screens/*.html、feature-screens/s*.html），
     展示的是别处的 demo，与产品无关 —— 现按真实界面重排成 3 组 × 3 台：
       uc-1 学习与评分   uc-2 社区与投稿   uc-3 消息与笔记
     （Web 端截图 assets/app-shots/web-*.png 仍在目录里，但页面不再展示。） */
  var PHONE_GROUPS = {
    /* 0 号：操作演示 —— 真实跑一遍的录屏，放在手机框里静音循环播放，
       作为「先看它怎么跑起来」的开场。录屏由 CDP screencast 抓帧、
       ffmpeg 按帧时间戳合成（可变帧率），素材与截图同为 390×844 @2x。 */
    "uc-0": [
      { video: "assets/app-shots/app-demo.mp4", title: "操作演示 · 浏览与导航",
        desc: "从社区首页出发：切频道 → 打开一条帖子 → 发帖 → 通知 → 学习中心 → 唱吧，最后完整走一遍跟唱（听参考旋律 → 开始跟唱 → 停止并评分）。录制自运行中的 app（Vite dev，演示账号 demoadult），47 秒，静音循环播放。" }
    ],
    "uc-1": [
      { img: "assets/app-shots/learn-center.png", title: "学习中心",
        desc: "以问候语和本周小结开场；等级徽章带 70 / 500 XP 进度条，右侧是连续打卡 12 天；近 30 天学习热力图标出当天 +75 XP；下方依次是我的单词、书房、社区足迹、我的发音四个入口，底部五个 Tab 主导航。" },
      { img: "assets/app-shots/report.png", title: "评分报告",
        desc: "一次跟唱的完整复盘：曲目与时间、总分 92.4，拆成发音 93 · 语法 91 · 流利 88 · 覆盖 100%；再往下是逐句评分（95 / 88 / 81），每句配一句点评，底部提供「再唱一遍」。" },
      { img: "assets/app-shots/pronunciation.png", title: "我的发音",
        desc: "发音这条线的纵向汇总：三张卡分别是发音 82 · 流利度 76 · 语法 86，下面用近 7 次练习的柱状图对比三项的走势；再往下是薄弱音素 /θ/ /ð/ /r/——词级错误沉淀自每次练习的发音评测，用来指下一轮该练什么。" }
    ],
    /* 唱吧单独成组：曲库 → 跟唱 → 评分，三张连起来才是这个功能的完整闭环。
       此前只展示了曲库，最关键的"逐句音准/节奏评分"反而没露过面。 */
    "uc-2": [
      { img: "assets/app-shots/sing.png", title: "唱吧 · 曲库",
        desc: "顶部是上一遍的诊断：88.1 分、音准 93、节奏 91，并给出「稳住节奏就能破 90」的建议；下方按全部 / 热门 / 收藏分组的歌曲库，每首带最佳成绩与等级标签（Perfect Night 88.1 新纪录、Yesterday Once More 91.5 优秀）。" },
      { img: "assets/app-shots/sing-ready.png", title: "跟唱 · 准备",
        desc: "从「去跟唱」进入的跟唱页：顶部是曲目与规模（Twinkle Twinkle Little Star · 6 句 · 整首 ≤180s），中间是整首歌词，先「听参考旋律」再「开始跟唱（≤3 分钟）」；下方预留实时音准线区域，可勾选是否显示。移动端提示授权后保持前台、录音 3 分钟自动停止。" },
      { img: "assets/app-shots/sing-score.png", title: "跟唱 · 评分结果",
        desc: "一遍唱完的评分：综合分拆成音准 41.0 · 节奏 57.4 · 发音 90.0；中间是 D3 绘制的音高对齐图（纵轴 G#5–C-1、横轴 0–25s，青线是实际音高走向）；下方逐句列出「起唱偏差 1237ms / 208ms」与得分，未唱到的句子标 no_pitch。有效句不足 40% 时不给总分，并直接建议「降 5 个半音」。" }
    ],
    /* 阅读线此前完全没展示：书房 → 书籍详情 → 阅读器。 */
    "uc-3": [
      { img: "assets/app-shots/bookshelf.png", title: "书房",
        desc: "英文小说书架：Alice's Adventures in Wonderland、Pride and Prejudice、The Wonderful Wizard of Oz、Don Quixote 四本公版书，各带封面与作者，点进去是书籍详情。" },
      { img: "assets/app-shots/book-detail.png", title: "书籍详情",
        desc: "单本书的档案页：封面、书名与作者，难度等级 L1、12 章、27k 词、公版标识，底部「开始阅读」直接进入第一章。" },
      { img: "assets/app-shots/reader.png", title: "阅读器",
        desc: "正文阅读页：章节名 Down the Rabbit-Hole、第 1 章 · 2.2k 词，正文按段落排版；阅读时点击单词即可查义并「加入生词本」，生词之后会出现在我的单词里。" }
    ],
    "uc-4": [
      { img: "assets/app-shots/community.png", title: "社区动态",
        desc: "为你推荐流，按新闻稿 / 教学分享 / 海外生活三频道组织；每张卡片带作者与等级、发布时间、正文摘要，以及点赞 / 评论 / 收藏数——例如 VocalVerse News 的 AI 英语学习长文、Teacher Amy 的职场闲聊三句式。" },
      { img: "assets/app-shots/post-detail.png", title: "帖子详情",
        desc: "从动态流点进去的完整文章页：标题、作者徽章、正文与配图，底部是评论数与评论区入口，用来把一条动态读完整。" },
      { img: "assets/app-shots/compose.png", title: "发帖",
        desc: "发布页：0/280 字数、与动态流一致的三个频道，图片最多 9 张（≤20MB）或视频 1 个（MP4/WebM，≤64MB）且不能同时发，可加话题标签与表情。" }
    ],
    "uc-5": [
      { img: "assets/app-shots/notifications.png", title: "通知中心",
        desc: "私信 / 通知 / 关注三条独立流；每条带对方等级与时间，例如老年高级 LV4 分享阅读笔记、青少年初级 LV1 询问跟读方法；弱网时自动降级，不依赖长连。" },
      { img: "assets/app-shots/messages.png", title: "私信会话",
        desc: "通知里点进去的一对一聊天：对方等级徽章、左右气泡与时间戳，用于把社区里的互动接下去。" },
      { img: "assets/app-shots/notes.png", title: "笔记 · 语言点",
        desc: "学习过程中自动沉淀的生词与短语本，按全部 / 口语 / 阅读 / 文化筛选：pick up、run out of、shadowing、procrastinate……每条保留释义、来源与日期。" }
    ]
  };

  /* 机身 SVG：路径逐条取自 React 版，fill 交给 CSS 变量以便随主题切换。
     机身＝「外壳轮廓 − 屏幕」的一圈：把屏幕那条子路径直接拼进同一条 d，用
     fill-rule="evenodd" 挖出屏幕，不再走 mask。
     改这个是因为原来那份遮罩定义在一个独立的隐藏 SVG 里、被 9 台机共用，
     实测 Chromium 下整组路径根本不渲染 —— 机身、内面、侧键、按键全丢，
     只剩描边、灵动岛和镜头；浅色页面上就只剩一圈线，看着像"元素边框"而不是手机。
     现在没有任何 id 依赖，路径一定画得出来。 */
  function frameSvg() {
    var BODY =
      "M2 73C2 32.6832 34.6832 0 75 0H357C397.317 0 430 32.6832 430 73V809C430 849.317 397.317 882 357 882H75C34.6832 882 2 849.317 2 809V73Z";
    /* 屏幕区：21.25,19.25 起、389.5×843.5、圆角 55.75（与 .uc-phone__screen 同形同位）*/
    var SCREEN =
      "M" + SCREEN_X + " 75C" + SCREEN_X + " 44.2101 46.2101 " + SCREEN_Y + " 77 " + SCREEN_Y +
      "H355C385.79 " + SCREEN_Y + " 410.75 44.2101 410.75 75V807C410.75 837.79 385.79 862.75 355 862.75H77C46.2101 862.75 " +
      SCREEN_X + " 837.79 " + SCREEN_X + " 807V75Z";
    /* 侧键：贴在机身左右外沿（x<2 / x>430），独立路径，不参与挖孔 */
    var BUTTONS = [
      "M0 171C0 170.448 0.447715 170 1 170H3V204H1C0.447715 204 0 203.552 0 203V171Z",
      "M1 234C1 233.448 1.44772 233 2 233H3.5V300H2C1.44772 300 1 299.552 1 299V234Z",
      "M1 319C1 318.448 1.44772 318 2 318H3.5V385H2C1.44772 385 1 384.552 1 384V319Z",
      "M430 279H432C432.552 279 433 279.448 433 280V384C433 384.552 432.552 385 432 385H430V279Z"
    ];
    return (
      '<svg class="uc-phone__frame" viewBox="0 0 ' + PHONE_W + " " + PHONE_H + '" fill="none" aria-hidden="true">' +
      '<path class="f-body" fill-rule="evenodd" d="' + BODY + SCREEN + '"/>' +
      BUTTONS.map(function (p) { return '<path class="f-body" d="' + p + '"/>'; }).join("") +
      /* 听筒缝：顶边一道 50% 的深色细线 */
      '<path opacity="0.5" class="f-island" d="M174 5H258V5.5C258 6.60457 257.105 7.5 256 7.5H176C174.895 7.5 174 6.60457 174 5.5V5Z"/>' +
      /* 灵动岛 + 镜头圈：画在屏幕上方，所以必须排在机身之后 */
      '<path class="f-island" d="M154 48.5C154 38.2827 162.283 30 172.5 30H259.5C269.717 30 278 38.2827 278 48.5C278 58.7173 269.717 67 259.5 67H172.5C162.283 67 154 58.7173 154 48.5Z"/>' +
      '<path class="f-island" d="M249 48.5C249 42.701 253.701 38 259.5 38C265.299 38 270 42.701 270 48.5C270 54.299 265.299 59 259.5 59C253.701 59 249 54.299 249 48.5Z"/>' +
      '<path class="f-lens" d="M254 48.5C254 45.4624 256.462 43 259.5 43C262.538 43 265 45.4624 265 48.5C265 51.5376 262.538 54 259.5 54C256.462 54 254 51.5376 254 48.5Z"/>' +
      "</svg>"
    );
  }

  function phoneHtml(item, i) {
    return (
      '<div class="uc-phone" style="--uc-i:' + i + '">' +
      '<div class="uc-phone__body" data-uc-tilt>' +
      '<div class="uc-phone__tilt">' +
      '<div class="uc-phone__screen">' +
      /* 三种屏幕内容：video = 演示录屏（0 号机）｜img = 真实 app 截图（当前）
         ｜src = 本地活页面 iframe。
         静音 + autoplay + loop，播放无需用户手势；preload=auto 让首帧尽快出来。 */
      (item.video
        ? '<video src="' + item.video + '" autoplay muted loop playsinline preload="auto" aria-label="' + item.title + '"></video>'
        : item.img
          ? '<img src="' + item.img + '" alt="' + item.title + '" draggable="false">'
          : '<iframe src="' + item.src + '" scrolling="no" title="' + item.title + '"></iframe>') +
      '<span class="uc-phone__glare" aria-hidden="true"></span>' +
      "</div>" +
      frameSvg() +
      /* 机身高光边：单独一个元素画，而不是给 SVG 路径加 stroke ——
         外层机身路径的顶边正好落在 viewBox 的 y=0 上，描边会被 SVG 视口裁掉一半，
         上下边就会明显比左右边细。用圆角矩形边框可以均匀贴合且不裁切。 */
      '<span class="uc-phone__edge" aria-hidden="true"></span>' +
      "</div>" +
      "</div>" +
      '<div class="uc-phone__cap">' +
      '<span class="uc-phone__idx">' + (i + 1) + "</span>" +
      "<h4>" + item.title + "</h4>" +
      "<p>" + item.desc + "</p>" +
      "</div>" +
      "</div>"
    );
  }

  (function initPhones() {
    var hosts = document.querySelectorAll("[data-uc-phones]");
    if (!hosts.length) return;

    Array.prototype.forEach.call(hosts, function (host) {
      var group = PHONE_GROUPS[host.getAttribute("data-group")];
      if (!group) return;
      host.innerHTML = group.map(phoneHtml).join("");
    });

    /* —— 屏幕内容等比缩放进机身屏幕区 ——
       素材统一按 390×844 视口准备（截图是 @2x，CSS 尺寸仍按 390×844），
       再整体缩放到屏幕框实际宽度，保证按设计视口排版而不是被挤压变形。 */
    var screens = [];
    Array.prototype.forEach.call(hosts, function (host) {
      Array.prototype.forEach.call(host.querySelectorAll(".uc-phone__screen"), function (s) {
        screens.push(s);
      });
    });

    function fit() {
      screens.forEach(function (s) {
        var el = s.querySelector("iframe, img, video");
        if (!el) return;
        var w = s.clientWidth;
        if (!w) return;
        var scale = w / 390;
        el.style.transform = "scale(" + scale.toFixed(5) + ")";
      });
    }
    fit();
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(fit);
      screens.forEach(function (s) { ro.observe(s); });
    } else {
      window.addEventListener("resize", fit, { passive: true });
    }

    /* —— 入场：整组进入视口时，三台机依次浮起 —— */
    if (reduceMotion) {
      Array.prototype.forEach.call(hosts, function (h) { h.classList.add("is-inview"); });
    } else if ("IntersectionObserver" in window) {
      var io = new IntersectionObserver(
        function (entries) {
          entries.forEach(function (e) {
            if (!e.isIntersecting) return;
            e.target.classList.add("is-inview");
            io.unobserve(e.target);
          });
        },
        { threshold: 0.12, rootMargin: "0px 0px -60px 0px" }
      );
      Array.prototype.forEach.call(hosts, function (h) { io.observe(h); });
    } else {
      Array.prototype.forEach.call(hosts, function (h) { h.classList.add("is-inview"); });
    }

    /* —— 悬停磁性倾斜：指针位置驱动 rotateX / rotateY，幅度克制 —— */
    if (reduceMotion || !window.matchMedia("(hover: hover)").matches) return;

    Array.prototype.forEach.call(document.querySelectorAll("[data-uc-tilt]"), function (body) {
      var MAX = 6; // 最大倾角（度）

      body.addEventListener("pointermove", function (e) {
        var r = body.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        body.style.setProperty("--uc-ry", (px * MAX * 2).toFixed(2) + "deg");
        body.style.setProperty("--uc-rx", (-py * MAX * 2).toFixed(2) + "deg");
      });

      body.addEventListener("pointerleave", function () {
        body.style.setProperty("--uc-ry", "0deg");
        body.style.setProperty("--uc-rx", "0deg");
      });
    });
  })();

  /* ============================================================
     操作演示浮层：右下角按钮 → 手机框从按钮位置长到页面正中
     ------------------------------------------------------------
     展开用 FLIP：先量出按钮矩形与手机框矩形，把手机框用 transform 摆到
     按钮上（缩到按钮大小），强制回流后再过渡回 transform:none —— 于是
     观感是"从按钮里长出来"，而不是淡入。关闭就是同一段反过来跑。
     关闭入口：点手机框外任意处、Esc。点手机框本身不关（便于细看）。
     ============================================================ */
  (function initDemoModal() {
    var fab = document.querySelector("[data-uc-demo-open]");
    var modal = document.querySelector("[data-uc-demo]");
    if (!fab || !modal) return;

    var phoneWrap = modal.querySelector("[data-uc-demo-phone]");
    var toggle = modal.querySelector("[data-uc-video-toggle]");
    var video = modal.querySelector(".uc-phone__screen video");
    var host = modal.querySelector("[data-uc-phones]");
    if (!phoneWrap || !host) return;

    var isOpen = false;
    var busy = false;

    /* 机身自带的入场动画在浮层里已被 CSS 关掉，但 IntersectionObserver 在
       hidden 状态下不会给 is-inview —— 这里直接补上，避免开框时内容还是空的 */
    host.classList.add("is-inview");

    /* —— 滚动锁 ——
       overflow:hidden 之后 Lenis 也写不动 window.scrollY，等于一并锁住；
       顺带补滚动条宽度，免得开框瞬间整页横向抖一下。 */
    function lockScroll(on) {
      if (on) {
        var sbw = window.innerWidth - root.clientWidth;
        root.style.overflow = "hidden";
        document.body.style.paddingRight = sbw > 0 ? sbw + "px" : "";
      } else {
        root.style.overflow = "";
        document.body.style.paddingRight = "";
      }
    }

    /* 让手机框"正好盖在按钮上"所需的 transform */
    function flipVector() {
      var f = fab.getBoundingClientRect();
      var p = phoneWrap.getBoundingClientRect();
      if (!p.width || !p.height || !f.width) return null;
      return {
        dx: (f.left + f.width / 2) - (p.left + p.width / 2),
        dy: (f.top + f.height / 2) - (p.top + p.height / 2),
        scale: f.width / p.width
      };
    }

    function place(v, opacity) {
      phoneWrap.style.transform =
        "translate(" + v.dx.toFixed(2) + "px," + v.dy.toFixed(2) + "px) scale(" + v.scale.toFixed(4) + ")";
      if (opacity !== undefined) phoneWrap.style.opacity = String(opacity);
    }

    function syncToggle() {
      if (!toggle || !video) return;
      var playing = !video.paused && !video.ended;
      toggle.setAttribute("aria-pressed", String(!playing)); // 按下态 = 已暂停
      var label = toggle.querySelector("[data-uc-video-label]");
      if (label) label.textContent = playing ? "Pause" : "Play";
    }

    function openModal() {
      if (isOpen || busy) return;
      isOpen = true;
      busy = true;

      modal.hidden = false;
      // 先让基础态（scrim/底栏 opacity:0）落地，再加 is-open ——
      // 两件事挤在同一帧里的话没有"起始值"可插值，遮罩会直接跳出来而不是淡入
      void modal.offsetWidth;
      modal.classList.add("is-open");
      lockScroll(true);
      fab.classList.add("is-hidden");
      fab.setAttribute("aria-expanded", "true");

      var v = reduceMotion ? null : flipVector();
      if (v) {
        phoneWrap.style.transition = "none";
        place(v, 0.25);
        void phoneWrap.offsetWidth; // 强制回流，让起始态先落地
        phoneWrap.style.transition = "transform .62s cubic-bezier(.22, 1, .36, 1), opacity .45s ease";
        phoneWrap.style.transform = "none";
        phoneWrap.style.opacity = "1";
      } else {
        phoneWrap.style.transition = "none";
        phoneWrap.style.transform = "none";
        phoneWrap.style.opacity = "1";
      }

      if (video) {
        try { video.currentTime = 0; } catch (_) {} // 每次打开都从头发
        var pr = video.play();
        if (pr && pr.catch) pr.catch(function () {}); // 自动播放被拒时静默降级
        syncToggle();
      }

      window.setTimeout(function () {
        busy = false;
        // 焦点交给浮层容器而不是按钮：键盘能接管、Esc 有落点，
        // 又不会在鼠标点开时给某个按钮套上一圈 focus-visible 蓝框
        var stage = modal.querySelector(".uc-demo__stage");
        if (stage) stage.focus();
      }, v ? 660 : 0);
    }

    function closeModal() {
      if (!isOpen || busy) return;
      busy = true;
      fab.setAttribute("aria-expanded", "false");
      // 先摘掉 is-open：scrim 与底栏立刻开始淡出，不必等手机框收完
      modal.classList.remove("is-open");

      var v = reduceMotion ? null : flipVector();

      function finish() {
        modal.hidden = true;
        phoneWrap.style.transition = "none";
        phoneWrap.style.transform = "none";
        phoneWrap.style.opacity = "";
        lockScroll(false);
        if (video) video.pause();
        fab.classList.remove("is-hidden"); // 收到位了才把按钮露出来，接得上
        busy = false;
        isOpen = false;
        fab.focus();
      }

      if (v) {
        phoneWrap.style.transition = "transform .5s cubic-bezier(.4, 0, .2, 1), opacity .45s ease";
        place(v, 0.2);
        window.setTimeout(finish, 540); // 略长于收缩时长，淡出与收缩一起收尾
      } else {
        window.setTimeout(finish, 460);
      }
    }

    fab.addEventListener("click", openModal);

    /* 点框外关闭：手机框与底部操作条之外都算"框外"（含模糊层与浮层留白） */
    modal.addEventListener("click", function (e) {
      if (e.target.closest("[data-uc-demo-phone], .uc-demo__bar")) return;
      closeModal();
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && isOpen) closeModal();
    });

    if (toggle && video) {
      toggle.addEventListener("click", function () {
        if (video.paused) {
          var p = video.play();
          if (p && p.catch) p.catch(function () {});
        } else {
          video.pause();
        }
      });
      video.addEventListener("play", syncToggle);
      video.addEventListener("pause", syncToggle);
      syncToggle();
    }
  })();

  /* ============================================================
     一、左侧区块索引轨：竖向进度条 + 当前区块高亮
     ============================================================ */
  (function initRail() {
    var rail = document.querySelector("[data-uc-rail]");
    if (!rail) return;

    var fill = rail.querySelector("[data-uc-fill]");
    var dots = Array.prototype.slice.call(rail.querySelectorAll("[data-uc-dot]"));
    var sections = dots
      .map(function (d) {
        return document.getElementById(d.getAttribute("data-uc-dot"));
      })
      .filter(Boolean);
    if (!sections.length) return;

    function update() {
      // 竖向进度：整页滚动百分比
      if (fill) {
        var max = root.scrollHeight - window.innerHeight;
        var p = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
        fill.style.transform = "scaleY(" + p.toFixed(4) + ")";
      }

      // 当前区块：以视口上方 35% 处为准，取最后一个越过该线的区块
      var line = window.scrollY + window.innerHeight * 0.35;
      var activeId = sections[0].id;
      sections.forEach(function (s) {
        if (s.offsetTop <= line) activeId = s.id;
      });

      dots.forEach(function (d) {
        d.classList.toggle("is-active", d.getAttribute("data-uc-dot") === activeId);
      });

      rail.classList.toggle("is-visible", window.scrollY > 120);
    }

    /* 时间戳节流：同一帧内不重复计算。
       刻意不用 rAF 来释放锁 —— 标签页转后台或 rAF 被节流时，rAF 可能长时间不回调，
       锁就一直不释放，索引轨会永久卡在旧状态。时间戳方案没有这个失效模式。 */
    var lastRun = 0;
    function onScroll() {
      var now = window.performance && performance.now ? performance.now() : Date.now();
      if (now - lastRun < 16) return;
      lastRun = now;
      update();
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    update();
  })();

  /* ============================================================
     二、整张 PNG 放大浮层（点击「查看整张 PNG」→ 全屏，支持键盘与左右切换）
     ============================================================ */
  (function initLightbox() {
    var triggers = Array.prototype.slice.call(document.querySelectorAll("[data-uc-zoom]"));
    if (!triggers.length) return;

    var items = triggers.map(function (btn) {
      var inner = btn.querySelector("img");
      return {
        src: btn.getAttribute("data-uc-src") || (inner ? inner.getAttribute("src") : ""),
        caption: btn.getAttribute("data-uc-caption") || ""
      };
    });

    var current = -1;
    var lastFocus = null;

    /* —— 浮层 DOM：遮罩 + 白卡舞台 + 关闭 + 左右翻页，一次性建好 —— */
    var box = document.createElement("div");
    box.className = "uc-lightbox";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    box.setAttribute("aria-label", "Enlarged view");
    box.hidden = true;
    box.innerHTML = [
      '<div class="uc-lightbox__scrim" data-uc-dismiss></div>',
      '<figure class="uc-lightbox__stage">',
      '  <img class="uc-lightbox__img" alt="" />',
      '  <figcaption class="uc-lightbox__cap"></figcaption>',
      "</figure>",
      '<button type="button" class="uc-lightbox__close" data-uc-dismiss aria-label="Close enlarged view">',
      '  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
      "</button>",
      '<button type="button" class="uc-lightbox__nav uc-lightbox__nav--prev" data-uc-step="-1" aria-label="Previous sheet">',
      '  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5l-7 7 7 7"/></svg>',
      "</button>",
      '<button type="button" class="uc-lightbox__nav uc-lightbox__nav--next" data-uc-step="1" aria-label="Next sheet">',
      '  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7"/></svg>',
      "</button>"
    ].join("");
    document.body.appendChild(box);

    var imgEl = box.querySelector(".uc-lightbox__img");
    var capEl = box.querySelector(".uc-lightbox__cap");
    var closeBtn = box.querySelector(".uc-lightbox__close");

    function render(i) {
      current = (i + items.length) % items.length;
      imgEl.setAttribute("src", items[current].src);
      imgEl.setAttribute("alt", items[current].caption);
      capEl.textContent = items[current].caption;
    }

    function open(i) {
      lastFocus = document.activeElement;
      render(i);
      box.hidden = false;
      // 先落 hidden=false 再加 class，保证过渡从初始态起跑
      requestAnimationFrame(function () {
        box.classList.add("is-open");
      });
      root.classList.add("uc-locked"); // 锁滚动
      closeBtn.focus();
    }

    function close() {
      if (box.hidden) return;
      box.classList.remove("is-open");
      root.classList.remove("uc-locked");
      var done = function () {
        box.hidden = true;
        imgEl.removeAttribute("src");
        if (lastFocus && lastFocus.focus) lastFocus.focus();
      };
      if (reduceMotion) done();
      else setTimeout(done, 320);
    }

    /* —— 触发 —— */
    triggers.forEach(function (btn, i) {
      btn.addEventListener("click", function () {
        open(i);
      });
    });

    /* —— 浮层内：遮罩点击关闭、左右翻页 —— */
    box.addEventListener("click", function (e) {
      var t = e.target;
      if (t.closest("[data-uc-dismiss]")) {
        close();
        return;
      }
      var step = t.closest("[data-uc-step]");
      if (step) {
        render(current + parseInt(step.getAttribute("data-uc-step"), 10));
      }
    });

    /* —— 键盘：Esc 关闭、← → 翻页 —— */
    document.addEventListener("keydown", function (e) {
      if (box.hidden) return;
      if (e.key === "Escape") {
        e.preventDefault();
        close();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        render(current - 1);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        render(current + 1);
      }
    });

    /* —— 焦点锁在浮层内（Tab 循环）—— */
    box.addEventListener("keydown", function (e) {
      if (e.key !== "Tab") return;
      var focusables = box.querySelectorAll("button");
      if (!focusables.length) return;
      var first = focusables[0];
      var last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    });
  })();
})();
