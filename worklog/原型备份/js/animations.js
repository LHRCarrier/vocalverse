/* 滚动触发的入场动画
   1) .fade-in / .scale-unblur —— 整段淡入（替换 Framer Motion 的 FadeIn / ScaleUnblur）
   2) 五个介绍页（practice / sing / recommend / community / stats）feature 版块里的
      「揭示组」—— 进入视口后加 .is-revealed，组内的卡片与文字再按
      css/feature-blocks.css 第 7 节的 nth-child 节奏错开播放。 */
(() => {
  const fadeEls = document.querySelectorAll(".fade-in, .scale-unblur");
  const groups = document.querySelectorAll(
    ".fs-head, .fs-steps, .fs-duo__text, .fs-duo__card, .fs-kpis, .fs-list, .fs-band"
  );
  if (!fadeEls.length && !groups.length) return;

  const revealAll = () => {
    fadeEls.forEach((el) => el.classList.add("is-inview"));
    groups.forEach((el) => el.classList.add("is-revealed"));
  };

  // 减弱动效、或没有 IntersectionObserver：直接全部显示。
  // 后者的兜底是必须的 —— 隐藏态写死在 CSS 里，观察器再缺席就会永久看不见。
  if (
    window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
    !("IntersectionObserver" in window)
  ) {
    revealAll();
    return;
  }

  const observe = (nodes, className, options) => {
    if (!nodes.length) return;
    const pending = new Set(nodes);

    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) reveal(entry.target);
      });
      // 兜底：跳转式滚动（End 键 / 锚点跳转 / 浏览器恢复滚动位置）会让元素
      // 直接从视口下方跳到上方，交集比例前后都是 0，IO 根本不会回调 —— 只靠
      // isIntersecting 会把它永久留在隐藏态。这里顺带扫一遍还没揭示的元素，
      // 把「整块已经滚到视口上方」的补上。
      // 判据用 bottom < 0（完全离开视口上方），不是 top < innerHeight ——
      // 后者会把还没越过 90% 触发线的元素提前揭示，等于废掉 rootMargin。
      pending.forEach((el) => {
        if (el.getBoundingClientRect().bottom < 0) reveal(el);
      });
    }, options);

    function reveal(el) {
      if (!pending.has(el)) return;
      pending.delete(el);
      el.classList.add(className);
      io.unobserve(el); // 只触发一次，避免滚动中反复播放
    }

    nodes.forEach((el) => io.observe(el));
  };

  observe(fadeEls, "is-inview", { threshold: 0.08, rootMargin: "0px 0px -40px 0px" });
  // 揭示组按「顶边越过视口下缘 10%」判定：与目标自身高度无关，
  // 所以 30 多行的 .fs-list 也不会因为比例阈值而迟迟不触发。
  // 不吃掉更多下缘：留白太多会在视口底部留下"已见标题、卡片还没出现"的空档。
  observe(groups, "is-revealed", { threshold: 0, rootMargin: "0px 0px -10% 0px" });
})();
