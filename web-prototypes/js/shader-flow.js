/* WebGL 流动噪声背景：复刻原版 ShaderFlow（ogl -> 原生 WebGL） */
(() => {
  const VS =
    "attribute vec2 position;void main(){gl_Position=vec4(position,0.,1.);}";

  const FS = `precision highp float;
uniform vec2 uR;
uniform float uT;
uniform vec2 uV;
uniform float uS;
uniform float uTw;
uniform float uDe;
uniform float uMs;
uniform float uB;
uniform int uIt;
uniform vec3 uColorLow;
uniform vec3 uColorHigh;
uniform vec3 uBgColor;
uniform vec4 uFadeShape;

float h(vec2 p){
  return sin(p.x+sin(p.y+uT*uV.x))*sin(p.y*p.x*0.1+uT*uV.y);
}

float fadeAlpha(float d){
  float t=clamp(1.0-d,0.0,1.0);
  return t*t*(3.0-2.0*t);
}

void main(){
  vec2 frag=gl_FragCoord.xy/uR;
  vec2 p=frag-0.5;
  p.x*=uR.x/uR.y;
  p*=uS;

  float ms=uT*uMs*0.1;
  vec2 d=vec2(sin(ms),cos(ms))*0.1;
  float kt=uTw*0.01;
  float kd=1.0/uDe;

  vec2 e=vec2(0.05,0.);
  vec2 r=vec2(0.);
  for(int i=0;i<24;i++){
    if(i>=uIt)break;
    float a=h(p);
    float b=h(p+e.xy);
    float c=h(p+e.yx);
    vec2 q=vec2(b-a,c-a)*20.;
    p+=vec2(-q.y,q.x)*kt+q*kd+d;
    r=q;
  }

  float t=clamp(length(r)*0.5,0.0,1.0);
  vec3 col=mix(uColorLow,uColorHigh,t)*uB;

  vec2 ndc=vec2(frag.x,1.0-frag.y);
  float aspect=uR.x/uR.y;
  float dx=((ndc.x-uFadeShape.x)*aspect)/uFadeShape.z;
  float dy=(ndc.y-uFadeShape.y)/uFadeShape.w;
  float fa=fadeAlpha(sqrt(dx*dx+dy*dy));

  vec3 outColor=mix(uBgColor,col,fa);
  gl_FragColor=vec4(outColor,1.0);
}`;

  function parseColor(input) {
    const s = (input || "").trim();
    if (s.startsWith("#")) {
      let hex = s.slice(1);
      if (hex.length === 3) {
        hex = hex.split("").map((c) => c + c).join("");
      }
      if (hex.length !== 6) return null;
      const n = parseInt(hex, 16);
      if (Number.isNaN(n)) return null;
      return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
    }
    const m = s.match(/(\d+(?:\.\d+)?)/g);
    if (!m || m.length < 3) return null;
    return [Number(m[0]) / 255, Number(m[1]) / 255, Number(m[2]) / 255];
  }

  function readBgColor() {
    const v = getComputedStyle(document.documentElement)
      .getPropertyValue("--background")
      .trim();
    const parsed = parseColor(v);
    if (parsed) return parsed;
    const probe = document.createElement("div");
    probe.style.cssText =
      "position:absolute;width:0;height:0;background:var(--background);";
    document.body.appendChild(probe);
    const raw = getComputedStyle(probe).backgroundColor;
    document.body.removeChild(probe);
    return parseColor(raw) || [1, 1, 1];
  }

  function makeShader(gl, type, source) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, source);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.error("Shader compile error:", gl.getShaderInfoLog(sh));
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  document.querySelectorAll("[data-shader]").forEach((el) => {
    try {
      init(el);
    } catch (e) {
      console.warn("ShaderFlow init failed:", e);
    }
  });

  function init(el) {
    if (el.dataset.shaderDone) return;
    el.dataset.shaderDone = "1";

    const d = el.dataset;
    const flowSpeed = (d.flowSpeed || "0.1,0.2").split(",").map(Number);
    const iterations = parseInt(d.iterations || "14", 10);
    const scale = parseFloat(d.scale || "6");
    const brightness = parseFloat(d.brightness || "1");
    /* 噪声渐变色随主题切换：日间用明亮的蓝棕流动，夜间压暗贴近背景色 */
    const COLOR_LIGHT_LOW = [0.18, 0.2, 0.3];
    const COLOR_LIGHT_HIGH = [0.55, 0.38, 0.32];
    const COLOR_DARK_LOW = [0.06, 0.07, 0.11];
    const COLOR_DARK_HIGH = [0.24, 0.17, 0.16];
    const fadeShape = [0.5, 0.0, 1.4, 0.6];

    const canvas = document.createElement("canvas");
    canvas.style.cssText = "width:100%;height:100%;display:block;";
    el.appendChild(canvas);

    const gl =
      canvas.getContext("webgl", { antialias: false, alpha: false }) ||
      canvas.getContext("experimental-webgl", { antialias: false, alpha: false });
    if (!gl) {
      canvas.remove();
      return;
    }

    const vs = makeShader(gl, gl.VERTEX_SHADER, VS);
    const fs = makeShader(gl, gl.FRAGMENT_SHADER, FS);
    if (!vs || !fs) return;

    const prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.error("Program link failed:", gl.getProgramInfoLog(prog));
      return;
    }
    gl.useProgram(prog);

    /* fullscreen triangle */
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "position");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const uni = {};
    const setU = (name, v) => {
      const u = gl.getUniformLocation(prog, name);
      if (!u) return;
      if (typeof v === "number") gl.uniform1f(u, v);
      else if (typeof v === "boolean") gl.uniform1i(u, v ? 1 : 0);
      else if (typeof v === "number" && Number.isInteger(v)) gl.uniform1i(u, v);
      else if (v.length === 2) gl.uniform2f(u, v[0], v[1]);
      else if (v.length === 3) gl.uniform3f(u, v[0], v[1], v[2]);
      else if (v.length === 4) gl.uniform4f(u, v[0], v[1], v[2], v[3]);
    };
    ["uT", "uR", "uV", "uS", "uTw", "uDe", "uMs", "uB", "uIt", "uColorLow", "uColorHigh", "uBgColor", "uFadeShape"].forEach(
      (n) => (uni[n] = n)
    );

    setU(uni.uV, flowSpeed);
    setU(uni.uS, scale);
    setU(uni.uTw, 50);
    setU(uni.uDe, 200);
    setU(uni.uMs, 2.5);
    setU(uni.uB, brightness);
    setU(uni.uIt, iterations);
    setU(uni.uFadeShape, fadeShape);

    /* 根据当前主题设置噪声渐变色 */
    const syncColors = () => {
      const isDark = document.documentElement.classList.contains("dark");
      setU(uni.uColorLow, isDark ? COLOR_DARK_LOW : COLOR_LIGHT_LOW);
      setU(uni.uColorHigh, isDark ? COLOR_DARK_HIGH : COLOR_LIGHT_HIGH);
    };

    const resize = () => {
      const w = Math.max(1, el.clientWidth);
      const h = Math.max(1, el.clientHeight);
      const dpr = Math.min(window.devicePixelRatio || 1, 1);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      gl.viewport(0, 0, canvas.width, canvas.height);
      setU(uni.uR, [canvas.width, canvas.height]);
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    let raf = 0;
    let visible = true;
    let onScreen = true;
    const t0 = performance.now();

    const onVisibility = () => {
      visible = document.visibilityState === "visible";
    };
    document.addEventListener("visibilitychange", onVisibility);

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) onScreen = entry.isIntersecting;
      },
      { rootMargin: "100px" }
    );
    io.observe(el);

    const syncBg = () => setU(uni.uBgColor, readBgColor());
    const syncTheme = () => {
      syncBg();
      syncColors();
    };
    const mo = new MutationObserver(syncTheme);
    mo.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme", "style"],
    });
    syncTheme();

    const tick = () => {
      if (visible && onScreen) {
        setU(uni.uT, (performance.now() - t0) / 1000);
        gl.drawArrays(gl.TRIANGLES, 0, 3);
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  }
})();
