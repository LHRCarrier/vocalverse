/* ===== 导航栏组件（单源渲染）=====
 * 所有页面共用本文件作为顶部导航栏的唯一实现来源，避免各页复制粘贴：
 * 1. 根据当前页面文件名自动高亮 `active` 链接（桌面 + 移动菜单）
 * 2. 首页自动附加 `nav-over-hero`（深色 Hero 白字方案，其余页面保持深色字）
 * 3. 内置 Dock 磁性放大类、Logo、Sign In、汉堡（ARIA）、移动菜单
 * 4. 滚动玻璃态 / 移动菜单动画 / Dock 放大逻辑共用 common.js，此处仅提供结构
 * 用法：在所有页面的 `<script src="common.js">` 之前引入本文件。
 */
(function initNavComponent() {
  // 当前页面文件名（小写；根路径视为 index）
  var path = location.pathname.split('/').pop().toLowerCase();
  var page = (path === '' || path === '/') ? 'index.html' : path;
  var isHome = page === 'index.html';

  var links = [
    ['index.html', 'Home'],
    ['practice.html', 'Practice'],
    ['sing.html', 'Sing'],
    ['recommend.html', 'Recommend'],
    ['stats.html', 'Stats'],
    ['community.html', 'Community']
  ];

  var logoHtml =
    '<a class="logo" href="index.html" aria-label="VocalVerse home">' +
    '<svg viewBox="0 0 32 32" xmlns="http://www.w3.org/2000/svg">' +
    '<g fill="#047857">' +
    '<circle cx="16" cy="6" r="3.5"></circle>' +
    '<circle cx="23.07" cy="11.07" r="3.5"></circle>' +
    '<circle cx="26" cy="16" r="3.5"></circle>' +
    '<circle cx="23.07" cy="20.93" r="3.5"></circle>' +
    '<circle cx="16" cy="26" r="3.5"></circle>' +
    '<circle cx="8.93" cy="20.93" r="3.5"></circle>' +
    '<circle cx="6" cy="16" r="3.5"></circle>' +
    '<circle cx="8.93" cy="11.07" r="3.5"></circle>' +
    '<circle cx="16" cy="16" r="3.5"></circle>' +
    '</g></svg></a>';

  // 桌面链接（带 Dock 磁性放大类）
  var desktopHtml = links.map(function (l) {
    return '<a class="nav-link dock-item' + (page === l[0] ? ' active' : '') + '" href="' + l[0] + '">' + l[1] + '</a>';
  }).join('');

  // 移动菜单链接
  var mobileHtml = links.map(function (l) {
    return '<a class="mobile-menu-link' + (page === l[0] ? ' active' : '') + '" href="' + l[0] + '">' + l[1] + '</a>';
  }).join('');

  var nav = document.createElement('nav');
  nav.className = 'navbar-wrapper' + (isHome ? ' nav-over-hero' : '');
  nav.id = 'mainNav';
  nav.setAttribute('aria-label', 'Primary');
  nav.innerHTML =
    '<div class="navbar-pill navbar-dock" id="navbar">' + logoHtml +
    '<div class="desktop-links">' + desktopHtml + '</div>' +
    '<div class="right-cluster">' +
    '<button class="btn-primary dock-item" onclick="openLogin()">Sign In' +
    '<span class="btn-primary-inner"><svg class="lucide" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg></span>' +
    '</button></div>' +
    '<button class="btn-hamburger" id="btnHamburger" aria-expanded="false" aria-controls="mobileMenu" aria-label="Toggle navigation menu" onclick="toggleMobileMenu()">' +
    '<svg class="lucide" style="width:1.5rem;height:1.5rem" viewBox="0 0 24 24"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>' +
    '</button>' +
    '<div class="mobile-menu" id="mobileMenu" aria-hidden="true">' + mobileHtml + '</div>' +
    '</div>';

  var mount = function () { document.body.insertBefore(nav, document.body.firstChild); };
  if (document.body) { mount(); }
  else { document.addEventListener('DOMContentLoaded', mount); }
})();