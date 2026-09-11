// ===== ScrollExpand 滚轮展开组件（React Bits · JavaScript 原生移植） =====
// 机制与 apps/web/src/assets/convix/scroll-expand.js 保持一致：rAF 指数平滑
// （k = 1 - exp(-1/(60*smoothing))）、ResizeObserver 重算、
// prefers-reduced-motion 直接落位、无 ResizeObserver 时静态降级。
// 默认参数：startWidth / startHeight = 100（进入即全幅 → clip-path inset 恒为 0，
// 不再产生"由小变大"的撑开动画），滚动仅驱动：
//   a. scrollHint 0–0.12 淡出并下移 8px；
//   b. 背景媒体 mediaZoom→1 平滑回正；
//   c. 圆角 startRadius→endRadius 收缩；
//   d. title 0.3–0.85 淡出、上移 28px、放大 1.06；
//   e. scrim opacity 按 overlayScrim 淡入；
//   f. overlay（功能卡片）0.62–1 渐显、由下 10px 上移到位；
//   g. 卡片（.se-projects 直接子节点）按实际布局位置，从左右两侧向
//      中间平滑聚合进入（位移 = dir * cardShift * (1 - inn)）。
//
// 用法：根节点加 .js-scroll-expand 类 + data-se-* 配置；大标题放
// .scroll-expand__title，功能卡片放 .scroll-expand__overlay > .se-overlay-inner
// > .se-projects 内；媒体由本脚本依据 data-se-media-* 注入（无源时不注入，背景保持透明）。
(function () {
  'use strict';

  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }

  function smoothstep(edge0, edge1, x) {
    var t = clamp((x - edge0) / (edge1 - edge0 || 1e-6), 0, 1);
    return t * t * (3 - 2 * t);
  }

  // 读取 data-se-* 数值配置，非法值时回退默认值
  function numAttr(root, attr, fallback) {
    var v = parseFloat(root.getAttribute(attr));
    return isNaN(v) ? fallback : v;
  }

  // 镜像 convix 的媒体渲染：video / img；无源时不注入媒体（保持背景透明，
  // 让页面背后的装饰元素（如 shader 粒子）完整透出）
  function buildMedia(root, opts) {
    var frame = root.querySelector('.scroll-expand__frame');
    var media = null;

    if (opts.mediaType === 'video') {
      media = document.createElement('video');
      media.className = 'scroll-expand__media';
      media.src = opts.mediaSrc;
      media.poster = opts.poster;
      media.autoplay = true;
      media.muted = true;
      media.loop = true;
      media.playsInline = true;
    } else if (opts.mediaSrc) {
      media = document.createElement('img');
      media.className = 'scroll-expand__media';
      media.src = opts.mediaSrc;
      media.alt = opts.alt;
      media.draggable = false;
    }

    if (media) frame.insertBefore(media, frame.firstChild);
    return media;
  }

  function init(root) {
    var track = root.querySelector('.scroll-expand__track');
    var stage = root.querySelector('.scroll-expand__stage');
    var frame = root.querySelector('.scroll-expand__frame');
    if (!track || !stage || !frame) return;

    var scrim = root.querySelector('.scroll-expand__scrim');
    var title = root.querySelector('.scroll-expand__title');
    var hint = root.querySelector('.scroll-expand__hint');
    var overlay = root.querySelector('.scroll-expand__overlay');
    var cards = root.querySelectorAll('.se-projects > div');

    // 默认参数：startWidth=100 / startHeight=100（全幅进入），其余与 convix 默认一致
    var opts = {
      startWidth: numAttr(root, 'data-se-start-width', 100),
      startHeight: numAttr(root, 'data-se-start-height', 100),
      startRadius: numAttr(root, 'data-se-start-radius', 24),
      endRadius: numAttr(root, 'data-se-end-radius', 0),
      mediaZoom: numAttr(root, 'data-se-media-zoom', 1.35),
      scrollDistance: numAttr(root, 'data-se-scroll-distance', 1.2),
      holdDistance: numAttr(root, 'data-se-hold-distance', 0.35),
      smoothing: numAttr(root, 'data-se-smoothing', 0.1),
      overlayScrim: numAttr(root, 'data-se-overlay-scrim', 0.45),
      cardShift: numAttr(root, 'data-se-card-shift', 56),
      cardRise: numAttr(root, 'data-se-card-rise', 12),
      useWindowScroll: root.getAttribute('data-se-use-window-scroll') !== 'false',
      mediaType: root.getAttribute('data-se-media-type') || 'image',
      mediaSrc: root.getAttribute('data-se-media-src') || '',
      poster: root.getAttribute('data-se-poster') || '',
      alt: root.getAttribute('data-se-alt') || ''
    };

    // 容器内滚动模式需要 .scroll-expand--scroller（与 convix 的 root class 逻辑一致）
    if (!opts.useWindowScroll) root.classList.add('scroll-expand--scroller');

    var media = buildMedia(root, opts);
    var isRealMedia = !!media && (media.tagName === 'IMG' || media.tagName === 'VIDEO');

    // 不支持 ResizeObserver 的旧环境：退化为静态展示（overlay/title 全部可见）
    if (!('ResizeObserver' in window)) {
      root.classList.add('scroll-expand--static');
      return;
    }

    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var raf = 0;
    var current = 0;
    var target = 0;
    var stageH = 0;
    var running = false;

    // 卡片入场方向：按卡片相对 overlay 中心的实际水平位置判定（左 → -1 / 右 → +1 / 居中 → 0）。
    // 依据真实布局（响应式列流）计算，避免依赖 DOM 顺序揣测列位置。
    var cardDirs = [];
    function measureCards() {
      if (!overlay) return;
      var o = overlay.getBoundingClientRect();
      var ocx = (o.left + o.right) / 2;
      cardDirs = [];
      for (var i = 0; i < cards.length; i++) {
        var r = cards[i].getBoundingClientRect();
        var dx = (r.left + r.right) / 2 - ocx;
        // 单列 / 窄屏下卡片居中，不做水平位移，避免来回抖动
        cardDirs.push(Math.abs(dx) < 8 ? 0 : dx < 0 ? -1 : 1);
      }
    }

    function applyProgress(p) {
      var e = smoothstep(0, 1, p);

      // startWidth/Height=100 时 ix/iy 恒为 0 → clip-path inset 恒为 0%，仅圆角随 e 收缩
      var w = opts.startWidth + (100 - opts.startWidth) * e;
      var h = opts.startHeight + (100 - opts.startHeight) * e;
      var ix = Math.max(0, (100 - w) / 2);
      var iy = Math.max(0, (100 - h) / 2);
      var r = opts.startRadius + (opts.endRadius - opts.startRadius) * e;
      frame.style.clipPath = 'inset(' + iy + '% ' + ix + '% ' + iy + '% ' + ix + '% round ' + r + 'px)';

      // 背景媒体平滑回正（放大 → 原尺寸）
      if (media) media.style.transform = 'scale(' + (opts.mediaZoom + (1 - opts.mediaZoom) * e) + ')';

      if (scrim) scrim.style.opacity = String(opts.overlayScrim * e);

      if (title) {
        var out = smoothstep(0.3, 0.85, p);
        title.style.opacity = String(1 - out);
        title.style.transform = 'translate3d(0, ' + (-28 * out) + 'px, 0) scale(' + (1 + 0.06 * out) + ')';
      }

      if (hint) {
        var gone = smoothstep(0, 0.12, p);
        hint.style.opacity = String(1 - gone);
        hint.style.transform = 'translate3d(0, ' + (8 * gone) + 'px, 0)';
      }

      if (overlay) {
        var inn = smoothstep(0.62, 1, p);
        overlay.style.opacity = String(inn);
        overlay.style.transform = 'translate3d(0, ' + (10 * (1 - inn)) + 'px, 0)';

        // 卡片：从左右两侧向中间平滑进入（位移随进度收敛为 0）
        var kx = 1 - inn;
        for (var i = 0; i < cards.length; i++) {
          var dir = cardDirs[i] || 0;
          cards[i].style.opacity = String(inn);
          cards[i].style.transform =
            'translate3d(' + (dir * opts.cardShift * kx).toFixed(2) + 'px, ' +
            (opts.cardRise * kx).toFixed(2) + 'px, 0)';
        }
      }

      // 实时媒体展开到最全后钉在视口（position: fixed）；回滚（p < 1）时自动解除。
      // 渐变占位媒体不钉住：它随舞台滚动离场，不遮挡后续内容。
      if (isRealMedia) media.classList.toggle('scroll-expand__media--pinned', p >= 0.999);
    }

    function measure() {
      var c = opts;
      stageH = c.useWindowScroll ? window.innerHeight : root.clientHeight;
      if (stageH <= 0) return;
      stage.style.height = stageH + 'px';
      track.style.height = (stageH * (1 + Math.max(0, c.scrollDistance) + Math.max(0, c.holdDistance))) + 'px';

      var w = root.clientWidth || stageH;
      stage.style.setProperty('--se-title-size', clamp(w * 0.075, 20, 84) + 'px');
      measureCards();

      // 仅当卡片内容真的超高（短视口）时才接管滚轮让 overlay 内部滚动；
      // 否则移除 data-lenis-prevent，滚轮继续由 Lenis 平滑驱动页面（展开动画）。 
      if (overlay) {
        if (overlay.scrollHeight > overlay.clientHeight + 1) {
          overlay.setAttribute('data-lenis-prevent', '');
        } else {
          overlay.removeAttribute('data-lenis-prevent');
        }
      }
    }

    function readProgress() {
      var c = opts;
      var span = stageH * Math.max(0.01, c.scrollDistance);
      if (c.useWindowScroll) {
        var top = track.getBoundingClientRect().top;
        return clamp(-top / span, 0, 1);
      }
      return clamp(root.scrollTop / span, 0, 1);
    }

    function tick() {
      var c = opts;
      var k = c.smoothing <= 0 ? 1 : 1 - Math.exp(-1 / (60 * c.smoothing));
      current += (target - current) * k;
      if (Math.abs(target - current) < 0.0004) {
        current = target;
        running = false;
      }
      applyProgress(current);
      raf = running ? requestAnimationFrame(tick) : 0;
    }

    function kick() {
      if (running) return;
      running = true;
      if (!raf) raf = requestAnimationFrame(tick);
    }

    function onScroll() {
      target = readProgress();
      if (opts.smoothing <= 0 || reduceMotion) {
        current = target;
        applyProgress(current);
        return;
      }
      kick();
    }

    function onResize() {
      measure();
      target = readProgress();
      current = target;
      applyProgress(current);
    }

    measure();
    target = readProgress();
    current = target;
    applyProgress(current);

    var scroller = opts.useWindowScroll ? window : root;
    scroller.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onResize);
    // 图片异步加载后卡片列流可能变化，重测入场方向（与 nav.js 的 load 处理一致）
    window.addEventListener('load', onResize);
    var ro = new ResizeObserver(onResize);
    ro.observe(root);

    // 供需要时销毁（SPA 局部刷新等场景）
    root.__seDestroy = function () {
      if (raf) cancelAnimationFrame(raf);
      scroller.removeEventListener('scroll', onScroll);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('load', onResize);
      ro.disconnect();
    };
  }

  function initAll() {
    var nodes = document.querySelectorAll('.js-scroll-expand');
    if (!nodes.length) return;
    nodes.forEach(init);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }
})();
