/* WebGL 肖像 morph：复刻原版 PortraitMorph（fBM 噪声扭曲 + 边缘擦除） */
(() => {
  const VERTEX_SHADER = `
attribute vec2 position;
varying vec2 vUv;
void main() {
  vUv = position * 0.5 + 0.5;
  gl_Position = vec4(position, 0.0, 1.0);
}
`;

  const FRAGMENT_SHADER = `
precision highp float;

uniform sampler2D uTexA;
uniform sampler2D uTexB;
uniform float uProgress;
uniform float uTime;
uniform vec2 uResolution;
uniform vec2 uImageSize;
uniform vec2 uOrigin;
uniform vec2 uDirection;

varying vec2 vUv;

vec2 coverUv(vec2 uv) {
  vec2 ratio = vec2(
    min((uResolution.x / uResolution.y) / (uImageSize.x / uImageSize.y), 1.0),
    min((uResolution.y / uResolution.x) / (uImageSize.y / uImageSize.x), 1.0)
  );
  return vec2(
    uv.x * ratio.x + (1.0 - ratio.x) * 0.5,
    uv.y * ratio.y + (1.0 - ratio.y) * 0.5
  );
}

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float noise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash(i);
  float b = hash(i + vec2(1.0, 0.0));
  float c = hash(i + vec2(0.0, 1.0));
  float d = hash(i + vec2(1.0, 1.0));
  return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += a * noise(p);
    p *= 2.0;
    a *= 0.5;
  }
  return v;
}

void main() {
  vec2 uv = vUv;
  vec2 baseUv = coverUv(uv);

  float p = uProgress;
  float bell = 4.0 * p * (1.0 - p);

  vec2 dir = normalize(uDirection + vec2(0.0001));
  float along = dot(uv - uOrigin, dir);
  float distGradient = (along + 1.4) / 2.8;

  float warpLow = fbm(uv * 1.8 + uTime * 0.05) - 0.5;
  float warpHi = fbm(uv * 5.5 - uTime * 0.04 + 13.0) - 0.5;
  float warp = warpLow * 0.55 + warpHi * 0.18;

  float field = distGradient + warp;

  float remapped = mix(-0.25, 1.25, p);
  float edgeWidth = 0.07;
  float mask = smoothstep(remapped - edgeWidth, remapped + edgeWidth, field);
  mask = 1.0 - mask;

  vec2 perp = vec2(-dir.y, dir.x);
  float ripplePhase = (field - remapped) * 14.0;
  float ripple = sin(ripplePhase) * 0.5 + 0.5;
  float edgeBand = 1.0 - smoothstep(0.0, edgeWidth * 1.6, abs(field - remapped));
  float pushAmount = ripple * edgeBand * 0.025 * bell;
  vec2 pushUv = uv + perp * pushAmount;
  vec2 baseUvA = coverUv(pushUv);
  vec2 baseUvB = coverUv(pushUv);

  vec4 texA = texture2D(uTexA, baseUvA);
  vec4 texB = texture2D(uTexB, baseUvB);

  vec4 color = mix(texA, texB, mask);

  float darken = edgeBand * 0.35 * bell;
  color.rgb *= 1.0 - darken;

  gl_FragColor = color;
}
`;

  function makeShader(gl, type, source) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, source);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.error("Shader compile error:", gl.getShaderInfoLog(sh));
      return null;
    }
    return sh;
  }

  function computeEdgeDirection(x, y) {
    const dxLeft = x;
    const dxRight = 1 - x;
    const dyBottom = y;
    const dyTop = 1 - y;
    const minDist = Math.min(dxLeft, dxRight, dyBottom, dyTop);
    if (minDist === dxLeft) return [1, 0];
    if (minDist === dxRight) return [-1, 0];
    if (minDist === dyBottom) return [0, 1];
    return [0, -1];
  }

  function loadImage(src) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = reject;
      img.src = src;
    });
  }

  document.querySelectorAll("[data-portrait-morph]").forEach((el) => {
    const srcA = el.dataset.srcA;
    const srcB = el.dataset.srcB;
    if (!srcA || !srcB) return;

    const fallback = el.querySelector("img");
    if (!fallback) return;

    let running = true;
    let raf = 0;

    try {
      if (!window.WebGLRenderingContext) throw new Error("no webgl");

      const canvas = document.createElement("canvas");
      canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block;";
      const gl = canvas.getContext("webgl", {
        alpha: true,
        premultipliedAlpha: false,
        antialias: true,
      });
      if (!gl) throw new Error("no context");

      const vs = makeShader(gl, gl.VERTEX_SHADER, VERTEX_SHADER);
      const fs = makeShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
      if (!vs || !fs) throw new Error("shader compile");
      const prog = gl.createProgram();
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("link");
      gl.useProgram(prog);

      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
      const posLoc = gl.getAttribLocation(prog, "position");
      gl.enableVertexAttribArray(posLoc);
      gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

      if (gl.getParameter(gl.MAX_TEXTURE_IMAGE_UNITS) < 2) throw new Error("no units");

      function makeTexture() {
        const tex = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        return tex;
      }
      const texA = makeTexture();
      const texB = makeTexture();

      const uni = {};
      ["uTexA", "uTexB", "uProgress", "uTime", "uResolution", "uImageSize", "uOrigin", "uDirection"].forEach(
        (n) => (uni[n] = gl.getUniformLocation(prog, n))
      );

      const imageSize = [1, 1];
      const origin = [0.5, 0.5];
      const direction = [1, 0];
      let progress = 0;
      let hover = false;

      const resize = () => {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = Math.max(1, el.clientWidth);
        const h = Math.max(1, el.clientHeight);
        canvas.width = Math.round(w * dpr);
        canvas.height = Math.round(h * dpr);
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.uniform2f(uni.uResolution, canvas.width, canvas.height);
      };
      const ro = new ResizeObserver(resize);
      ro.observe(el);
      resize();

      const setTex = (u, tex, img) => {
        gl.activeTexture(tex === texA ? gl.TEXTURE0 : gl.TEXTURE1);
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        gl.uniform1i(u, tex === texA ? 0 : 1);
      };

      let last = performance.now();
      let time = 0;

      const tick = () => {
        if (!running) return;
        const now = performance.now();
        const dt = Math.min((now - last) / 1000, 0.05);
        last = now;
        time += dt;

        const target = hover ? 1 : 0;
        const stiffness = hover ? 2.4 : 2.0;
        const k = 1 - Math.exp(-stiffness * dt);
        progress += (target - progress) * k;

        gl.uniform1f(uni.uTime, time);
        gl.uniform1f(uni.uProgress, progress);
        gl.uniform2f(uni.uOrigin, origin[0], origin[1]);
        gl.uniform2f(uni.uDirection, direction[0], direction[1]);
        gl.uniform2f(uni.uImageSize, imageSize[0], imageSize[1]);

        gl.drawArrays(gl.TRIANGLES, 0, 3);
        raf = requestAnimationFrame(tick);
      };

      const onPointerEnter = (e) => {
        const rect = el.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = 1 - (e.clientY - rect.top) / rect.height;
        origin[0] = x;
        origin[1] = y;
        const d = computeEdgeDirection(x, y);
        direction[0] = d[0];
        direction[1] = d[1];
        hover = true;
      };
      const onPointerLeave = (e) => {
        const rect = el.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = 1 - (e.clientY - rect.top) / rect.height;
        origin[0] = x;
        origin[1] = y;
        const d = computeEdgeDirection(x, y);
        direction[0] = -d[0];
        direction[1] = -d[1];
        hover = false;
      };
      el.addEventListener("pointerenter", onPointerEnter);
      el.addEventListener("pointerleave", onPointerLeave);

      Promise.all([loadImage(srcA), loadImage(srcB)])
        .then(([imgA, imgB]) => {
          if (!running) return;
          setTex(uni.uTexA, texA, imgA);
          setTex(uni.uTexB, texB, imgB);
          imageSize[0] = imgA.naturalWidth;
          imageSize[1] = imgA.naturalHeight;
          /* 加载完成：隐藏静态图，显示 WebGL canvas（morph 特效启用） */
          fallback.style.display = "none";
          el.appendChild(canvas);
          running = true;
          last = performance.now();
          raf = requestAnimationFrame(tick);
        })
        .catch(() => {
          /* 加载失败：保留静态图 */
          canvas.remove();
        });

      window.addEventListener("beforeunload", () => {
        running = false;
        cancelAnimationFrame(raf);
        ro.disconnect();
        el.removeEventListener("pointerenter", onPointerEnter);
        el.removeEventListener("pointerleave", onPointerLeave);
        gl.getExtension("WEBGL_lose_context")?.loseContext();
        if (canvas.parentNode === el) el.removeChild(canvas);
      });
    } catch (err) {
      /* WebGL 不可用时退化为静态图片 */
      console.warn("PortraitMorph fallback to static image:", err);
    }
  });
})();