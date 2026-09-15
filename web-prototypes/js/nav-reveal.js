/* ===== 导航栏悬浮显现（非首页）=====
   交互约定：
   - 默认隐藏（CSS 基础态：上移出视口 + 透明 + pointer-events: none）；
   - 鼠标进入顶部透明触发区（.nav-reveal-zone）→ 导航从上往下滑入；
   - 鼠标移出导航（移回触发区除外）延迟片刻后隐藏；
   - 键盘 Tab 聚焦到导航链接时同样显现，焦点离开后隐藏；
   - 触摸端（hover: none）不接管，由 CSS 保持常显；
   - 站内跳转（点导航里的链接）后到达的新页面：导航立刻显现、不缩回去
     —— 详见下方"站内跳转后导航留在原地"。
   仅接入带有 data-nav-reveal-zone 触发区的页面（非首页）。 */
(() => {
  "use strict";

  const zone = document.querySelector("[data-nav-reveal-zone]");
  const nav = document.querySelector('nav[aria-label="Primary"]');
  if (!zone || !nav) return; // 首页等未接入的页面直接跳过
  if (window.matchMedia("(hover: none)").matches) return;

  const ZONE_HIDE_DELAY = 300;   // 从触发区移出后的隐藏延迟
  const NAV_HIDE_DELAY = 420;    // 从导航移出后的隐藏延迟（留出移动到链接的时间）
  const FOCUS_HIDE_DELAY = 600;  // 键盘焦点离开导航后的隐藏延迟
  let hideTimer = 0;

  const show = () => {
    clearTimeout(hideTimer);
    nav.classList.add("nav-reveal--visible");
  };

  const hide = () => {
    clearTimeout(hideTimer);
    nav.classList.remove("nav-reveal--visible");
  };

  const scheduleHide = (delay) => {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hide, delay);
  };

  /* ===== 站内跳转后"导航留在原地" =====
     点导航里的链接跳走时，鼠标通常一动没动：新页面上 mouseenter 不会触发，
     导航就一直缩在顶部外面 —— 用户看到的是"跳转后导航缩回去了"，
     点击后的第一次气泡动画（GooeyNav burstOnShow）也就无从播起。
     做法：点导航链接时留一个一次性标记（sessionStorage），新页面加载时据此
     立刻显现；再用 :hover 兜住"加载时光标本来就停在触发区/导航上"的情况。
     其余行为一概不变：显现后仍由下面原有的监听接管，鼠标移开照旧延迟隐藏。 */
  const ARRIVAL_KEY = "vv-nav-arrival";
  const ARRIVAL_TTL = 10000; // 10s 内有效，避免标记长期残留导致误显现

  const markArrival = () => {
    try {
      sessionStorage.setItem(ARRIVAL_KEY, String(Date.now()));
    } catch (e) {
      /* file:// 下可能禁用 sessionStorage，忽略 */
    }
  };

  const consumeArrival = () => {
    let stamp = null;
    try {
      stamp = sessionStorage.getItem(ARRIVAL_KEY);
      sessionStorage.removeItem(ARRIVAL_KEY); // 一次性的：只影响紧随其后的那一页
    } catch (e) {
      /* 同上 */
    }
    const t = Number(stamp);
    return Number.isFinite(t) && t > 0 && Date.now() - t < ARRIVAL_TTL;
  };

  // 点到导航里的链接（含键盘 Space/Enter 触发的 click）→ 记下"这次跳转来自导航"
  nav.addEventListener("click", (e) => {
    if (e.target instanceof Element && e.target.closest("a[href]")) markArrival();
  });

  // 带着标记回来、或光标本来就悬在触发区/导航上 → 直接显现。
  // 这一次不走 0.5s 滑入（.nav-reveal--instant 临时关掉过渡）：跳转前后导航
  // 都在同一个位置，直接落位才是"它一直在那儿"；滑一下反而像重新进场，
  // 而且会把 GooeyNav 的气泡动画前 0.5s 盖在淡入里。
  if (consumeArrival() || zone.matches(":hover") || nav.matches(":hover")) {
    nav.classList.add("nav-reveal--instant");
    show();
    requestAnimationFrame(() => {
      requestAnimationFrame(() => nav.classList.remove("nav-reveal--instant"));
    });
  }

  // 触发区：进入立即显现；离开时若移入导航本身则保持，否则稍后隐藏。
  zone.addEventListener("mouseenter", show);
  zone.addEventListener("mouseleave", (e) => {
    if (e.relatedTarget && nav.contains(e.relatedTarget)) return;
    scheduleHide(ZONE_HIDE_DELAY);
  });

  // 导航：悬浮期间保持显现；移出导航（回到触发区除外）后隐藏。
  nav.addEventListener("mouseenter", show);
  nav.addEventListener("mouseleave", (e) => {
    if (e.relatedTarget && zone.contains(e.relatedTarget)) return;
    scheduleHide(NAV_HIDE_DELAY);
  });

  // 键盘可达性：焦点进入导航时显现，离开后隐藏。
  nav.addEventListener("focusin", show);
  nav.addEventListener("focusout", () => scheduleHide(FOCUS_HIDE_DELAY));
})();
