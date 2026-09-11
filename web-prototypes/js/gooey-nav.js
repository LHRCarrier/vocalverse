/* ===== GooeyNav · React Bits（JavaScript + CSS 变体）原生移植 =====
   上游：reactbits.dev 的 GooeyNav（React + JSX，样式见 css/gooey-nav.css）。
   本站是无构建的静态原型（没有 React、没有打包器），故把 JSX 版本逐行移植成
   原生实现：粒子算法、参数默认值、动画时序（30ms 建粒子 / requestAnimationFrame
   加 .active / t 毫秒后回收）都与上游一致：
     items / animationTime / particleCount / particleDistances / particleR /
     timeVariance / colors / initialActiveIndex

   接入范围：除首页（index.html）外的全部页面。
   首页是另一套 .nav__nav 导航，选择器不会命中，行为完全不受影响。

   用法：
     1) <head> 里：<link rel="stylesheet" href="css/gooey-nav.css" />
     2) 页面底部：<script src="js/gooey-nav.js" defer></script>
     3) 结构不用改：本文件自动挂到页面上已有的 <nav class="site-nav">。
   按需覆盖参数（可选，写在 nav 标签上）：
     <nav class="site-nav"
          data-gooey-animation-time="600"
          data-gooey-particle-count="15"
          data-gooey-particle-distances="90,10"
          data-gooey-particle-r="100"
          data-gooey-time-variance="300"
          data-gooey-colors="1,2,3,1,2,3,1,4"
          data-gooey-initial-index="0"
          data-gooey-burst-on-show="off">
     data-gooey-nav="off" 可整页关闭（本文件仍会加载，但不做任何事）。
   也可以在任意导航上手动挂载：
     window.GooeyNav.mount(navElement, { particleCount: 22 });

   —— 与上游实现的差异（逐条给出原因）——
   1) items 不由 JS 渲染：链接文字与 href 本来就在 HTML 里（8 个页面的
      <ul><li><a> 结构完全一致），直接沿用现成 DOM，避免同一份导航写两处。
      label / href 仍可从实例的 items 读到。
   2) initialActiveIndex 默认"自动"：取 [aria-current="page"] 的下标，取不到才
      退回 0 —— 多页站点每页都要高亮自己，写死 0 会让每页都指错；显式传数字
      则以传入值为准（与上游一致）。
   3) 挂载点是外层 <nav class="site-nav">，不是 .gooey-nav-container：
      .site-nav__bar 上有 overflow-x:auto，气泡挂在里面会被裁掉。
   4) 静止态药丸：上游靠 li.active::after 做静态底，.effect.filter::after 只在
      点击时播一次；这里改成挂载时直接给滤镜层加 .active（加载时播一次 0→1 的
      展开，此时导航通常还隐藏着，用户看到的是"已经在位"的结果），静止态与
      过渡态共用同一层，省掉两层同色药丸的重叠。
   5) 键盘：Enter 交给 <a> 原生跳转（本站是真链接，上游 href="#" 才无所谓）；
      Space 走 a.click()，与 Enter 结果一致（上游 Space 只切换高亮、不跳转，
      在真链接上会让人以为"选中了却没进页面"）。
   6) prefers-reduced-motion 下不生成气泡（本站全局把动画时长压到 0.01ms，
      生成了也是瞬间消失），药丸依旧直接落位。
   7) burstOnShow（新增开关，默认开）：非首页导航是"悬浮才滑入"的，加载那一刻
      的动画用户根本看不到；而点击链接又会立刻跳转，气泡刚开始就被新页面打断。
      所以把一次完整的气泡动画挪到"导航第一次真正露面"时播放（悬浮滑入 /
      键盘聚焦 / 触摸端加载即显），每次加载只播一次。
   8) 滤镜层比激活项外扩 --gooey-field：底布要大于药丸，药丸的边才不会被
      blur(7px) 糊成光晕。外扩量按导航条内边距夹取后写回同名 CSS 变量，
      CSS（药丸内缩量）与 JS（滤镜层外扩量）共用同一个值，详见 syncField()。
   9) 静止态药丸用 .is-settled 直接落位、不播 0→1 的生长：挂载（含站内跳转
      到达）时激活项的字会被立刻换成"药丸反色"，若药丸还在从 0 长大，
      浅色主题下就是白字压白底、深色主题下黑字压黑底，头 200ms 看不清。
      生长形变只在第一次点击切换时启用（handleClick 摘掉 .is-settled）。
*/
(() => {
  "use strict";

  /* 与上游 props 一一对应的默认值 */
  const DEFAULTS = {
    animationTime: 600,
    particleCount: 15,
    particleDistances: [90, 10],
    particleR: 100,
    timeVariance: 300,
    colors: [1, 2, 3, 1, 2, 3, 1, 4],
    initialActiveIndex: null, // null = 自动（见差异 2）
    burstOnShow: true         // 见差异 7
  };

  const ACTIVE = "active";
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* ===== 上游原样保留的三个数学函数 ===== */
  const noise = (n = 1) => n / 2 - Math.random() * n;

  const getXY = (distance, pointIndex, totalPoints) => {
    const angle = ((360 + noise(8)) / totalPoints) * pointIndex * (Math.PI / 180);
    return [distance * Math.cos(angle), distance * Math.sin(angle)];
  };

  const toNumber = (value, fallback) => {
    const n = Number.parseFloat(value);
    return Number.isFinite(n) ? n : fallback;
  };

  const toNumberList = (value) =>
    String(value)
      .split(/[,\s]+/)
      .map((part) => Number.parseFloat(part))
      .filter((n) => Number.isFinite(n));

  /* 标签上的 data-gooey-* 覆盖（可选） */
  const readDataset = (nav) => {
    const d = nav.dataset;
    const opts = {};
    if (d.gooeyAnimationTime) opts.animationTime = toNumber(d.gooeyAnimationTime, DEFAULTS.animationTime);
    if (d.gooeyParticleCount) opts.particleCount = Math.max(0, Math.round(toNumber(d.gooeyParticleCount, DEFAULTS.particleCount)));
    if (d.gooeyParticleR) opts.particleR = toNumber(d.gooeyParticleR, DEFAULTS.particleR);
    if (d.gooeyTimeVariance) opts.timeVariance = toNumber(d.gooeyTimeVariance, DEFAULTS.timeVariance);
    if (d.gooeyParticleDistances) {
      const pair = toNumberList(d.gooeyParticleDistances);
      if (pair.length >= 2) opts.particleDistances = [pair[0], pair[1]];
    }
    if (d.gooeyColors) {
      const list = toNumberList(d.gooeyColors);
      if (list.length) opts.colors = list.map((n) => Math.round(n));
    }
    if (d.gooeyInitialIndex) opts.initialActiveIndex = Math.round(toNumber(d.gooeyInitialIndex, 0));
    if (d.gooeyBurstOnShow) opts.burstOnShow = d.gooeyBurstOnShow !== "off";
    return opts;
  };

  /* ===== 挂载 ===== */
  const mount = (nav, options) => {
    if (!nav || nav.dataset.gooeyNav === "on") return null;

    const list = nav.querySelector("ul");
    if (!list) return null;

    /* 差异 1：沿用现成的 <li><a> 作为 items */
    const entries = Array.prototype.slice
      .call(list.children)
      .filter((el) => el.tagName === "LI")
      .map((li) => ({ li, a: li.querySelector("a") }))
      .filter((entry) => entry.a);
    if (!entries.length) return null;

    const opts = Object.assign({}, DEFAULTS, readDataset(nav), options || {});
    const bar = nav.querySelector(".site-nav__bar") || list.parentElement;
    const filter = document.createElement("span");
    const text = document.createElement("span");

    let activeIndex = 0;
    let disposed = false;

    /* —— 计时器 / 监听器登记，destroy() 时可完整回收 —— */
    const timers = new Set();
    const listeners = [];
    const schedule = (fn, ms) => {
      const id = window.setTimeout(() => {
        timers.delete(id);
        fn();
      }, ms);
      timers.add(id);
      return id;
    };
    const on = (target, type, handler, opts2) => {
      target.addEventListener(type, handler, opts2);
      listeners.push([target, type, handler, opts2]);
    };

    /* —— 两个效果层：滤镜层（底布 + 药丸 + 气泡）与文字镜像层 ——
       挂在 nav 上而不是 .site-nav__bar 里（差异 3），并标 aria-hidden：
       镜像层内容是激活项文字的副本，不能让读屏软件读第二遍。 */
    filter.className = "effect filter";
    filter.setAttribute("aria-hidden", "true");
    text.className = "effect text";
    text.setAttribute("aria-hidden", "true");
    nav.appendChild(filter);
    nav.appendChild(text);

    nav.classList.add("gooey-nav");
    nav.dataset.gooeyNav = "on";

    /* —— 上游原样：造单个气团的参数 —— */
    const createParticle = (i, t, d, r) => {
      const rotate = noise(r / 10);
      return {
        start: getXY(d[0], opts.particleCount - i, opts.particleCount),
        end: getXY(d[1] + noise(7), opts.particleCount - i, opts.particleCount),
        time: t,
        scale: 1 + noise(0.2),
        color: opts.colors[Math.floor(Math.random() * opts.colors.length)],
        rotate: rotate > 0 ? (rotate + r / 20) * 10 : (rotate - r / 20) * 10
      };
    };

    /* —— 上游 makeParticles：先撤掉药丸，再逐个投递气泡，落位后重放药丸 —— */
    const makeParticles = (element) => {
      element.classList.remove(ACTIVE);

      if (motionQuery.matches) {
        /* 差异 6：不生成气泡，但药丸仍要在下一帧落位 */
        requestAnimationFrame(() => {
          if (!disposed) element.classList.add(ACTIVE);
        });
        return;
      }

      const d = opts.particleDistances;
      const r = opts.particleR;
      const bubbleTime = opts.animationTime * 2 + opts.timeVariance;
      element.style.setProperty("--time", `${bubbleTime}ms`);

      for (let i = 0; i < opts.particleCount; i++) {
        const t = opts.animationTime * 2 + noise(opts.timeVariance * 2);
        const p = createParticle(i, t, d, r);

        schedule(() => {
          if (disposed) return;
          const particle = document.createElement("span");
          const point = document.createElement("span");

          particle.className = "particle";
          particle.style.setProperty("--start-x", `${p.start[0]}px`);
          particle.style.setProperty("--start-y", `${p.start[1]}px`);
          particle.style.setProperty("--end-x", `${p.end[0]}px`);
          particle.style.setProperty("--end-y", `${p.end[1]}px`);
          particle.style.setProperty("--time", `${p.time}ms`);
          particle.style.setProperty("--scale", `${p.scale}`);
          particle.style.setProperty("--color", `var(--color-${p.color}, var(--gooey-ink))`);
          particle.style.setProperty("--rotate", `${p.rotate}deg`);

          point.className = "point";
          particle.appendChild(point);
          element.appendChild(particle);

          requestAnimationFrame(() => {
            if (!disposed) element.classList.add(ACTIVE);
          });
          schedule(() => {
            try {
              element.removeChild(particle);
            } catch (err) {
              /* 已被下一轮清理掉了 */
            }
          }, t);
        }, 30);
      }
    };

    /* —— 阈值场外扩量 ——
       期望值写在 CSS 的 --gooey-field（默认 7px ≈ blur 半径），这里再按导航条
       实际内边距夹一次，夹完写回该变量：药丸的内缩量（CSS 用）与滤镜层的外扩量
       （下面 updateEffectPosition 用）因此永远相等，底布也不会透到条子外面。 */
    let field = 7;
    const syncField = () => {
      const want = toNumber(getComputedStyle(nav).getPropertyValue("--gooey-field"), 7);
      let limit = want;
      if (bar && bar !== nav) {
        const bs = getComputedStyle(bar);
        limit = Math.min(
          toNumber(bs.paddingTop, want),
          toNumber(bs.paddingRight, want),
          toNumber(bs.paddingBottom, want),
          toNumber(bs.paddingLeft, want)
        );
      }
      field = Math.max(0, Math.min(want, limit));
      if (nav.style.getPropertyValue("--gooey-field") !== `${field}px`) {
        nav.style.setProperty("--gooey-field", `${field}px`);
      }
    };

    /* —— 上游 updateEffectPosition：把效果层对齐到激活项，
           参照物由容器换成外层 nav（差异 3），相对量不变；
           滤镜层额外外扩 field，让底布比药丸大一圈（否则药丸的边会被 blur 糊掉）—— */
    const updateEffectPosition = (element) => {
      const hostRect = nav.getBoundingClientRect();
      const pos = element.getBoundingClientRect();
      const left = pos.x - hostRect.x;
      const top = pos.y - hostRect.y;

      Object.assign(text.style, {
        left: `${left}px`,
        top: `${top}px`,
        width: `${pos.width}px`,
        height: `${pos.height}px`
      });
      Object.assign(filter.style, {
        left: `${left - field}px`,
        top: `${top - field}px`,
        width: `${pos.width + field * 2}px`,
        height: `${pos.height + field * 2}px`
      });
      text.innerText = element.innerText;
    };

    const syncActiveLi = () => {
      entries.forEach((entry, i) => entry.li.classList.toggle(ACTIVE, i === activeIndex));
    };

    const reposition = () => updateEffectPosition(entries[activeIndex].li);

    /* —— 上游 handleClick —— */
    const handleClick = (index) => {
      if (activeIndex === index) return;

      /* 退出"静止态"：从这一次起药丸恢复生长形变（差异 9）。
         放在 reposition 之前，免得药丸先按满尺寸跳到新位置再消失。 */
      filter.classList.remove("is-settled");

      activeIndex = index;
      syncActiveLi();
      reposition();

      filter.querySelectorAll(".particle").forEach((p) => filter.removeChild(p));

      text.classList.remove(ACTIVE);
      void text.offsetWidth; /* 强制重排，让颜色过渡能重放 */
      text.classList.add(ACTIVE);

      makeParticles(filter);
    };

    /* —— 差异 2：初始激活项 —— */
    const pageIndex = entries.findIndex((entry) => entry.a.getAttribute("aria-current") === "page");
    activeIndex =
      Number.isInteger(opts.initialActiveIndex) && opts.initialActiveIndex >= 0
        ? Math.min(opts.initialActiveIndex, entries.length - 1)
        : pageIndex >= 0
          ? pageIndex
          : 0;

    /* —— 上游 useEffect：落位 + 文字层变色；差异 4：药丸也一起落位 ——
       静止态直接落位（.is-settled，见 css 说明）：不播 0→1 的生长，
       否则到达新页面时激活项的字会先变成药丸反色、而药丸还没长出来。 */
    syncField();
    syncActiveLi();
    reposition();
    filter.classList.add("is-settled");
    text.classList.add(ACTIVE);
    filter.classList.add(ACTIVE);

    /* 初始化落位完成后再放开文字换色的过渡（.is-ready）：挂载那一次换色必须
       瞬时完成，否则会先看到"字已变成药丸反色、药丸还没铺到"的中间态。 */
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (!disposed) nav.classList.add("is-ready");
      });
    });

    /* —— 上游 ResizeObserver —— */
    let ro = null;
    if (typeof ResizeObserver === "function") {
      ro = new ResizeObserver(() => {
        syncField();
        reposition();
      });
      ro.observe(nav);
    }

    /* —— 窄屏条子可横向滚动（site-nav.css），滚动时效果层跟手 —— */
    if (bar && bar !== nav) {
      let raf = 0;
      on(bar, "scroll", () => {
        if (raf) return;
        raf = requestAnimationFrame(() => {
          raf = 0;
          reposition();
        });
      }, { passive: true });
    }

    /* —— 点击 / 键盘 —— */
    entries.forEach((entry, index) => {
      on(entry.a, "click", () => handleClick(index));
      on(entry.a, "keydown", (event) => {
        /* 差异 5：只接管 Space；Enter 交给 <a> 原生跳转 */
        if (event.key === " " || event.key === "Spacebar") {
          event.preventDefault();
          entry.a.click();
        }
      });
    });

    /* —— 差异 7：导航第一次真正露面时补播一次气泡 —— */
    let revealObserver = null;
    let burstPlayed = false;
    const isOnScreen = () =>
      nav.classList.contains("nav-reveal--visible") ||
      nav.matches(":focus-within") ||
      Number.parseFloat(getComputedStyle(nav).opacity) > 0;
    const playOnce = () => {
      if (disposed || burstPlayed) return;
      burstPlayed = true;
      if (revealObserver) {
        revealObserver.disconnect();
        revealObserver = null;
      }
      makeParticles(filter);
    };

    if (opts.burstOnShow) {
      if (isOnScreen()) {
        /* 触摸端 / 未接入 nav-reveal 的页面：加载即可见 */
        playOnce();
      } else if (typeof MutationObserver === "function") {
        revealObserver = new MutationObserver(() => {
          if (isOnScreen()) playOnce();
        });
        revealObserver.observe(nav, { attributes: true, attributeFilter: ["class", "style"] });
      }
    }

    return {
      nav,
      items: entries.map((entry) => ({
        label: entry.a.textContent.trim(),
        href: entry.a.getAttribute("href")
      })),
      get activeIndex() {
        return activeIndex;
      },
      setActiveIndex(index) {
        if (!Number.isInteger(index) || index < 0 || index >= entries.length) return;
        filter.classList.remove("is-settled");
        activeIndex = index;
        syncActiveLi();
        reposition();
        text.classList.add(ACTIVE);
      },
      destroy() {
        disposed = true;
        timers.forEach((id) => clearTimeout(id));
        timers.clear();
        listeners.forEach(([target, type, handler, opts2]) => target.removeEventListener(type, handler, opts2));
        listeners.length = 0;
        if (ro) ro.disconnect();
        if (revealObserver) revealObserver.disconnect();
        filter.remove();
        text.remove();
        nav.classList.remove("gooey-nav", "is-ready");
        delete nav.dataset.gooeyNav;
        entries.forEach((entry) => entry.li.classList.remove(ACTIVE));
      }
    };
  };

  /* ===== 自动挂载：除首页外的页面都用 <nav class="site-nav"> ===== */
  const autoMount = () => {
    document
      .querySelectorAll("nav.site-nav:not([data-gooey-nav='off']), [data-gooey-nav]:not([data-gooey-nav='off'])")
      .forEach((nav) => mount(nav));
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoMount);
  } else {
    autoMount();
  }

  window.GooeyNav = { mount, autoMount, defaults: DEFAULTS };
})();
