/**
 * 社区媒体宫格测试（components/mobile/MobileMediaGrid）。
 *
 * 2026-09-23 回归：视频封面的**播放钮跑到右缘只剩半个**——`.u-media` 是 flex 居中容器，
 * 而 `.u-media__play` 是普通 flex 子项：封面图 `width:100%`（替换元素 `min-width:auto`
 * 不可收缩）占满整行后，52px 圆钮被挤出容器、`overflow:hidden` 裁掉一半。
 * 修复 = 播放钮改绝对定位居中（不参与 flex 排布）。样式契约用例**修复前必失败**。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import MobileMediaGrid from '@/components/mobile/MobileMediaGrid.vue'
import type { NormalizedMedia } from '@/types/community'

const video: NormalizedMedia = {
  kind: 'video',
  items: [],
  coverUrl: '/api/v1/media/abc',
  durationS: 56,
}

describe('MobileMediaGrid · 视频封面', () => {
  it('渲染封面 + 播放钮 + 时长角标；点击 emit play', async () => {
    const w = mount(MobileMediaGrid, { props: { media: video } })
    expect(w.find('.u-media--video').exists()).toBe(true)
    expect(w.find('.u-media__img').exists()).toBe(true)
    expect(w.find('.u-media__play').exists()).toBe(true)
    expect(w.find('.u-media__dur').text()).toBe('0:56')
    await w.find('.u-media--video').trigger('click')
    expect(w.emitted('play')).toHaveLength(1)
  })

  it('样式契约：播放钮必须绝对定位居中（不得退回 flex 子项——修复前被封面图挤到右缘裁半）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const css = readFileSync(resolve(process.cwd(), 'src/styles/mobile-uic.css'), 'utf-8')
    const start = css.indexOf('.u-media__play {')
    const block = css.slice(start, css.indexOf('}', start))
    expect(start).toBeGreaterThan(-1)
    expect(block).toContain('position: absolute')
    expect(block).toContain('top: 50%')
    expect(block).toContain('left: 50%')
    expect(block).toContain('translate(-50%, -50%)')
  })
})
