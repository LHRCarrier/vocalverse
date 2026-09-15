/* 生成两套手机框展示页（表单与控件 / 浮层与状态）。
   Iphone 框与 app-screens 那张同源：几何常量、SVG 路径完全一致。 */
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;

const PHONE_W = 433, PHONE_H = 882;
const SCREEN_X = 21.25, SCREEN_Y = 19.25;
const SCREEN_W = 389.5, SCREEN_H = 843.5, SCREEN_R = 55.75;

function frame(id) {
  const paths = [
    "M2 73C2 32.6832 34.6832 0 75 0H357C397.317 0 430 32.6832 430 73V809C430 849.317 397.317 882 357 882H75C34.6832 882 2 849.317 2 809V73Z",
    "M0 171C0 170.448 0.447715 170 1 170H3V204H1C0.447715 204 0 203.552 0 203V171Z",
    "M1 234C1 233.448 1.44772 233 2 233H3.5V300H2C1.44772 300 1 299.552 1 299V234Z",
    "M1 319C1 318.448 1.44772 318 2 318H3.5V385H2C1.44772 385 1 384.552 1 384V319Z",
    "M430 279H432C432.552 279 433 279.448 433 280V384C433 384.552 432.552 385 432 385H430V279Z"
  ];
  return `
      <svg class="ip__frame" viewBox="0 0 ${PHONE_W} ${PHONE_H}" fill="none" xmlns="http://www.w3.org/2000/svg">
        <g mask="url(#punch${id})">
${paths.map((d) => `          <path class="f-body" d="${d}"/>`).join("\n")}
          <path class="f-inner" d="M6 74C6 35.3401 37.3401 4 76 4H356C394.66 4 426 35.3401 426 74V808C426 846.66 394.66 878 356 878H76C37.3401 878 6 846.66 6 808V74Z"/>
        </g>
        <path opacity="0.5" d="M174 5H258V5.5C258 6.60457 257.105 7.5 256 7.5H176C174.895 7.5 174 6.60457 174 5.5V5Z" fill="#E5E5E5"/>
        <path class="f-screen" mask="url(#punch${id})" d="M${SCREEN_X} 75C${SCREEN_X} 44.2101 46.2101 ${SCREEN_Y} 77 ${SCREEN_Y}H355C385.79 ${SCREEN_Y} 410.75 44.2101 410.75 75V807C410.75 837.79 385.79 862.75 355 862.75H77C46.2101 862.75 ${SCREEN_X} 837.79 ${SCREEN_X} 807V75Z"/>
        <path class="f-island" d="M154 48.5C154 38.2827 162.283 30 172.5 30H259.5C269.717 30 278 38.2827 278 48.5C278 58.7173 269.717 67 259.5 67H172.5C162.283 67 154 58.7173 154 48.5Z"/>
        <path class="f-island" d="M249 48.5C249 42.701 253.701 38 259.5 38C265.299 38 270 42.701 270 48.5C270 54.299 265.299 59 259.5 59C253.701 59 249 54.299 249 48.5Z"/>
        <path class="f-body" d="M254 48.5C254 45.4624 256.462 43 259.5 43C262.538 43 265 45.4624 265 48.5C265 51.5376 262.538 54 259.5 54C256.462 54 254 51.5376 254 48.5Z"/>
        <defs>
          <mask id="punch${id}" maskUnits="userSpaceOnUse">
            <rect x="0" y="0" width="${PHONE_W}" height="${PHONE_H}" fill="white"/>
            <rect x="${SCREEN_X}" y="${SCREEN_Y}" width="${SCREEN_W}" height="${SCREEN_H}" rx="${SCREEN_R}" ry="${SCREEN_R}" fill="black"/>
          </mask>
        </defs>
      </svg>`;
}

