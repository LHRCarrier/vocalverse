// ===== 滚动入场动画（卡片揭示）=====
// 使用 IntersectionObserver 实现：卡片进入视口 30% 时触发动画
// 触发后立即停止观察（unobserve），天然防抖动，动画完成后保持最终状态
(function () {
  var THRESHOLD = 0.3; // 卡片进入视口 30% 以上时触发

  // 应用 data-reveal-delay 交错延迟（仅作用于入场动画）
  function applyDelay(el) {
    var delay = el.getAttribute('data-reveal-delay');
    if (delay) {
      el.style.transitionDelay = delay + 'ms';
    }
  }

  // 触发显示：添加完成态类，并在动画结束后清除延迟
  function revealNow(el) {
    el.classList.add('reveal-active');
    var onEnd = function () {
      el.style.transitionDelay = '';
      el.removeEventListener('transitionend', onEnd);
    };
    el.addEventListener('transitionend', onEnd);
  }

  function init() {
    var items = document.querySelectorAll('.reveal');
    if (!items.length) return;

    // 降级处理：不支持 IntersectionObserver 的旧浏览器直接显示全部
    if (!('IntersectionObserver' in window)) {
      items.forEach(revealNow);
      return;
    }

    items.forEach(applyDelay);

    var observer = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          revealNow(entry.target);
          observer.unobserve(entry.target); // 只触发一次，避免滚动中反复触发
        }
      });
    }, { threshold: THRESHOLD });

    items.forEach(function (el) {
      observer.observe(el);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
