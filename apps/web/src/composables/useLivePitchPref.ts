/**
 * 「实时音准线」显示开关（localStorage 记忆）。
 *
 * 2026-09-22：按用户视频模板，开关从 `LivePitchChart` 内部**提到面板底部按钮行**
 * （与「听参考语音」「开始跟唱」并列的小圆钮），故把偏好抽成独立 composable，
 * 由视图持有、图表只负责显示。
 *
 * 注意：本开关只管**显示**；跟唱时的音高检测仍照常运行——歌词滚动的「首帧人声锚点」
 * 依赖它（关掉曲线不应导致歌词不滚），且检测跑在 Worker 内（≈4ms/60ms）。
 */
import { ref } from 'vue'

const STORE_KEY = 'vv_sing_live_pitch'

export function useLivePitchPref() {
  const on = ref(localStorage.getItem(STORE_KEY) !== 'off')

  function toggle(next?: boolean) {
    on.value = next ?? !on.value
    localStorage.setItem(STORE_KEY, on.value ? 'on' : 'off')
  }

  return { on, toggle }
}
