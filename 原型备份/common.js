// ===== Toast 通知系统 =====
function showToast(message, type) {
  type = type || 'success';
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast ' + type;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.animation = 'toastOut .3s ease-out forwards';
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// ===== 移动端菜单（开合动画 + ARIA 状态同步） =====
function toggleMobileMenu() {
  const menu = document.getElementById('mobileMenu');
  const btn = document.getElementById('btnHamburger');
  const open = menu.classList.toggle('open');
  menu.setAttribute('aria-hidden', String(!open));
  if (btn) btn.setAttribute('aria-expanded', String(open));
}

// ===== 登录 =====
function openLogin() { document.getElementById('loginModal').classList.add('active'); }
function closeLogin() { document.getElementById('loginModal').classList.remove('active'); }
document.addEventListener('DOMContentLoaded', function () {
  const loginModal = document.getElementById('loginModal');
  if (loginModal) {
    loginModal.addEventListener('click', function (e) { if (e.target === this) closeLogin(); });
  }
});

function handleLogin() {
  const email = document.getElementById('loginEmail');
  const pass = document.getElementById('loginPassword');
  const emailVal = email ? email.value : 'user@test.com';
  closeLogin();
  showToast('Welcome back! Signed in as ' + emailVal, 'success');
}

// ===== Dock 磁性放大导航 =====
(function initDock() {
  const dock = document.getElementById('navbar');
  if (!dock) return;
  const items = Array.from(dock.querySelectorAll('.dock-item'));
  if (!items.length) return;

  // 配置：基础倍数 / 放大倍数 / 作用距离（像素）
  const PROPS = { base: 1, mag: 1.2, distance: 180 };

  // 为每个 dock-item 生成悬浮提示（来自原有文字内容）
  items.forEach(item => {
    const label = document.createElement('span');
    label.className = 'dock-label';
    label.textContent = item.textContent.trim().replace(/\s+/g, ' ');
    label.setAttribute('role', 'tooltip');
    label.setAttribute('aria-hidden', 'true'); // 内容已由链接文字朗读，避免重复
    item.appendChild(label);
  });

  // 仅在支持悬停的设备上启用磁性放大
  if (!window.matchMedia('(hover: hover)').matches) return;

  const apply = (x, active) => {
    requestAnimationFrame(() => {
      items.forEach(item => {
        if (!active) { item.style.transform = 'scale(1)'; item.classList.remove('hovered'); return; }
        const rect = item.getBoundingClientRect();
        const center = rect.left + window.scrollX + rect.width / 2;
        const t = Math.max(0, 1 - Math.abs(x - center) / PROPS.distance);
        const s = PROPS.base + (PROPS.mag - PROPS.base) * t;
        item.style.transform = 'scale(' + s.toFixed(3) + ')';
        item.classList.toggle('hovered', t > 0.85);
      });
    });
  };

  const reset = () => {
    items.forEach(item => { item.style.transform = 'scale(1)'; item.classList.remove('hovered'); });
  };

  dock.addEventListener('mousemove', e => apply(e.pageX, true));
  dock.addEventListener('mouseleave', reset);
  // 键盘聚焦时高亮
  items.forEach(item => {
    item.addEventListener('focus', () => { item.classList.add('hovered'); item.style.transform = 'scale(' + PROPS.mag + ')'; });
    item.addEventListener('blur', () => { item.classList.remove('hovered'); item.style.transform = 'scale(1)'; });
  });
})();

// ===== 导航栏滚动状态（滚动后玻璃底 + 深色字，深色 Hero 上白字） =====
(function initNavScroll() {
  const nav = document.getElementById('mainNav');
  if (!nav) return;
  const update = () => nav.classList.toggle('is-scrolled', window.scrollY > 8);
  window.addEventListener('scroll', update, { passive: true });
  update(); // 页面刷新/回退时同步初始状态
})();

// ===== 全屏视频背景组件（应用于除首页外的所有界面） =====
(function initPageBackground() {
  // 识别当前页面，首页（index.html）不启用视频背景
  const path = location.pathname.split('/').pop().toLowerCase();
  const page = (path === '' || path === '/') ? 'index.html' : path;
  if (page === 'index.html') return;

  // 页面自带媒体背景（如 ScrollExpand 图片滚动区）时，声明 no-page-bg 抑制动态视频，
  // 改为注入与滚动区同一张图的固定全屏背景：容器 fixed 恒定视口、图片 absolute 铺满，
  // 滚动到任意位置背景始终是同一条图片（浏览器缓存共享，不重复下载）。
  const suppressVideo = document.body.classList.contains('no-page-bg');

  if (suppressVideo) {
    document.body.classList.add('has-page-bg');

    // 取滚动展示区同源背景图，保证滚动前后背景视觉连续
    const root = document.querySelector('.js-scroll-expand');
    const imgSrc = root ? root.getAttribute('data-se-media-src') : '';
    if (imgSrc) {
      const wrap = document.createElement('div');
      wrap.className = 'page-bg-img';
      wrap.setAttribute('aria-hidden', 'true');

      const img = document.createElement('img');
      img.src = imgSrc;
      img.alt = '';
      img.draggable = false;

      const scrim = document.createElement('div');
      scrim.className = 'page-bg-scrim';

      wrap.appendChild(img);
      wrap.appendChild(scrim);
      document.body.insertBefore(wrap, document.body.firstChild);
    }
  } else {
    document.body.classList.add('has-page-bg');

    // 背景层：视频 + 压暗遮罩，aria-hidden 对屏幕阅读器不可见
    const wrap = document.createElement('div');
    wrap.className = 'page-bg';
    wrap.setAttribute('aria-hidden', 'true');

    const video = document.createElement('video');
    video.autoplay = true;
    video.loop = true;          // 循环播放
    video.muted = true;         // 静音
    video.playsInline = true;   // iOS 行内播放（无全屏）
    video.preload = 'metadata'; // 起步只载元数据，优化启动速度
    video.poster = 'https://images.unsplash.com/photo-1557683316-973673baf926?w=1600&q=60';

    const source = document.createElement('source');
    source.src = 'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260622_202655_a7f5aca0-2f80-4bc9-bcb5-96ac95662003.mp4';
    source.type = 'video/mp4';
    video.appendChild(source);

    const scrim = document.createElement('div');
    scrim.className = 'page-bg-scrim';

    wrap.appendChild(video);
    wrap.appendChild(scrim);
    document.body.insertBefore(wrap, document.body.firstChild);

    // 显式启动播放；若被浏览器自动播放策略拦截（如节能模式），静默降级为封面图 + 遮罩
    const attempt = video.play();
    if (attempt && attempt.catch) attempt.catch(function () {});
  }

  // 非首页顶部均为深色媒体区（有无视频都是），固定导航仍需白字，滚动后由 is-scrolled 回退深色字
  const nav = document.getElementById('mainNav');
  if (nav) nav.classList.add('nav-over-hero');
})();
