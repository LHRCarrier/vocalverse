/* ===== SplitText 文字动画适配（vanilla 版）=====
 * 复刻 React Bits <SplitText />（https://reactbits.dev）的 GSAP 效果：
 * 将带 data-split-text 的元素按字符拆分，进入视口时逐字从下方淡入。
 * 依赖：js/vendor/gsap.min.js + ScrollTrigger.min.js + SplitText.min.js
 * 用法：
 *   <h1 data-split-text>Title</h1>
 *   <p class="se-title-sub" data-split-text>subtitle</p>
 * 可选覆盖属性：data-split-type / data-split-delay / data-split-duration / data-split-ease
 */
(function () {
  "use strict";
  if (
    typeof gsap === "undefined" ||
    typeof ScrollTrigger === "undefined" ||
    typeof SplitText === "undefined"
  ) {
    return; // GSAP 未加载时保持原文可见，优雅降级
  }
  gsap.registerPlugin(ScrollTrigger, SplitText);

  var targets = document.querySelectorAll("[data-split-text]");
  if (!targets.length) return;

  var defaults = {
    splitType: "chars",
    delay: 50,          // 逐字间隔（ms）
    duration: 1.25,     // 每字动画时长（s）
    ease: "power3.out",
    from: { opacity: 0, y: 40 },
    to: { opacity: 1, y: 0 },
    threshold: 0.1,
    rootMargin: "-100px"
  };

  function readOpts(el) {
    var o = {};
    for (var k in defaults) o[k] = defaults[k];
    if (el.dataset.splitType) o.splitType = el.dataset.splitType;
    if (el.dataset.splitDelay) o.delay = parseFloat(el.dataset.splitDelay);
    if (el.dataset.splitDuration) o.duration = parseFloat(el.dataset.splitDuration);
    if (el.dataset.splitEase) o.ease = el.dataset.splitEase;
    return o;
  }

  // 与 React 组件一致的 ScrollTrigger start 计算：
  // start = `top ${(1 - threshold) * 100}%` + rootMargin 的正负偏移
  function calcStart(rootMargin, threshold) {
    var startPct = (1 - threshold) * 100;
    var m = /^(-?\d+(?:\.\d+)?)(px|em|rem|%)?$/.exec(rootMargin);
    var mv = m ? parseFloat(m[1]) : 0;
    var mu = m ? m[2] || "px" : "px";
    var sign = mv === 0 ? "" : mv < 0 ? "-=" + Math.abs(mv) + mu : "+=" + mv + mu;
    return "top " + startPct + "%" + sign;
  }

  function apply() {
    Array.prototype.forEach.call(targets, function (el) {
      if (!(el.textContent || "").trim()) return;
      var o = readOpts(el);

      // 与 React 组件渲染的包裹样式保持一致
      el.style.textAlign = "center";
      el.style.overflow = "hidden";
      el.style.display = "inline-block";
      el.style.whiteSpace = "normal";
      el.style.wordWrap = "break-word";
      el.style.willChange = "transform, opacity";

      if (el._rbsplitInstance) {
        try { el._rbsplitInstance.revert(); } catch (_) {}
        el._rbsplitInstance = null;
      }

      var start = calcStart(o.rootMargin, o.threshold);

      var splitInstance = new SplitText(el, {
        type: o.splitType,
        smartWrap: true,
        autoSplit: o.splitType === "lines",
        linesClass: "split-line",
        wordsClass: "split-word",
        charsClass: "split-char",
        reduceWhiteSpace: false,
        onSplit: function (self) {
          var t = null;
          if (o.splitType.indexOf("chars") !== -1 && self.chars.length) t = self.chars;
          if (!t && o.splitType.indexOf("words") !== -1 && self.words.length) t = self.words;
          if (!t && o.splitType.indexOf("lines") !== -1 && self.lines.length) t = self.lines;
          if (!t) t = self.chars || self.words || self.lines;

          return gsap.fromTo(
            t,
            Object.assign({}, o.from),
            Object.assign({}, o.to, {
              duration: o.duration,
              ease: o.ease,
              stagger: o.delay / 1000,
              scrollTrigger: {
                trigger: el,
                start: start,
                once: true,
                fastScrollEnd: true,
                anticipatePin: 0.4
              },
              onComplete: function () { el.classList.add("is-animated"); },
              willChange: "transform, opacity",
              force3D: true
            })
          );
        }
      });

      el._rbsplitInstance = splitInstance;
    });
  }

  // 等待字体加载完成再拆分，避免字形宽度/行高未定导致布局跳动
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(apply);
  } else {
    apply();
  }
})();
