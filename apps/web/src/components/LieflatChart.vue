<script setup lang="ts">
/**
 * LieflatChart · 渲染单文件 HTML 图表/报告（lieflat-charts 交付物预览用）。
 *
 * 为什么用 sandbox iframe 而不是解析/重写：
 * - 交付物是"自成一体"的文档（内联 <style>/<script>、滚动 reveal 动画），
 *   iframe 天然隔离样式与脚本，不污染应用全局样式，也不被应用样式污染；
 * - sandbox="allow-scripts"（不含 allow-same-origin）→ 不透明源：脚本可跑，
 *   但拿不到父页面的 origin/storage/cookie（演示 HTML 视为不可信输入）；
 * - 高度自适应：注入桥接脚本，内容尺寸变化后 postMessage 回传高度。
 *
 * 局限（预览已知）：模板自带的"滚入视野触发动画"在整高 iframe 内会提前触发
 * （iframe 视口 = 内容大小），如需要精确的滚入时序再改分帧渲染。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

let seq = 0

const props = withDefaults(
  defineProps<{
    /** 完整的 HTML 文档字符串（lieflat 交付物：<html>…</html>） */
    html: string
    /** 桥接/加载完成前占位高度（px），收到内容高度消息后被覆盖 */
    fallbackHeight?: number
    /** 内容高度下限（px） */
    minHeight?: number
    /** iframe 无障碍标题 */
    title?: string
  }>(),
  { fallbackHeight: 480, minHeight: 120, title: 'Lieflat 图表' },
)

const emit = defineEmits<{ resize: [height: number] }>()

const uid = `lieflat-${(seq += 1)}-${Date.now().toString(36)}`
const iframe = ref<HTMLIFrameElement | null>(null)
const contentHeight = ref(props.fallbackHeight)

/**
 * 注入内容高度回传桥。注意：字符串里写关闭标签必须用反斜杠转义
 * （`<\/script>`），否则字面序列会提前切断 SFC 的 script 块；
 * `\/` 在 JS 字符串里等价于 `/`。
 */
const bridgeScript = `
<script>
(function () {
  var uid = ${JSON.stringify(uid)};
  function send() {
    var doc = document.documentElement;
    var body = document.body;
    var h = Math.max(doc ? doc.scrollHeight : 0, body ? body.scrollHeight : 0, doc ? doc.clientHeight : 0);
    parent.postMessage({ __lieflat: true, uid: uid, height: Math.ceil(h) }, '*');
  }
  function boot() { send(); }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else { boot(); }
  window.addEventListener('load', boot);
  if (document.fonts && document.fonts.ready) { document.fonts.ready.then(boot); }
  if (window.ResizeObserver) {
    new ResizeObserver(function () { send(); }).observe(document.documentElement);
  }
  window.addEventListener('resize', send);
})();
<\/script>`

/** 桥接脚本插到 </body> 前；没有 </body> 就追加到文档末尾 */
const docHtml = computed(() => {
  const raw = props.html.trim()
  if (!raw) return ''
  return /<\/body>/i.test(raw) ? raw.replace(/<\/body>/i, `${bridgeScript}</body>`) : raw + bridgeScript
})

function onMessage(event: MessageEvent) {
  if (event.source !== iframe.value?.contentWindow) return
  const data = event.data as { __lieflat?: unknown; uid?: unknown; height?: unknown } | null
  if (!data || data.__lieflat !== true || data.uid !== uid) return
  const h = Number(data.height)
  if (Number.isFinite(h) && h > 0) {
    const next = Math.max(h, props.minHeight)
    contentHeight.value = next
    emit('resize', next)
  }
}

watch(
  () => props.html,
  () => {
    contentHeight.value = props.fallbackHeight
  },
)

onMounted(() => window.addEventListener('message', onMessage))
onBeforeUnmount(() => window.removeEventListener('message', onMessage))
</script>

<template>
  <div class="lieflat-chart w-full overflow-hidden">
    <iframe
      v-if="docHtml"
      ref="iframe"
      class="block w-full border-0"
      :style="{ height: contentHeight + 'px' }"
      :srcdoc="docHtml"
      :title="title"
      sandbox="allow-scripts"
    />
    <div v-else class="flex h-[120px] items-center justify-center text-xs text-[#8F8E88]">
      暂无图表内容
    </div>
  </div>
</template>
