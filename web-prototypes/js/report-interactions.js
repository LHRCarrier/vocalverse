/* ===== report.html 交互增强：图表绘制入场、数字滚动、卡片错峰、提示气泡 =====
 * 1. 为带 data-tip 的 SVG 元素生成 <title> 气泡（悬浮提示）；
 * 2. 图表（雷达/折线/环形/弧线/点阵）进入视口后绘制入场；
 * 3. .count-up 元素在进入视口时数字滚动（支持 data-prefix / data-suffix / data-dec）；
 * 4. 卡片 / KPI 瓦片进入视口后错峰上浮；
 * 5. prefers-reduced-motion 时全部静态展示（默认可见，不做任何隐藏）。
 * ============================================================= */
(function () {
  'use strict';

  var SVGNS = 'http://www.w3.org/2000/svg';
  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var EASE = 'cubic-bezier(0.22, 1, 0.36, 1)';

  // —— 提示气泡：data-tip → <title> ——
  document.querySelectorAll('[data-tip]').forEach(function (el) {
    if (!el.querySelector('title')) {
      var t = document.createElementNS(SVGNS, 'title');
      t.textContent = el.getAttribute('data-tip');
      el.appendChild(t);
    }
  });

  if (reduceMotion) return; // 减弱动效：全部保持静态可见

  document.body.classList.add('js-report-anim');

  // —— 准备绘制动画：把路径长度写入 dash 变量（由 CSS 过渡驱动） ——
  document.querySelectorAll('.draw-path, .draw-poly, .arc-path').forEach(function (el) {
    try {
      var len = Math.ceil(el.getTotalLength());
      el.style.setProperty('--len', len);
      el.setAttribute('stroke-dasharray', len + ' ' + len);
    } catch (e) { /* 隐藏元素等情形，忽略 */ }
  });

  // —— 图表入场：进入视口 → .is-anim ——
  var charts = document.querySelectorAll('.report-chart .report-anim, .report-arc');
  if (charts.length) {
    var ioChart = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        en.target.classList.add('is-anim');
        ioChart.unobserve(en.target);
      });
    }, { threshold: 0.35 });
    charts.forEach(function (el) { ioChart.observe(el); });
  }

  // —— 点阵：逐点弹入（点由内联脚本生成，带 data-o 与隐藏初态） ——
  var dotsSvg = document.querySelector('.report-dots');
  if (dotsSvg) {
    var revealDots = function () {
      var dots = dotsSvg.querySelectorAll('circle');
      dots.forEach(function (c, i) {
        var o = c.getAttribute('data-o') || c.getAttribute('opacity');
        c.style.transition =
          'opacity 0.5s ' + EASE + ' ' + (i * 8) + 'ms, transform 0.5s ' + EASE + ' ' + (i * 8) + 'ms';
        c.style.opacity = o;
        c.style.transform = 'scale(1)';
      });
    };
    var ioDots = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        revealDots();
        ioDots.unobserve(en.target);
      });
    }, { threshold: 0.4 });
    ioDots.observe(dotsSvg);
  }

  // —— 数字滚动（count-up） ——
  var counters = document.querySelectorAll('.count-up');
  counters.forEach(function (el) {
    if (!el.hasAttribute('data-to')) el.setAttribute('data-to', el.textContent.trim());
  });
  var runCount = function (el) {
    var to = parseFloat(el.getAttribute('data-to'));
    if (isNaN(to)) return;
    var dec = parseInt(el.getAttribute('data-dec') || '0', 10) || 0;
    var prefix = el.getAttribute('data-prefix') || '';
    var suffix = el.getAttribute('data-suffix') || '';
    var start = performance.now();
    var dur = 1100;
    var step = function (now) {
      var t = Math.min(1, (now - start) / dur);
      var k = 1 - Math.pow(1 - t, 3); // ease-out-cubic
      var v = Math.round(to * k * Math.pow(10, dec)) / Math.pow(10, dec);
      el.textContent = prefix + (dec ? v.toFixed(dec) : String(Math.round(v))) + suffix;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  if (counters.length) {
    var ioCount = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        runCount(en.target);
        ioCount.unobserve(en.target);
      });
    }, { threshold: 0.5 });
    counters.forEach(function (el) { ioCount.observe(el); });
  }

  // —— 卡片 / KPI / 瓦片：进入视口后按兄弟顺序错峰上浮 ——
  var animIn = document.querySelectorAll('.report-card, .report-kpi, .stat-tile');
  if (animIn.length) {
    var ioAnim = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target;
        var idx = Array.prototype.indexOf.call(el.parentNode.children, el);
        el.style.transitionDelay = ((idx % 8) * 70) + 'ms';
        el.classList.add('is-inview');
        // 入场结束后释放过渡与延迟，交还给悬浮交互（0.8s 动画 + 缓冲）
        setTimeout(function () {
          el.style.transitionDelay = '';
          el.classList.add('anim-done');
        }, 950 + (idx % 8) * 70);
        ioAnim.unobserve(el);
      });
    }, { threshold: 0.15, rootMargin: '0px 0px -60px 0px' });
    animIn.forEach(function (el) {
      el.classList.add('anim-in');
      ioAnim.observe(el);
    });
  }
})();
