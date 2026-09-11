/* 联系按钮：hover 展开显示邮箱、点击复制 */
(() => {
  document.querySelectorAll("[data-contact-button]").forEach((btn) => {
    const email = btn.dataset.email || "";
    const labels = {
      closed: btn.querySelector('[data-contact-state="closed"]'),
      open: btn.querySelector('[data-contact-state="open"]'),
      copied: btn.querySelector('[data-contact-state="copied"]'),
    };
    let state = "closed";
    let copiedTimer = null;

    const setWidth = (px, animate) => {
      if (!animate) {
        btn.style.transition = "none";
      }
      btn.style.maxWidth = `${px}px`;
      if (!animate) {
        void btn.offsetWidth;
        btn.style.transition = "";
      }
    };

    const measureActive = (s) => {
      const el = labels[s];
      if (!el) return 120;
      return Math.round(el.getBoundingClientRect().width) + 48;
    };

    const setState = (s, animate = true) => {
      if (s === state) return;
      state = s;
      Object.keys(labels).forEach((k) => {
        labels[k].classList.toggle("active", k === s);
      });
      btn.setAttribute(
        "aria-label",
        s === "copied"
          ? "Email copied"
          : s === "open"
            ? `Copy ${email}`
            : "Show email"
      );
      setWidth(measureActive(s), animate);
    };

    btn.addEventListener("mouseenter", () => {
      setState("open");
    });
    btn.addEventListener("mouseleave", () => {
      setState("closed");
    });
    btn.addEventListener("focus", () => {
      setState("open");
    });
    btn.addEventListener("blur", () => {
      setState("closed");
    });
    btn.addEventListener("click", () => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(email).catch(() => {});
      } else {
        const ta = document.createElement("textarea");
        ta.value = email;
        ta.style.cssText = "position:fixed;opacity:0";
        document.body.appendChild(ta);
        ta.select();
        try {
          document.execCommand("copy");
        } catch (e) {
          /* ignore */
        }
        document.body.removeChild(ta);
      }
      setState("copied");
      clearTimeout(copiedTimer);
      copiedTimer = setTimeout(() => setState("closed"), 1600);
    });

    /* 初始化 */
    state = "";
    setState("closed", false);
  });
})();