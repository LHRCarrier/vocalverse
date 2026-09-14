/* ===== 统一页脚组件（单源渲染）=====
 * 全站页面共用本文件注入同一份页脚，避免各页复制粘贴：
 * 1. 在 body 末尾插入 .site-footer（品牌 + 联系方式 + 法律链接 + 版权）
 * 2. 配合 css/footer.css 实现响应式与粘性页脚
 * 用法：在所有页面 </body> 前引入 <script src="js/footer.js" defer></script>
 */
(function () {
  "use strict";
  if (document.querySelector(".site-footer")) return; // 已存在则跳过

  var footer = document.createElement("footer");
  footer.className = "site-footer";
  footer.setAttribute("aria-label", "Footer");
  footer.innerHTML = [
    '<div class="site-footer__inner">',
    '  <div class="site-footer__block site-footer__brand">',
    '    <span class="site-footer__logo">VocalVerse</span>',
    '    <p class="site-footer__tagline">AI English Speaking Trainer</p>',
    '  </div>',
    '  <div class="site-footer__block site-footer__contact">',
    '    <span class="site-footer__heading">Contact</span>',
    '    <a class="site-footer__link" href="mailto:hello@example.com">hello@example.com</a>',
    '    <div class="site-footer__social">',
    '      <a href="https://www.linkedin.com" target="_blank" rel="noopener noreferrer" aria-label="LinkedIn"><img src="assets/linkedin.svg" alt="" width="14" height="14" aria-hidden="true" /></a>',
    '      <a href="https://x.com" target="_blank" rel="noopener noreferrer" aria-label="X"><img src="assets/x.svg" alt="" width="14" height="14" aria-hidden="true" /></a>',
    '    </div>',
    '  </div>',
    '  <nav class="site-footer__block site-footer__legal" aria-label="Legal">',
    '    <span class="site-footer__heading">Legal</span>',
    '    <a class="site-footer__link" href="#privacy-policy">Privacy Policy</a>',
    '    <a class="site-footer__link" href="#terms-of-use">Terms of Use</a>',
    '  </nav>',
    '</div>',
    '<p class="site-footer__copy">&copy; 2026 VocalVerse &middot; AI English Speaking Trainer</p>'
  ].join("");

  (document.body || document.documentElement).appendChild(footer);
})();
