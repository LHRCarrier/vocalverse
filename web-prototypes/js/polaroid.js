/* Polaroid 卡片：鼠标视差（spring 近似） */
(() => {
  const cards = document.querySelectorAll("[data-polaroid]");
  if (!cards.length) return;

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  cards.forEach((card) => {
    let tx = 0,
      ty = 0,
      cx = 0,
      cy = 0;

    card.addEventListener("pointermove", (e) => {
      const rect = card.getBoundingClientRect();
      const dx = e.clientX - (rect.left + rect.width / 2);
      const dy = e.clientY - (rect.top + rect.height / 2);
      const k = 0.25;
      const max = 18;
      tx = Math.max(-max, Math.min(max, dx * k));
      ty = Math.max(-max, Math.min(max, dy * k));
    });
    card.addEventListener("pointerleave", () => {
      tx = 0;
      ty = 0;
    });

    (function loop() {
      cx += (tx - cx) * 0.12;
      cy += (ty - cy) * 0.12;
      if (Math.abs(cx) > 0.01 || Math.abs(cy) > 0.01) {
        card.style.transform = `translate(${cx}px, ${cy}px)`;
      }
      requestAnimationFrame(loop);
    })();
  });
})();