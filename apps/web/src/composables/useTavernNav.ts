/**
 * 酒馆 · 页内四视图导航（大堂 / 酒馆跑团 / 角色卡 / 纪事，TrpgGameNav 驱动）：
 *
 * - `view` 为当前视图（默认酒馆跑团 = 游玩态）；
 * - `go(key)` 切换：回酒馆跑团时滚到正文底（回到刚才的对话），去其它视图滚到顶（新内容从头读）；
 * - 视图本身是可替换的内容区，底部导航与顶栏在所有视图常驻（docs/35 沉浸页口径）。
 */
import { nextTick, ref } from 'vue'

export type TavernNavKey = 'hall' | 'tavern' | 'card' | 'chronicle'

export interface TavernNavDeps {
  /** 回「酒馆跑团」时定位正文底部（useTavernScrollFollow.pinToBottom） */
  pinToBottom: () => void
}

export function useTavernNav(deps: TavernNavDeps) {
  const view = ref<TavernNavKey>('tavern')

  async function go(key: TavernNavKey) {
    if (key === view.value) return
    view.value = key
    await nextTick()
    if (key === 'tavern') deps.pinToBottom()
    else window.scrollTo({ top: 0, behavior: 'auto' })
  }

  return { view, go }
}