function slot(p, i) {
  return `
  <div class="slot">
    <div class="ip">
      <div class="ip__screen"><iframe src="${p.src}" scrolling="no" title="${p.title}"></iframe></div>${frame("f" + i)}
    </div>
    <div class="cap">
      <span class="idx">${i + 1}</span><h3>${p.title}</h3>
      <p>${p.desc}</p>
    </div>
  </div>`;
}

const CSS = `
  :root { --ip-body:#E5E5E5; --ip-inner:#FFFFFF; --ip-island:#F5F5F5; }
  * { margin:0; padding:0; box-sizing:border-box; }
  body { width:1499px; background:#F5F4F1;
    font-family:'Segoe UI','Microsoft YaHei UI','Microsoft YaHei',sans-serif;
    -webkit-font-smoothing:antialiased; }
  .stage { display:flex; align-items:flex-start; justify-content:center; gap:44px; padding:60px 56px 52px; }
  .slot { width:433px; }
  .ip { position:relative; display:inline-block; width:100%; vertical-align:middle;
    line-height:0; aspect-ratio:433/882; }
  .ip__screen { position:absolute; z-index:0; overflow:hidden; pointer-events:none;
    left:4.9076%; top:2.1826%; width:89.9538%; height:95.6349%;
    border-radius:14.3132% / 6.6094%; background:#F5F4F1; }
  .ip__screen > iframe { display:block; width:390px; height:844px; border:0;
    transform:scale(.998718,.999408); transform-origin:top left; }
  .ip__frame { position:absolute; inset:0; width:100%; height:100%; transform:translateZ(0); }
  .ip__frame .f-body { fill:var(--ip-body); }
  .ip__frame .f-inner { fill:var(--ip-inner); }
  .ip__frame .f-island { fill:var(--ip-island); }
  .ip__frame .f-screen { fill:var(--ip-body); stroke:var(--ip-body); stroke-width:.5; }
  .cap { margin-top:26px; text-align:center; }
  .cap .idx { display:inline-flex; align-items:center; justify-content:center;
    width:22px; height:22px; border-radius:999px; background:#1C1C1A; color:#fff;
    font-size:12px; font-weight:700; margin-right:8px; vertical-align:1px; }
  .cap h3 { display:inline; font-size:17px; font-weight:700; color:#1C1C1A; letter-spacing:-.2px; }
  .cap p { margin-top:7px; font-size:13px; line-height:1.5; color:#6F6F6A; }
`;

function page(phones) {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title>feature showcase</title>
<style>${CSS}</style>
</head>
<body>
<div class="stage">${phones.map(slot).join("\n")}
</div>
</body>
</html>
`;
}

const FORMS = [
  { src: "s1-inputs.html", title: "胶囊输入框", desc: "默认 / 填充 / 聚焦 / 禁用 四态<br>聚焦取唯一点缀色 accent 描边 + 光晕" },
  { src: "s2-buttons.html", title: "按钮五态", desc: "Primary 炭黑胶囊 · 高 48px<br>Hover / Pressed / Disabled / Loading / Focus" },
  { src: "s3-controls.html", title: "分段控件与图标按钮", desc: "分段 56px · 字号 16 · 图标 24<br>图标-only 按钮必带 Tooltip" }
];

const OVERLAYS = [
  { src: "s4-imagecard.html", title: "图片卡", desc: "大图铺满 r-24 · 文字压图底<br>hover 浮出收藏 / 分享" },
  { src: "s5-lightbox.html", title: "近黑浮层预览", desc: "rgba(28,28,26,.92) 全屏压暗<br>幽灵描边按钮 + 关闭" },
  { src: "s6-dialog.html", title: "遮罩弹窗 · Toast · 空状态", desc: "白卡 r-24 + 浅色遮罩 · 顶层 Toast<br>底层是空状态页（被遮罩压淡）" }
];

fs.writeFileSync(path.join(ROOT, "showcase-forms.html"), page(FORMS), "utf8");
fs.writeFileSync(path.join(ROOT, "showcase-overlays.html"), page(OVERLAYS), "utf8");
console.log("wrote showcase-forms.html / showcase-overlays.html");
