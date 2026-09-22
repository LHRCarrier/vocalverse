/* ============================================================
   MagicBento · React Bits 组件（JavaScript + CSS 版）的原生移植
   ------------------------------------------------------------
   本项目是纯 HTML / CSS / JS（没有 React），所以这里把组件的六个
   行为按 1:1 的节奏搬到原生 DOM 上，作用对象是页面里已有的卡片：

     enableSpotlight   全局跟随光斑（文档级 mousemove + GSAP）—— **默认关闭**
     enableBorderGlow  描边光晕：给每张卡写 --bento-glow-x/y/intensity
     enableStars       悬停冒出的粒子星点（每张卡预热 particleCount 个模板）
     enableTilt        3D 倾斜
     enableMagnetism   光标磁吸
     clickEffect       点击涟漪

   ★ 光色不在 JS 里计算：粒子 / 涟漪 / 光斑全部是 CSS 类 + --bento-glow-rgb，
     浅色主题 = 深灰光（multiply 压暗），深色主题 = 白光（screen 提亮）。
     切换 .dark 时立刻生效，本文件不需要监听主题变化。

   与现有系统的三处让步（否则会和原有动画打架）：
     1. GSAP 只写 .project-card 自己的内联 transform；scroll-expand.js 写的是
        它外层 .fade-in 包装，feature-blocks.css 的入场动画写的是
        .fs-duo__card 包装 —— 元素不同，互不干扰。
     2. .project-card 自带 transition: transform .4s，逐帧改 transform 会被
        CSS 过渡拖成"橡皮筋"；css/magic-bento.css 已把它覆写为只过渡
        box-shadow / border-color。
     3. 悬停抬升（-4px）原本由 .project-card:hover 的 transform 提供，
        现在并进 GSAP 的 lift 选项，和倾斜/磁吸同一个 tween 出口。

   调参：在本文件之前挂 window.MagicBentoOptions = {...} 即可覆盖默认值。
   ============================================================ */
