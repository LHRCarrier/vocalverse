/**
 * SingMiniPlayer（唱吧悬浮试听播放条 · 2026-09-23 用户原型）组件测试。
 *
 * 契约：转盘=封面（播放时转动 `is-on`）、播放/暂停图标随 `playing` 切换、
 * 红心=收藏（`favorited` 真源透传）、队列=选曲、整条可点开跟唱面板；纯展示组件不持状态。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SingMiniPlayer from '@/components/sing/SingMiniPlayer.vue'
import type { SongSummary } from '@/api/sing'

const song = (over: Partial<SongSummary> = {}): SongSummary => ({
  id: 9,
  title: 'NIGHT DANCER',
  artist: 'imase · NIGHT DANCER',
  album: 'NIGHT DANCER',
  level: 1,
  duration_s: 211,
  pitch_ref_status: 'ready',
  expected_lines: 6,
  favorited: false,
  cover_url: '/api/v1/songs/covers/local-demo-06.jpg',
  ...over,
})

describe('SingMiniPlayer', () => {
  it('封面渲染 + 播放态转盘转动（is-on）；暂停态不转', () => {
    const playing = mount(SingMiniPlayer, { props: { song: song(), playing: true } })
    expect(playing.get('.m-sing-mini__disc img').attributes('src')).toContain('local-demo-06.jpg')
    expect(playing.get('.m-sing-mini__disc').classes()).toContain('is-on')
    const paused = mount(SingMiniPlayer, { props: { song: song(), playing: false } })
    expect(paused.get('.m-sing-mini__disc').classes()).not.toContain('is-on')
  })

  it('无封面/图裂 → 转盘退音符图标（不留破图）', async () => {
    const noCover = mount(SingMiniPlayer, { props: { song: song({ cover_url: null }), playing: false } })
    expect(noCover.find('.m-sing-mini__disc img').exists()).toBe(false)
    expect(noCover.find('.m-sing-mini__disc svg').exists()).toBe(true)
    const broken = mount(SingMiniPlayer, { props: { song: song(), playing: false } })
    await broken.get('.m-sing-mini__disc img').trigger('error')
    expect(broken.find('.m-sing-mini__disc img').exists()).toBe(false)
    expect(broken.find('.m-sing-mini__disc svg').exists()).toBe(true)
  })

  it('播放/暂停键图标随 playing 切换，点击 emit toggle', async () => {
    const playing = mount(SingMiniPlayer, { props: { song: song(), playing: true } })
    expect(playing.find('button[aria-label="暂停试听"]').exists()).toBe(true)
    await playing.get('button[aria-label="暂停试听"]').trigger('click')
    expect(playing.emitted('toggle')).toHaveLength(1)

    const paused = mount(SingMiniPlayer, { props: { song: song(), playing: false } })
    expect(paused.find('button[aria-label="播放试听"]').exists()).toBe(true)
  })

  it('副文 = 歌手 + 状态文案（正在试听 / 点击试听）', () => {
    expect(mount(SingMiniPlayer, { props: { song: song(), playing: true } }).get('.m-sing-mini__sub').text()).toBe(
      'imase · 正在试听参考旋律',
    )
    expect(mount(SingMiniPlayer, { props: { song: song(), playing: false } }).get('.m-sing-mini__sub').text()).toBe(
      'imase · 点击试听参考旋律',
    )
  })

  it('红心透传收藏态并 emit favorite；队列键 emit queue；点标题/转盘 emit open(id)', async () => {
    const w = mount(SingMiniPlayer, { props: { song: song({ favorited: true }), playing: false } })
    const fav = w.get('button[aria-label="取消收藏"]')
    expect(fav.classes()).toContain('is-fav')
    await fav.trigger('click')
    expect(w.emitted('favorite')?.[0]).toEqual([song({ favorited: true })])

    await w.get('button[aria-label="选曲"]').trigger('click')
    expect(w.emitted('queue')).toHaveLength(1)

    await w.get('.m-sing-mini__info').trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([9])
  })

  it('样式契约：转盘 8s 线性旋转 + 动效分级 off 停转（读源文件，改回即红）', () => {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { readFileSync } = require('node:fs') as typeof import('node:fs')
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const { resolve } = require('node:path') as typeof import('node:path')
    const src = readFileSync(resolve(process.cwd(), 'src/components/sing/SingMiniPlayer.vue'), 'utf-8')
    const style = src.slice(src.indexOf('<style scoped>'))
    expect(style).toContain('@keyframes m-sing-disc')
    const disc = style.slice(style.indexOf('.m-sing-mini__disc {'), style.indexOf('.m-sing-mini__disc.is-on'))
    expect(disc).toContain('animation: m-sing-disc 8s linear infinite')
    expect(disc).toContain('animation-play-state: paused') // 未播放不转
    expect(style).toContain("html[data-motion='off'] .m-sing-mini__disc")
    expect(style).toContain('animation: none')
  })
})
