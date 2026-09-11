/* 导航：激活项下的圆角 pill 指示器（弹簧近似动画）
   尺寸/间距见 css/site-nav.css —— 这里只负责指示器定位：
   - 激活项下画 pill，随窗口尺寸变化重新贴合；
   - 窄屏条子可横向滚动（css/site-nav.css 的溢出兜底），
     滚动时同步指示器，并在进入页面时把当前页滚进视野中央。 */
(() => {
  const pill = document.querySelector("[data-nav-pill]");
  const list = document.querySelector("[data-nav-list]");
  if (!pill || !list) return;

  const bar = list.closest(".site-nav__bar") || list.parentElement;
  const active = list.querySelector('a[aria-current="page"]');
  if (!active) {
    pill.hidden = true;
    return;
  }

  const move = (animate) => {
    const listRect = list.getBoundingClientRect();
    const itemRect = active.getBoundingClientRect();
    const x = itemRect.left - listRect.left;
    const w = itemRect.width;
    if (!animate) {
      pill.style.transition = "none";
      pill.style.transform = `translateX(${x}px)`;
      pill.style.width = `${w}px`;
      void pill.offsetHeight; // 强制重排
      pill.style.transition = "";
    } else {
      pill.style.transform = `translateX(${x}px)`;
      pill.style.width = `${w}px`;
    }
    pill.hidden = false;
  };

  /* 窄屏：条子放不下时把当前页滚到中间，否则用户看到的可能是一排别的入口 */
  const centerActive = () => {
    if (!bar) return;
    const over = bar.scrollWidth - bar.clientWidth;
    if (over <= 1) return;
    const barRect = bar.getBoundingClientRect();
    const itemRect = active.getBoundingClientRect();
    const delta = itemRect.left + itemRect.width / 2 - (barRect.left + barRect.width / 2);
    bar.scrollLeft = Math.max(0, Math.min(bar.scrollLeft + delta, over));
  };

  requestAnimationFrame(() =>
    requestAnimationFrame(() => {
      centerActive();
      move(false);
    })
  );
  window.addEventListener("load", () => {
    centerActive();
    move(true);
  });
  window.addEventListener("resize", () => move(true));
  /* 条子横向滚动时指示器跟着走（用无动画版，避免跟手时拖影） */
  if (bar) bar.addEventListener("scroll", () => move(false), { passive: true });
})();