(() => {
  'use strict';

  if (!window.gsap) return;

  const gsap = window.gsap;
  const MOBILE_BREAKPOINT = 768; // 与组件一致：≤768px 视为移动端，关闭动效

  const OPT = Object.assign(
    {
      selector: '[data-bento], .project-card',
      /* 全局跟随光斑默认关闭：它是一个 800px 的 fixed 光晕，跟着光标在整个
         页面上跑，视觉上更抢眼、也更"特效"。这里只要卡片自己的光效，所以
         关掉它 —— 注意描边光晕（enableBorderGlow）不依赖它，照常工作。
         想恢复：window.MagicBentoOptions = { enableSpotlight: true } */
      enableSpotlight: false,
      enableBorderGlow: true,
      enableStars: true,
      enableTilt: true,
      enableMagnetism: true,
      clickEffect: true,
      spotlightRadius: 300, // 光斑半径（px）：proximity = 0.5r，fade = 0.75r
      particleCount: 12, // 每张卡悬停时冒出的粒子数
      tiltMax: 7, // 光标顶到角上时的最大倾角（组件原值 10，这里收一点）
      tiltRest: 3, // 刚进入卡片时的初始倾角（组件原值 5）
      lift: -4, // 悬停抬升，接手 .project-card:hover 的 translateY(-4px)
      magnetism: 0.04, // 组件原值 0.05
      tiltDuration: 0.4,
      particleStagger: 100, // 粒子逐个出场的间隔（ms）
    },
    window.MagicBentoOptions || {}
  );

  let cards = [];
  let enabled = false;

  const mqReduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  const supported = () =>
    window.innerWidth > MOBILE_BREAKPOINT && !mqReduce.matches;

  /* ------------------------------------------------------------
     1. 每张卡的状态：粒子模板 / 已生成粒子 / 定时器 / GSAP 句柄
     ------------------------------------------------------------ */
  const states = new WeakMap();

  const stateOf = (el) => {
    let s = states.get(el);
    if (!s) {
      s = { seeds: [], seedKey: '', live: [], timers: [], hovered: false, qt: null };
      states.set(el, s);
    }
    return s;
  };

  /* 倾斜 / 磁吸的快捷补间（quickTo 复用同一个 tween，比每帧新建省得多） */
  const settersOf = (el) => {
    const s = stateOf(el);
    if (!s.qt) {
      const cfg = { duration: OPT.tiltDuration, ease: 'power2.out' };
      s.qt = {
        rx: gsap.quickTo(el, 'rotateX', cfg),
        ry: gsap.quickTo(el, 'rotateY', cfg),
        x: gsap.quickTo(el, 'x', cfg),
        y: gsap.quickTo(el, 'y', cfg),
      };
      if (OPT.enableTilt) {
        // 透视写一次就够，之后旋转才有立体感；transformOrigin 取卡片中心
        gsap.set(el, { transformPerspective: 1000, transformOrigin: '50% 50%' });
      }
    }
    return s.qt;
  };

  const clearParticles = (el, fade) => {
    const s = stateOf(el);
    s.timers.forEach(clearTimeout);
    s.timers = [];
    s.live.forEach((dot) => {
      if (fade) {
        gsap.to(dot, {
          scale: 0,
          opacity: 0,
          duration: 0.3,
          ease: 'back.in(1.7)',
          onComplete: () => dot.remove(),
        });
      } else {
        gsap.killTweensOf(dot);
        dot.remove();
      }
    });
    s.live = [];
  };

  /* 粒子模板：按卡片当前尺寸预热，尺寸没变就复用（组件里的 memoizedParticles） */
  const seedParticles = (el, rect) => {
    const s = stateOf(el);
    const key = Math.round(rect.width) + 'x' + Math.round(rect.height);
    if (s.seedKey === key) return;
    s.seeds = Array.from({ length: OPT.particleCount }, () => {
      const seed = document.createElement('span');
      seed.className = 'bento-particle';
      seed.style.left = Math.random() * rect.width + 'px';
      seed.style.top = Math.random() * rect.height + 'px';
      return seed;
    });
    s.seedKey = key;
  };

  const burstParticles = (el) => {
    const s = stateOf(el);
    if (!s.hovered) return;

    const rect = el.getBoundingClientRect();
    if (rect.width < 2 || rect.height < 2) return;
    seedParticles(el, rect);

    s.seeds.forEach((seed, i) => {
      const id = setTimeout(() => {
        if (!s.hovered) return;

        const dot = seed.cloneNode(true);
        el.appendChild(dot);
        s.live.push(dot);

        gsap.fromTo(
          dot,
          { scale: 0, opacity: 0 },
          { scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.7)' }
        );
        gsap.to(dot, {
          x: (Math.random() - 0.5) * 100,
          y: (Math.random() - 0.5) * 100,
          rotation: Math.random() * 360,
          duration: 2 + Math.random() * 2,
          ease: 'none',
          repeat: -1,
          yoyo: true,
        });
        gsap.to(dot, {
          opacity: 0.3,
          duration: 1.5,
          ease: 'power2.inOut',
          repeat: -1,
          yoyo: true,
        });
      }, i * OPT.particleStagger);

      s.timers.push(id);
    });
  };

  /* ------------------------------------------------------------
     2. 单卡：倾斜 / 磁吸 / 粒子 / 涟漪
     ------------------------------------------------------------ */
  const follow = (el, e) => {
    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const s = settersOf(el);

    if (OPT.enableTilt) {
      s.rx(((y - cy) / cy) * -OPT.tiltMax);
      s.ry(((x - cx) / cx) * OPT.tiltMax);
    }
    if (OPT.enableMagnetism) {
      s.x((x - cx) * OPT.magnetism);
      s.y((y - cy) * OPT.magnetism + OPT.lift);
    } else if (OPT.enableTilt) {
      s.y(OPT.lift);
    }
  };

  const release = (el) => {
    const s = stateOf(el);
    s.hovered = false;
    clearParticles(el, true);
    if (s.qt) {
      s.qt.rx(0);
      s.qt.ry(0);
      s.qt.x(0);
      s.qt.y(0);
    }
  };

  const ripple = (el, e) => {
    if (!OPT.clickEffect) return;

    const rect = el.getBoundingClientRect();
    if (!rect.width || !rect.height) return;

    // 键盘触发的 click（e.detail === 0）没有坐标，从卡片中心扩散
    const fromCenter = e.detail === 0;
    const x = fromCenter ? rect.width / 2 : e.clientX - rect.left;
    const y = fromCenter ? rect.height / 2 : e.clientY - rect.top;
    const max = Math.max(
      Math.hypot(x, y),
      Math.hypot(x - rect.width, y),
      Math.hypot(x, y - rect.height),
      Math.hypot(x - rect.width, y - rect.height)
    );

    const dot = document.createElement('span');
    dot.className = 'bento-ripple';
    dot.style.width = max * 2 + 'px';
    dot.style.height = max * 2 + 'px';
    dot.style.left = x - max + 'px';
    dot.style.top = y - max + 'px';
    el.appendChild(dot);

    gsap.fromTo(
      dot,
      { scale: 0, opacity: 1 },
      {
        scale: 1,
        opacity: 0,
        duration: 0.8,
        ease: 'power2.out',
        onComplete: () => dot.remove(),
      }
    );
  };

  const bind = (el) => {
    if (el.dataset.bentoBound === '1') return;
    el.dataset.bentoBound = '1';

    el.addEventListener('mouseenter', (e) => {
      if (!enabled) return;
      stateOf(el).hovered = true;
      if (OPT.enableStars) burstParticles(el);
      follow(el, e);
    });

    el.addEventListener('mousemove', (e) => {
      if (!enabled) return;
      follow(el, e);
    });

    el.addEventListener('mouseleave', () => {
      if (!enabled) return;
      release(el);
    });

    el.addEventListener('click', (e) => {
      if (!enabled) return;
      ripple(el, e);
    });
  };

  /* ------------------------------------------------------------
     3. 全局跟随光斑 + 描边光晕强度
        光晕强度按卡片中心到光标的距离算（组件里的 proximity / fadeDistance），
        每张卡各自记自己的相对坐标，所以光环永远朝光标那一侧亮。
     ------------------------------------------------------------ */
  let spotlight = null;
  let spotX = null;
  let spotY = null;
  let spotO = null;
  let nextX = 0;
  let nextY = 0;
  let hasPointer = false;
  let frame = 0;

  const buildSpotlight = () => {
    spotlight = document.createElement('div');
    spotlight.className = 'bento-spotlight';
    document.body.appendChild(spotlight);
    spotX = gsap.quickTo(spotlight, 'x', { duration: 0.22, ease: 'power2.out' });
    spotY = gsap.quickTo(spotlight, 'y', { duration: 0.22, ease: 'power2.out' });
    spotO = gsap.quickTo(spotlight, 'opacity', { duration: 0.3, ease: 'power2.out' });
  };

  const hideSpotlight = () => {
    hasPointer = false;
    if (spotO) spotO(0);
    cards.forEach((card) => card.style.setProperty('--bento-glow-intensity', '0'));
  };

  const paint = () => {
    frame = 0;
    if (!enabled) return;

    if (OPT.enableSpotlight && spotlight) {
      spotX(nextX);
      spotY(nextY);
    }

    const proximity = OPT.spotlightRadius * 0.5;
    const fade = OPT.spotlightRadius * 0.75;
    const vh = window.innerHeight;

    // 先读后写：一次读完所有 rect，再统一写 CSS 变量，
    // 避免"读布局 → 写样式 → 再读布局"的重复样式重算。
    const rects = cards.map((card) => card.getBoundingClientRect());

    let min = Infinity;
    cards.forEach((card, i) => {
      const r = rects[i];
      if (!r.width || r.bottom < -160 || r.top > vh + 160) {
        card.style.setProperty('--bento-glow-intensity', '0');
        return;
      }

      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const distance = Math.max(
        0,
        Math.hypot(nextX - cx, nextY - cy) - Math.max(r.width, r.height) / 2
      );
      if (distance < min) min = distance;

      let intensity = 0;
      if (distance <= proximity) intensity = 1;
      else if (distance <= fade) intensity = (fade - distance) / (fade - proximity);

      card.style.setProperty('--bento-glow-x', (((nextX - r.left) / r.width) * 100).toFixed(2) + '%');
      card.style.setProperty('--bento-glow-y', (((nextY - r.top) / r.height) * 100).toFixed(2) + '%');
      card.style.setProperty('--bento-glow-intensity', intensity.toFixed(3));
    });

    if (OPT.enableSpotlight && spotO) {
      spotO(
        min <= proximity
          ? 0.85
          : min <= fade
            ? ((fade - min) / (fade - proximity)) * 0.85
            : 0
      );
    }
  };

  /* 一帧只算一次：mousemove 与 scroll 共用同一个 rAF 闸门 */
  const schedule = () => {
    if (!enabled || frame || !hasPointer) return;
    frame = requestAnimationFrame(paint);
  };

  const onPointerMove = (e) => {
    if (!enabled) return;
    nextX = e.clientX;
    nextY = e.clientY;
    hasPointer = true;
    schedule();
  };

  /* 页面滚动（含 Lenis 平滑滚动）时卡片在动，光晕坐标会长在旧位置上 ——
     比如 hero 卡在 scroll-expand 里横向位移时，光环会明显脱节。
     用最后一次光标位置重算一遍即可，代价是每帧 4 次 rect 读取。 */
  const onScroll = () => {
    if (!enabled) return;
    schedule();
  };

  /* ------------------------------------------------------------
     4. 开关
     ------------------------------------------------------------ */
  const hardStop = (el) => {
    const s = states.get(el);
    if (!s) return;
    s.hovered = false;
    clearParticles(el, false);
    if (s.qt) {
      gsap.killTweensOf(el);
      gsap.set(el, { clearProps: 'transform' }); // 把内联 transform 还给 CSS
      s.qt = null;
    }
  };

  const setEnabled = (next) => {
    if (next === enabled) return;
    enabled = next;

    if (enabled) {
      cards.forEach((el) => {
        el.classList.add('bento-card');
        if (OPT.enableBorderGlow) el.classList.add('bento-card--border-glow');
        el.style.setProperty('--bento-glow-radius', OPT.spotlightRadius + 'px');
        if (OPT.enableTilt) settersOf(el);
      });
      if (OPT.enableSpotlight && !spotlight) buildSpotlight();
      if (spotlight) spotlight.style.display = '';
    } else {
      cards.forEach((el) => {
        el.classList.remove('bento-card--border-glow');
        el.style.setProperty('--bento-glow-intensity', '0');
        hardStop(el);
      });
      hideSpotlight();
      if (spotlight) spotlight.style.display = 'none';
    }
  };

  /* ------------------------------------------------------------
     5. 启动
     ------------------------------------------------------------ */
  const collect = () =>
    Array.from(document.querySelectorAll(OPT.selector)).filter(
      (el) => el instanceof HTMLElement
    );

  cards = collect();
  if (!cards.length) return;
  cards.forEach(bind);

  if (OPT.enableSpotlight || OPT.enableBorderGlow) {
    document.addEventListener('mousemove', onPointerMove, { passive: true });
    window.addEventListener('scroll', onScroll, { passive: true });
    document.addEventListener('mouseleave', hideSpotlight);
    window.addEventListener('blur', hideSpotlight);
  }

  let resizeTimer = 0;
  const sync = () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => setEnabled(supported()), 120);
  };
  window.addEventListener('resize', sync, { passive: true });
  if (mqReduce.addEventListener) mqReduce.addEventListener('change', sync);

  setEnabled(supported());

  /* 供调试 / 动态插入卡片后使用 */
  window.MagicBento = {
    get enabled() {
      return enabled;
    },
    cards: () => cards,
    refresh() {
      const fresh = collect().filter((el) => !cards.includes(el));
      if (!fresh.length) return cards;
      fresh.forEach(bind);
      cards = cards.concat(fresh);
      if (enabled) {
        fresh.forEach((el) => {
          el.classList.add('bento-card');
          if (OPT.enableBorderGlow) el.classList.add('bento-card--border-glow');
          el.style.setProperty('--bento-glow-radius', OPT.spotlightRadius + 'px');
          if (OPT.enableTilt) settersOf(el);
        });
      }
      return cards;
    },
    enable: () => setEnabled(true),
    disable: () => setEnabled(false),
  };
})();
