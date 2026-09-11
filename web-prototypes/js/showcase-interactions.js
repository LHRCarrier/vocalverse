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
     屏幕内容用 iframe 装真页面（390×844），非贴图。
     说明文字走站点令牌渲染，因此深浅主题都会跟着变 —— 这是换成活框的主要收益。
     ============================================================ */
  var PHONE_W = 433, PHONE_H = 882;
  var SCREEN_X = 21.25, SCREEN_Y = 19.25;
  /* 屏幕区尺寸与圆角：路径里已按数值写死，这里留作几何参照（与 CSS 的 .uc-phone__screen 对应）*/
  var SCREEN_W = 389.5, SCREEN_H = 843.5, SCREEN_R = 55.75;

  var PHONE_GROUPS = {
    "uc-1": [
      { src: "assets/app-screens/home.html", title: "今日学习主页", desc: "底部浮动 Tab 栏 · 打卡徽章 · 统计卡 · 全宽分段控件" },
      { src: "assets/app-screens/speaking.html", title: "场景对话", desc: "对话气泡 · 语言点 chip · 录音大按钮（波纹动效）" },
      { src: "assets/app-screens/report.html", title: "唱歌评分报告", desc: "深紫成绩卡 · 四维统计行 · 逐句评分列表" }
    ],
    "uc-2": [
      { src: "assets/feature-screens/s1-inputs.html", title: "胶囊输入框", desc: "默认 / 填充 / 聚焦 / 禁用 四态" },
      { src: "assets/feature-screens/s2-buttons.html", title: "按钮五态", desc: "Hover · Pressed · Disabled · Loading · Focus" },
      { src: "assets/feature-screens/s3-controls.html", title: "分段控件与图标按钮", desc: "56px 分段 · 图标-only 必带 Tooltip" }
    ],
    "uc-3": [
      { src: "assets/feature-screens/s4-imagecard.html", title: "图片卡", desc: "大图 r-24 · 文字压图底 · hover 浮出操作" },
      { src: "assets/feature-screens/s5-lightbox.html", title: "近黑浮层预览", desc: "全屏压暗 · 幽灵描边按钮" },
      { src: "assets/feature-screens/s6-dialog.html", title: "遮罩弹窗 · Toast · 空状态", desc: "白卡 r-24 + 浅色遮罩 · Toast 浮顶" }
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
      /* 刻意不加 loading="lazy"：9 台机一次性加载更可预期，
         且这些页面都是本地单文件、无外部字体/图片请求，代价可忽略；
         lazy 若未按预期触发，机身里就是一片空白，不划算。 */
      '<iframe src="' + item.src + '" scrolling="no" title="' + item.title + '"></iframe>' +
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
       iframe 固定按 390×844 渲染，再整体缩放到屏幕框尺寸，
       保证页面按设计视口排版而不是被挤压变形。 */
    var screens = [];
    Array.prototype.forEach.call(hosts, function (host) {
      Array.prototype.forEach.call(host.querySelectorAll(".uc-phone__screen"), function (s) {
        screens.push(s);
      });
    });

    function fit() {
      screens.forEach(function (s) {
        var iframe = s.querySelector("iframe");
        if (!iframe) return;
        var w = s.clientWidth;
        if (!w) return;
        var scale = w / 390;
        iframe.style.transform = "scale(" + scale.toFixed(5) + ")";
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
