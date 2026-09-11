/* ============================================================
   AeroShards · 页面接入引导（浅色 / 深色主题自适应）· 原型
   ============================================================
   - 仅在 WebGPU 可用时挂载（无 WebGPU 环境页面保持原样，渐进增强）；
   - 主题预设：浅色 #ffffff 底 + 白 shard + 黑 accent；
             深色 #000000 底 + 白 shard + 黑 accent（官方两组提示词）；
   - 监听 <html> class（theme.js 切换 dark）→ setProps 热切换，
     保持 placement/flow/material 等参数跨主题不变、仅换底色；
   - 挂载层 .aero-shards-host：fixed 全视口、z-index:-1、事件穿透；
     出错（WebGPU 初始化/渲染失败）则移除挂载层，页面回退原样。
   - 组件源 aero-shards.js 缺失或加载失败时（动态 import 被拒）静默跳过，
     不抛错、不阻断页面其余脚本。
   ============================================================ */

const LIGHT_PROPS = {
  backgroundColor: '#ffffff',
  shardColor: '#ffffff',
  accentColor: '#000000',
  placement: 'center',
  flow: 'stream',
  material: 'pearl',
  detail: 'balanced',
  effect: 'none',
  scale: 1,
  spread: 1,
  depth: 1,
  speed: 1,
  spin: 1,
  interaction: 'repel',
  density: 1.5,
  shardSize: 0.6,
  stretch: 1,
  turbulence: 1,
  glow: 1.35,
  edgeSoftness: 2,
  bloom: 1,
  grain: 0.05,
  chromaticAberration: 0.0075,
  transitionDuration: 1,
  interactionRadius: 1.5,
  interactionStrength: 0.45,
  rippleIntensity: 1.2,
  holdToGather: true
};

const DARK_PROPS = Object.assign({}, LIGHT_PROPS, {
  backgroundColor: '#000000'
});

function currentTheme() {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

function boot() {
  if (!navigator.gpu || !navigator.gpu.requestAdapter) return; /* 降级：不挂载 */

  /* 动态 import：拿不到组件就静默跳过（原静态 import 会直接 404 报错） */
  import('./aero-shards.js')
    .then((mod) => mount(mod.createAeroShards))
    .catch(() => {
      /* 组件缺失：不挂载，页面保持原样 */
    });
}

function mount(createAeroShards) {
  const host = document.createElement('div');
  host.className = 'aero-shards-host';
  document.body.appendChild(host);

  const shards = createAeroShards(host, currentTheme() === 'dark' ? DARK_PROPS : LIGHT_PROPS, {
    onError() {
      /* WebGPU 初始化/渲染失败：回退为原页面（移除背景层） */
      host.remove();
      observer.disconnect();
    }
  });

  /* 主题切换（html.dark 类变化）→ 热更新 props */
  const observer = new MutationObserver(() => {
    shards.setProps(currentTheme() === 'dark' ? DARK_PROPS : LIGHT_PROPS);
  });
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });

  window.addEventListener('beforeunload', () => shards.dispose(), { once: true });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
