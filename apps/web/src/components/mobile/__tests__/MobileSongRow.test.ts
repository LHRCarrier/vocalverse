/**
 * MobileSongRow（唱吧歌单行）组件测试 —— 收藏按钮（2026-09-10 组长需求）。
 *
 * 断言点：
 * - 每首歌都有收藏按钮，且**行点击（去跟唱）与按钮点击（收藏）互不干扰**
 *   （两颗独立 button：原来的整行 button 内嵌按钮是无效 HTML）；
 * - 未收藏 → 点击 emit favorite + aria-pressed=false；已收藏 → aria-label 变「取消收藏」；
 * - 就绪状态徽标与右侧关键值随 pitch_ref_status 变（含未列状态回落「未就绪」）。
 */

import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobileSongRow from '@/components/mobile/MobileSongRow.vue'
import type { SongSummary } from '@/api/sing'

const song = (over: Partial<SongSummary> = {}): SongSummary => ({
  id: 7,
  title: 'Twinkle Twinkle Little Star',
  artist: 'Traditional',
  level: 1,
  pitch_ref_status: 'ready',
  expected_lines: 6,
  favorited: false,
  ...over,
})

describe('MobileSongRow（歌单行 + 收藏按钮）', () => {
  it('未收藏：aria-pressed=false，点击收藏按钮 emit favorite（不触发 open）', async () => {
    const w = mount(MobileSongRow, { props: { song: song() } })
    const fav = w.get('button.m-sing-fav')
    expect(fav.attributes('aria-pressed')).toBe('false')
    expect(fav.attributes('aria-label')).toBe('收藏 Twinkle Twinkle Little Star')
    expect(w.find('button.m-sing-fav.is-on').exists()).toBe(false)

    await fav.trigger('click')
    expect(w.emitted('favorite')?.[0]).toEqual([song()])
    expect(w.emitted('open')).toBeUndefined() // 收藏不能顺带进跟唱面板
  })

  it('已收藏：is-on + aria-pressed=true，标题/标签变「取消收藏」', () => {
    const w = mount(MobileSongRow, { props: { song: song({ favorited: true }) } })
    const fav = w.get('button.m-sing-fav')
    expect(fav.classes()).toContain('is-on')
    expect(fav.attributes('aria-pressed')).toBe('true')
    expect(fav.attributes('aria-label')).toBe('取消收藏 Twinkle Twinkle Little Star')
    expect(fav.attributes('title')).toBe('取消收藏')
  })

  it('主点击区 emit open(songId)（与收藏按钮分离）', async () => {
    const w = mount(MobileSongRow, { props: { song: song() } })
    await w.get('button.m-sing-row__hit').trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([7])
    expect(w.emitted('favorite')).toBeUndefined()
  })

  it('就绪徽标与关键值随状态变；未列状态回落「未就绪」', () => {
    const ready = mount(MobileSongRow, { props: { song: song() } })
    expect(ready.text()).toContain('可跟唱')
    expect(ready.text()).toContain('就绪')

    const building = mount(MobileSongRow, { props: { song: song({ pitch_ref_status: 'building' }) } })
    expect(building.text()).toContain('提取中')

    const missing = mount(MobileSongRow, { props: { song: song({ pitch_ref_status: 'missing' }) } })
    expect(missing.text()).toContain('未就绪')
  })
})
