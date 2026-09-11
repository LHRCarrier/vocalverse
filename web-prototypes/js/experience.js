/* Experience 折叠列表：高度动画（测量版）+ 底部模糊遮罩 + Show more/less
   旧版在 176px 与 auto 之间切换 height —— auto 不可插值，过渡不生效，
   展开/收起是瞬时的（僵硬）。新版：
   1) 先测量完整展开高度（fullHeight）；
   2) 展开：176px → fullHeight 触发过渡，结束后解除固定高度恢复响应式；
   3) 收起：先钉住当前实际高度，再回落到 176px（必须用 px 才能过渡）；
   4) 底部遮罩由 display 硬切改为 opacity 淡入淡出。 */
(() => {
  const shell = document.querySelector("[data-experience]");
  if (!shell) return;

  const inner = shell.querySelector("[data-experience-inner]");
  const toggle = shell.querySelector("[data-experience-toggle]");
  const chevron = shell.querySelector("[data-experience-chevron]");
  const fade = shell.querySelector(".experience-fade");
  const COLLAPSED_HEIGHT = 176; /* 2.5 行的折叠高度 */

  let open = false;
  let fullHeight = 0;

  // 测量完整展开高度；内容（字体/图片/响应式）变化时重新测量
  const measure = () => {
    const prev = inner.style.height;
    inner.style.height = "auto";
    fullHeight = inner.scrollHeight;
    inner.style.height = prev;
  };

  const openPanel = () => {
    inner.style.height = `${fullHeight}px`;
    const done = (e) => {
      if (e.target !== inner) return; // 只响应自身 height 过渡结束
      inner.removeEventListener("transitionend", done);
      if (open) inner.style.height = "auto"; // 到位后解除固定高度，保持响应式
    };
    inner.addEventListener("transitionend", done);
  };

  const closePanel = () => {
    // 先钉住当前实际高度，强制回流后再回落到折叠高度
    inner.style.height = `${inner.scrollHeight}px`;
    void inner.offsetHeight;
    inner.style.height = `${COLLAPSED_HEIGHT}px`;
  };

  measure();
  window.addEventListener("load", measure);
  window.addEventListener("resize", measure);

  toggle.addEventListener("click", () => {
    open = !open;
    if (open) openPanel();
    else closePanel();
    chevron.style.transform = open ? "rotate(180deg)" : "rotate(0deg)";
    toggle.setAttribute("aria-expanded", String(open));
    shell.classList.toggle("open", open);
    toggle.childNodes[0].nodeValue = open ? "Show less" : "Show 5 more";
    fade.style.opacity = open ? "0" : "1";
  });
})();
