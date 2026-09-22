/**
 * SingHeroCards（唱吧双英雄卡 · 2026-09-23 用户原型）组件测试。
 *
 * 契约：卡 1 = 本周精选（featured 必渲染）、卡 2 = 我的收藏（无收藏整卡不渲染）；
 * 封面图裂/缺失退图标；点卡片 emit open(id)；卡面只讲歌曲信息（不出现练习元数据）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import SingHeroCards from '@/components/sing/SingHeroCards.vue'
import type { SongSummary } from '@/api/sing'

const song = (id: number, title: string, over: Partial<SongSummary> = {}): SongSummary => ({
  id,
  title,
  artist: 'imase · NIGHT DANCER',
  album: 'NIGHT DANCER',
  level: 1,
  duration_s: 211,
  pitch_ref_status: 'ready',
  expected_lines: 6,
  favorited: false,
  cover_url: `/api/v1/songs/covers/local-demo-0${id}.jpg`,
  ...over,
})

describe('SingHeroCards', () => {
  it('卡 1 = 本周精选（For You）；点卡 emit open(id)', async () => {
    const w = mount(SingHeroCards, {
      props: { featured: song(6, 'NIGHT DANCER'), favorite: null },
    })
    const cards = w.findAll('.m-sing-hero__card')
    expect(cards).toHaveLength(1)
    expect(cards[0].classes()).toContain('m-sing-hero__card--pink')
    expect(cards[0].text()).toContain('本周精选')
    expect(cards[0].text()).toContain('NIGHT DANCER')
    expect(cards[0].text()).toContain('imase') // 署名只取 `·` 前第一段
    expect(cards[0].text()).not.toContain('合成旋律')
    await cards[0].trigger('click')
    expect(w.emitted('open')?.[0]).toEqual([6])
  })

  it('卡 2 = 我的收藏（紫）；无收藏 → 整卡不渲染（不放假数据）', () => {
    const withFav = mount(SingHeroCards, {
      props: { featured: song(6, 'NIGHT DANCER'), favorite: song(8, 'Myra') },
    })
    const cards = withFav.findAll('.m-sing-hero__card')
    expect(cards).toHaveLength(2)
    expect(cards[1].classes()).toContain('m-sing-hero__card--purple')
    expect(cards[1].text()).toContain('Myra')

    const noFav = mount(SingHeroCards, {
      props: { featured: song(6, 'NIGHT DANCER'), favorite: null },
    })
    expect(noFav.findAll('.m-sing-hero__card')).toHaveLength(1)
  })

  it('封面图裂 → 该卡退图标（不牵连另一张）', async () => {
    const w = mount(SingHeroCards, {
      props: { featured: song(6, 'NIGHT DANCER'), favorite: song(8, 'Myra') },
    })
    await w.findAll('.m-sing-hero__cover img')[0].trigger('error')
    const covers = w.findAll('.m-sing-hero__cover')
    expect(covers[0].find('img').exists()).toBe(false)
    expect(covers[0].find('svg').exists()).toBe(true)
    expect(covers[1].find('img').exists()).toBe(true) // 另一张不受影响
  })

  it('卡面只讲歌曲信息：不出现练习元数据（句数/难度/可跟唱）', () => {
    const w = mount(SingHeroCards, {
      props: { featured: song(6, 'NIGHT DANCER'), favorite: null },
    })
    expect(w.text()).not.toContain('6 句')
    expect(w.text()).not.toContain('可跟唱')
  })
})
