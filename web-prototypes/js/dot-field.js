/* ============================================================
   DotField · 页面底层的点阵纹理（canvas 版）
   ------------------------------------------------------------
   在每个点的位置上算一次分形噪声（fbm），用噪声决定这个点
   "出不出、多大、多实"，于是点自然聚成团、团与团之间留空 ——
   就是参考图里那种点阵云，而不是一张均匀网格。

   与项目其余部分的三条对齐：
     1. 网格 26px：与卡片插画 .pca 的 26 单位点阵同源，整站的"点"
        是同一套密度；
     2. 颜色不写死：读 CSS 变量 --dot-rgb / --dot-max，浅色深灰点、
        深色白点，换主题只需重绘一次（见下面的 MutationObserver）；
     3. 静态图层：只在 resize / 换主题时重绘，不参与滚动与动画，
        没有逐帧开销。

   想调疏密/强弱，改下面的 CELL、NOISE_SCALE 和 css 里的 --dot-max；
   想换一张"云图"，换 SEED 即可。
   ============================================================ */
(() => {
  'use strict';

  const CELL = 26; // 点距（px），与 .pca 卡片的点阵同源
  const NOISE_SCALE = 430; // 噪声特征尺寸：越大团块越大
  const DOT_MIN = 1; // 点的最小半径
  const DOT_MAX = 2.1; // 点的最大半径
  /* 噪声阈值：低于它的位置完全不出点 —— 这个值决定"空"的比例，是
     "点云"与"方格纸"的分界。实测本噪声中位数 0.52（分布 0.11~0.86），
     取 0.34 时出点率 79%，看着就是一张均匀网格；取 0.52 时出点率 49%，
     点才会聚成团、团之间留白。 */
  const CUT = 0.52;
  const GAMMA = 0.6; // 提亮中间调，让团心更实、团边更虚
  const SEED = 7;

  /* ---------- 值噪声 ---------- */
  const hash2 = (x, y, seed) => {
    let h = Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263) ^ Math.imul(seed | 0, 1274126177);
    h = Math.imul(h ^ (h >>> 13), 1274126177);
    return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
  };

  const valueNoise = (x, y, seed) => {
    const xi = Math.floor(x);
    const yi = Math.floor(y);
    const xf = x - xi;
    const yf = y - yi;
    const u = xf * xf * (3 - 2 * xf);
    const v = yf * yf * (3 - 2 * yf);
    const a = hash2(xi, yi, seed);
    const b = hash2(xi + 1, yi, seed);
    const c = hash2(xi, yi + 1, seed);
    const d = hash2(xi + 1, yi + 1, seed);
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v;
  };

  const fbm = (x, y, seed) => {
    let sum = 0;
    let amp = 0.5;
    let freq = 1;
    let norm = 0;
    for (let o = 0; o < 3; o++) {
      sum += amp * valueNoise(x * freq, y * freq, seed + o * 17);
      norm += amp;
      freq *= 2;
      amp *= 0.5;
    }
    return sum / norm;
  };

  /* ---------- 主题色 ---------- */
  const readVar = (name, fallback) => {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  };

  /* ---------- 绘制 ---------- */
  const canvas = document.createElement('canvas');
  canvas.className = 'dot-field';
  canvas.setAttribute('aria-hidden', 'true');

  let ctx = null;
  let raf = 0;

  const draw = () => {
    raf = 0;

    const w = window.innerWidth;
    const h = window.innerHeight;
    if (w < 2 || h < 2) return;

    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    ctx.fillStyle = 'rgb(' + readVar('--dot-rgb', '17, 17, 17') + ')';
    const maxAlpha = parseFloat(readVar('--dot-max', '0.2')) || 0.2;

    // 视口边缘略强、中心略弱：中间是正文，让它更安静一点
    const cx = w / 2;
    const cy = h / 2;
    const norm = Math.hypot(cx, cy) || 1;

    for (let y = CELL / 2; y < h + CELL; y += CELL) {
      for (let x = CELL / 2; x < w + CELL; x += CELL) {
        let n = fbm(x / NOISE_SCALE, y / NOISE_SCALE, SEED);

        // 阈值切掉"空地" → 提亮中间调 → 平滑，把噪声压成
        // "有团有空、团心实团边虚"的分布，而不是一片灰
        n = (n - CUT) / (1 - CUT);
        if (n <= 0) continue;
        if (n > 1) n = 1;
        n = Math.pow(n, GAMMA);
        n = n * n * (3 - 2 * n);

        const edge = 0.62 + 0.38 * (Math.hypot(x - cx, y - cy) / norm);
        const alpha = n * maxAlpha * edge;
        if (alpha < 0.006) continue;

        ctx.globalAlpha = alpha;
        ctx.beginPath();
        ctx.arc(x, y, DOT_MIN + n * (DOT_MAX - DOT_MIN), 0, Math.PI * 2);
        ctx.fill();
      }
    }

    ctx.globalAlpha = 1;
  };

  const schedule = () => {
    if (!raf) raf = requestAnimationFrame(draw);
  };

  const start = () => {
    ctx = canvas.getContext('2d');
    if (!ctx) return;

    document.body.appendChild(canvas);
    schedule();

    window.addEventListener('resize', schedule, { passive: true });
    window.addEventListener('orientationchange', schedule, { passive: true });

    // theme.js 切主题时改的是 <html> 的 class —— 变量变了就重绘一次
    new MutationObserver(schedule).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['class'],
    });
  };

  if (document.body) start();
  else document.addEventListener('DOMContentLoaded', start);
})();
