// ===== GradualBlur 渐进模糊组件（React Bits · JavaScript + CSS 变体 · 原生移植）=====
// 与 React 版逐项对齐：DEFAULT_CONFIG / PRESETS 预设、CURVE_FUNCTIONS 曲线、
// 逐层 mask-image 渐变 + backdrop-filter 叠加、hoverIntensity 悬停加强、
// animated（true 淡入 / "scroll" 进视口淡入）、responsive 响应式取值。
//
// —— 页面集成层（本原型用法）——
// 引入本文件后自动在视口底边挂一条模糊带：新内容滚动进入视口底部时被逐层
// 模糊，越靠近底边越糊，像从雾里"浮现"。参数写在 <html> / <body> 的
// data-gb-* 属性上；<body data-gb="off"> 可整页关闭。
//
// —— 局部用法（组件形态）——
// 任意容器加 .js-gradual-blur + data-gb-* 即可：
//   <section style="position:relative;overflow:hidden">
//     <div class="js-gradual-blur" data-gb-target="parent" data-gb-position="bottom"
//          data-gb-height="6rem" data-gb-strength="2" data-gb-div-count="5"
//          data-gb-curve="bezier" data-gb-exponential data-gb-opacity="1"></div>
//   </section>
// 父容器 position 为 static 时脚本会自动补 position:relative（原型便利，省去手写）。
//
// —— data-gb-* 属性表 ——
//   position / strength / height / width / div-count / exponential / curve /
//   opacity / animated（true | scroll | false）/ duration / easing /
//   hover-intensity / target（parent | page）/ preset / responsive /
//   z-index / class / hide-near-end / mobile|tablet|desktop-height /
//   mobile|tablet|desktop-width
//
// —— 三处与原版的偏差（均为本原型的落地取舍）——
//   1. z-index：原版 target="page" 会额外 +100（默认 1000 → 1100）。本原型导航
//      z-50、nav 触发区 z-49、首页移动端菜单 z-60，+100 会把模糊带顶到它们之上；
//      这里直接取 data-gb-z-index（页面层默认 45：高于正文与 pinned 媒体，
//      低于导航/菜单）。模糊带与导航一在底一在顶，几何上本就不重叠。
//   2. 新增 hide-near-end（默认开）：滚到文档末尾时淡出。否则页脚上方常驻
//      一层雾，属于"效果"之外的多余遮挡。
//   3. 官方标注依赖 mathjs，但组件源码只用原生 Math，故本移植不引入任何依赖。
(function () {
  'use strict';

  var END_FADE_PX = 160; // 距文档末尾多少像素以内开始淡出

  var DEFAULT_CONFIG = {
    position: 'bottom',
    strength: 2,
    height: '6rem',
    divCount: 5,
    exponential: false,
    zIndex: 1000,
    animated: false,
    duration: '0.3s',
    easing: 'ease-out',
    opacity: 1,
    curve: 'linear',
    responsive: false,
    target: 'parent',
    className: ''
  };

  var PRESETS = {
    top: { position: 'top', height: '6rem' },
    bottom: { position: 'bottom', height: '6rem' },
    left: { position: 'left', height: '6rem' },
    right: { position: 'right', height: '6rem' },
    subtle: { height: '4rem', strength: 1, opacity: 0.8, divCount: 3 },
    intense: { height: '10rem', strength: 4, divCount: 8, exponential: true },
    smooth: { height: '8rem', curve: 'bezier', divCount: 10 },
    sharp: { height: '5rem', curve: 'linear', divCount: 4 },
    header: { position: 'top', height: '8rem', curve: 'ease-out' },
    footer: { position: 'bottom', height: '8rem', curve: 'ease-out' },
    sidebar: { position: 'left', height: '6rem', strength: 2.5 },
    'page-header': { position: 'top', height: '10rem', target: 'page', strength: 3 },
    'page-footer': { position: 'bottom', height: '10rem', target: 'page', strength: 3 }
  };

  var CURVE_FUNCTIONS = {
    linear: function (p) { return p; },
    bezier: function (p) { return p * p * (3 - 2 * p); },
    'ease-in': function (p) { return p * p; },
    'ease-out': function (p) { return 1 - Math.pow(1 - p, 2); },
    'ease-in-out': function (p) {
      return p < 0.5 ? 2 * p * p : 1 - Math.pow(-2 * p + 2, 2) / 2;
    }
  };

  // 页面集成层默认值：只铺视口底边 · 克制的轻模糊（strength 1.6 / 5 层 / 7rem）
  var PAGE_DEFAULTS = {
    target: 'page',
    position: 'bottom',
    height: '7rem',
    strength: 1.6,
    divCount: 5,
    curve: 'bezier',
    exponential: true,
    opacity: 1,
    zIndex: 45,
    animated: true,
    hideNearEnd: true
  };

  var GRADIENT_DIRECTIONS = {
    top: 'to top',
    bottom: 'to bottom',
    left: 'to left',
    right: 'to right'
  };

  function getGradientDirection(position) {
    return GRADIENT_DIRECTIONS[position] || 'to bottom';
  }

  function mergeConfigs() {
    var out = {};
    for (var i = 0; i < arguments.length; i++) {
      var c = arguments[i];
      if (!c) continue;
      for (var k in c) {
        if (Object.prototype.hasOwnProperty.call(c, k)) out[k] = c[k];
      }
    }
    return out;
  }

  function debounce(fn, wait) {
    var t;
    return function () {
      var self = this;
      var a = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(self, a); }, wait);
    };
  }

  // ---------- data-gb-* → 配置对象 ----------

  var ATTR_MAP = {
    'data-gb-position': 'position',
    'data-gb-strength': 'strength',
    'data-gb-height': 'height',
    'data-gb-width': 'width',
    'data-gb-div-count': 'divCount',
    'data-gb-exponential': 'exponential',
    'data-gb-curve': 'curve',
    'data-gb-opacity': 'opacity',
    'data-gb-animated': 'animated',
    'data-gb-duration': 'duration',
    'data-gb-easing': 'easing',
    'data-gb-hover-intensity': 'hoverIntensity',
    'data-gb-target': 'target',
    'data-gb-preset': 'preset',
    'data-gb-responsive': 'responsive',
    'data-gb-z-index': 'zIndex',
    'data-gb-class': 'className',
    'data-gb-hide-near-end': 'hideNearEnd',
    'data-gb-mobile-height': 'mobileHeight',
    'data-gb-tablet-height': 'tabletHeight',
    'data-gb-desktop-height': 'desktopHeight',
    'data-gb-mobile-width': 'mobileWidth',
    'data-gb-tablet-width': 'tabletWidth',
    'data-gb-desktop-width': 'desktopWidth'
  };

  var NUM_KEYS = { strength: 1, divCount: 1, opacity: 1, hoverIntensity: 1, zIndex: 1 };
  var BOOL_KEYS = { exponential: 1, responsive: 1, hideNearEnd: 1 };

  function isTruthyAttr(v) {
    return v === '' || v === 'true' || v === '1' || v === 'yes';
  }

  function readConfig(el) {
    var cfg = {};
    if (!el || !el.getAttribute) return cfg;

    for (var attr in ATTR_MAP) {
      if (!Object.prototype.hasOwnProperty.call(ATTR_MAP, attr)) continue;
      if (!el.hasAttribute(attr)) continue;

      var key = ATTR_MAP[attr];
      var raw = el.getAttribute(attr);

      if (BOOL_KEYS[key]) {
        cfg[key] = isTruthyAttr(raw);
      } else if (NUM_KEYS[key]) {
        var n = parseFloat(raw);
        if (!isNaN(n)) cfg[key] = n;
      } else if (key === 'animated') {
        // true 淡入 / "scroll" 进视口淡入 / false 常驻
        cfg[key] = raw === 'scroll' ? 'scroll' : isTruthyAttr(raw);
      } else {
        cfg[key] = raw;
      }
    }
    return cfg;
  }

  // ---------- 响应式取值（对应原版 useResponsiveDimension） ----------

  function responsiveValue(config, key) {
    if (!config.responsive) return config[key];
    var cap = key.charAt(0).toUpperCase() + key.slice(1);
    var w = window.innerWidth;
    if (w <= 480 && config['mobile' + cap] !== undefined) return config['mobile' + cap];
    if (w <= 768 && config['tablet' + cap] !== undefined) return config['tablet' + cap];
    if (w <= 1024 && config['desktop' + cap] !== undefined) return config['desktop' + cap];
    return config[key];
  }

  // ---------- 组件实例 ----------

  function createBlur(opts) {
    var config = mergeConfigs(
      DEFAULT_CONFIG,
      opts.preset && PRESETS[opts.preset] ? PRESETS[opts.preset] : null,
      opts
    );

    var isPageTarget = config.target === 'page';
    var isVertical = config.position === 'top' || config.position === 'bottom';
    var isHorizontal = config.position === 'left' || config.position === 'right';

    var el = document.createElement('div');
    el.className =
      'gradual-blur ' +
      (isPageTarget ? 'gradual-blur-page' : 'gradual-blur-parent') +
      (config.className ? ' ' + config.className : '');
    el.setAttribute('aria-hidden', 'true'); // 纯装饰层，不进无障碍树

    var inner = document.createElement('div');
    inner.className = 'gradual-blur-inner';
    inner.style.position = 'relative';
    inner.style.width = '100%';
    inner.style.height = '100%';
    el.appendChild(inner);

    var hovered = false;
    var visible = false; // 出现时置 true → 由 CSS/内联 transition 淡入
    var atEnd = false;
    var hasStarted = false;
    var destroyed = false;
    var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // ---- 逐层：mask-image 渐变 + backdrop-filter（对应原版 blurDivs useMemo）----
    function renderLayers() {
      var increment = 100 / config.divCount;
      var currentStrength =
        hovered && config.hoverIntensity ? config.strength * config.hoverIntensity : config.strength;
      var curveFunc = CURVE_FUNCTIONS[config.curve] || CURVE_FUNCTIONS.linear;
      var direction = getGradientDirection(config.position);

      var frag = document.createDocumentFragment();

      for (var i = 1; i <= config.divCount; i++) {
        var progress = curveFunc(i / config.divCount);
        var blurValue = config.exponential
          ? Math.pow(2, progress * 4) * 0.0625 * currentStrength
          : 0.0625 * (progress * config.divCount + 1) * currentStrength;

        var p1 = Math.round((increment * i - increment) * 10) / 10;
        var p2 = Math.round(increment * i * 10) / 10;
        var p3 = Math.round((increment * i + increment) * 10) / 10;
        var p4 = Math.round((increment * i + increment * 2) * 10) / 10;

        var gradient = 'transparent ' + p1 + '%, black ' + p2 + '%';
        if (p3 <= 100) gradient += ', black ' + p3 + '%';
        if (p4 <= 100) gradient += ', transparent ' + p4 + '%';

        var mask = 'linear-gradient(' + direction + ', ' + gradient + ')';
        var blur = 'blur(' + blurValue.toFixed(3) + 'rem)';

        var layer = document.createElement('div');
        var s = layer.style;
        s.position = 'absolute';
        s.inset = '0';
        s.maskImage = mask;
        s.webkitMaskImage = mask;
        s.backdropFilter = blur;
        s.webkitBackdropFilter = blur;
        s.opacity = String(config.opacity);
        s.transition =
          config.animated && config.animated !== 'scroll'
            ? 'backdrop-filter ' + config.duration + ' ' + config.easing
            : '';

        frag.appendChild(layer);
      }

      inner.textContent = '';
      inner.appendChild(frag);
    }

    // ---- 容器几何与显隐（对应原版 containerStyle useMemo）----
    function apply() {
      var s = el.style;
      var h = responsiveValue(config, 'height');
      var w = responsiveValue(config, 'width');

      s.position = isPageTarget ? 'fixed' : 'absolute';
      s.pointerEvents = config.hoverIntensity ? 'auto' : 'none';
      s.opacity = visible && !atEnd ? '1' : '0';
      s.zIndex = String(config.zIndex);
      // animated 为假时清空内联 transition，回落到 .gradual-blur 的 CSS 过渡
      s.transition = config.animated
        ? 'opacity ' + config.duration + ' ' + config.easing
        : '';

      if (isVertical) {
        s.height = h;
        s.width = w || '100%';
        s.left = '0';
        s.right = '0';
        s.top = '';
        s.bottom = '';
        s[config.position] = '0';
      } else if (isHorizontal) {
        s.width = w || h;
        s.height = '100%';
        s.top = '0';
        s.bottom = '0';
        s.left = '';
        s.right = '';
        s[config.position] = '0';
      }

      if (config.style) {
        for (var k in config.style) {
          if (Object.prototype.hasOwnProperty.call(config.style, k)) s[k] = config.style[k];
        }
      }
    }

    // ---- 滚到文档末尾淡出（本移植新增，见文件头偏差 2）----
    function updateEnd() {
      if (!config.hideNearEnd || !isPageTarget) return;
      var doc = document.documentElement;
      var max = (doc.scrollHeight || 0) - window.innerHeight;
      var y = window.pageYOffset || doc.scrollTop || 0;
      var next = max > 8 && max - y < END_FADE_PX;
      if (next !== atEnd) {
        atEnd = next;
        apply();
      }
    }

    function onScroll() {
      updateEnd();
    }

    var onResize = debounce(function () {
      apply();
    }, 100);

    // ---- 悬停加强（对应原版 hoverIntensity / isHovered）----
    function onEnter() {
      hovered = true;
      renderLayers();
    }
    function onLeave() {
      hovered = false;
      renderLayers();
    }

    // ---- 进视口淡入（对应原版 useIntersectionObserver）----
    var observer = null;
    function startObserving() {
      if (!('IntersectionObserver' in window) || !el.parentNode) {
        visible = true;
        apply();
        return;
      }
      observer = new IntersectionObserver(
        function (entries) {
          visible = entries[0].isIntersecting;
          apply();
        },
        { threshold: 0.1 }
      );
      observer.observe(el);
    }

    var api = {
      el: el,
      config: config,

      // 挂载到 DOM 后调用：首帧 opacity 0 → 下一帧 1，得到一次淡入
      start: function () {
        if (hasStarted || destroyed) return;
        hasStarted = true;

        if (!isPageTarget && el.parentNode) {
          var parent = el.parentNode;
          if (window.getComputedStyle(parent).position === 'static') {
            parent.style.position = 'relative';
          }
        }

        visible = reduceMotion; // 减动效时直接常驻，不淡入
        apply();

        if (config.animated === 'scroll' && !isPageTarget) {
          startObserving();
        } else if (!reduceMotion) {
          requestAnimationFrame(function () {
            if (destroyed) return;
            visible = true;
            apply();
          });
        } else {
          visible = true;
          apply();
        }

        if (config.hoverIntensity) {
          el.addEventListener('mouseenter', onEnter);
          el.addEventListener('mouseleave', onLeave);
        }

        if (config.hideNearEnd && isPageTarget) {
          window.addEventListener('scroll', onScroll, { passive: true });
          window.addEventListener('resize', onScroll);
          window.addEventListener('load', onScroll);
          document.addEventListener('scroll', onScroll, { passive: true });
          updateEnd();
        }

        if (config.responsive) window.addEventListener('resize', onResize);
      },

      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        if (observer) observer.disconnect();
        el.removeEventListener('mouseenter', onEnter);
        el.removeEventListener('mouseleave', onLeave);
        window.removeEventListener('scroll', onScroll);
        window.removeEventListener('resize', onScroll);
        window.removeEventListener('load', onScroll);
        document.removeEventListener('scroll', onScroll);
        window.removeEventListener('resize', onResize);
        if (el.parentNode) el.parentNode.removeChild(el);
      }
    };

    renderLayers();
    apply();
    return api;
  }

  // ---------- 挂载 ----------

  var instances = [];

  function readGlobalConfig() {
    var cfg = mergeConfigs(readConfig(document.documentElement), readConfig(document.body));
    // 页面集成层只做"贴视口"这一件事；要贴父容器请用 .js-gradual-blur 局部挂载
    cfg.target = 'page';
    return cfg;
  }

  function initPageBand() {
    var de = document.documentElement;
    var b = document.body;
    if (
      (de && de.getAttribute('data-gb') === 'off') ||
      (b && b.getAttribute('data-gb') === 'off')
    ) {
      return;
    }

    var inst = createBlur(mergeConfigs(PAGE_DEFAULTS, readGlobalConfig()));
    document.body.appendChild(inst.el);
    inst.start();
    instances.push(inst);
  }

  function initHosts() {
    var hosts = document.querySelectorAll('.js-gradual-blur');
    for (var i = 0; i < hosts.length; i++) {
      var host = hosts[i];
      // 标记类本身就是要挂载的容器，避免重复 init
      if (host.getAttribute('data-gb-mounted') === 'true') continue;
      host.setAttribute('data-gb-mounted', 'true');

      var inst = createBlur(readConfig(host));
      host.appendChild(inst.el);
      inst.start();
      instances.push(inst);
    }
  }

  function initAll() {
    if (!document.body) return;
    initHosts();
    initPageBand();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }

  // 供调试/SPA 复用（与 js/scroll-expand.js 暴露 __seDestroy 的做法一致）
  window.GradualBlur = {
    create: function (opts) {
      var inst = createBlur(opts || {});
      document.body.appendChild(inst.el);
      inst.start();
      instances.push(inst);
      return inst;
    },
    presets: PRESETS,
    curves: CURVE_FUNCTIONS,
    destroyAll: function () {
      instances.slice().forEach(function (i) { i.destroy(); });
      instances = [];
    }
  };
})();
