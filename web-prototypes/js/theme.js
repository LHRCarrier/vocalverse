/* 主题切换：class 策略 + 圆形 View Transition 扩散动画 */
(() => {
  const root = document.documentElement;
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) return;

  const sunIcon = toggle.querySelector(".sun-icon");
  const moonIcon = toggle.querySelector(".moon-icon");

  const applyIcons = () => {
    const isDark = root.classList.contains("dark");
    const set = (el, rotate, scale, opacity) => {
      el.style.transform = `rotate(${rotate}deg) scale(${scale})`;
      el.style.opacity = opacity;
    };
    if (isDark) {
      set(sunIcon, 0, 1, 1);
      set(moonIcon, 90, 0, 0);
    } else {
      set(sunIcon, -90, 0, 0);
      set(moonIcon, 0, 1, 1);
    }
  };

  const commit = (next) => {
    root.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("theme", next);
    } catch (e) {
      /* file:// 下可能禁用 localStorage */
    }
    toggle.setAttribute("aria-pressed", String(next === "dark"));
    applyIcons();
  };

  toggle.addEventListener("click", (e) => {
    const isDark = root.classList.contains("dark");
    const next = isDark ? "light" : "dark";
    const prefersReducedMotion =
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const supportsVT =
      typeof document.startViewTransition === "function" && !prefersReducedMotion;

    if (!supportsVT) {
      commit(next);
      return;
    }

    const rect = e.currentTarget.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const radius = Math.hypot(
      Math.max(cx, window.innerWidth - cx),
      Math.max(cy, window.innerHeight - cy)
    );
    root.style.setProperty("--theme-cx", `${cx}px`);
    root.style.setProperty("--theme-cy", `${cy}px`);
    root.style.setProperty("--theme-r", `${radius}px`);
    root.dataset.themeAnim = "1";

    const vt = document.startViewTransition(() => commit(next));
    vt.finished.finally(() => {
      delete root.dataset.themeAnim;
    });
  });

  applyIcons();

  /* 跟随系统主题（未手动设置时） */
  const media = matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", (e) => {
    let stored = null;
    try {
      stored = localStorage.getItem("theme");
    } catch (err) {
      /* ignore */
    }
    if (!stored) {
      root.classList.toggle("dark", e.matches);
      applyIcons();
    }
  });
})();