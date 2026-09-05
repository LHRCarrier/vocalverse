import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobilePostActions from '@/components/mobile/MobilePostActions.vue'
import MobilePostCard from '@/components/mobile/MobilePostCard.vue'

import type { CommunityPost } from '@/types/community'

function makePost(overrides: Partial<CommunityPost> = {}): CommunityPost {
  return {
    id: 1,
    author: 'Global Post',
    handle: '@globalpost',
    level: 'L4',
    time: '12 分钟前',
    domain: '新闻稿',
    kind: 'post',
    title: "'AI learning' is taking over China's classrooms",
    desc: 'Education experts say AI partners are changing how students practice speaking.',
    media: { gradient: 'linear-gradient(135deg, #16303a, #2b5566)', label: '📰 NEWS' },
    stats: { like: 1240, comment: 46, coin: 37, share: 15 },
    liked: false,
    tint: '#16303a',
    ...overrides,
  }
}

describe('MobilePostCard', () => {
  it('渲染作者 / 标题 / 摘要 / 媒体标签 / 互动计数（千位缩写 1.2k）', () => {
    const wrapper = mount(MobilePostCard, { props: { post: makePost() } })
    const text = wrapper.text()
    expect(text).toContain('Global Post')
    expect(text).toContain('@globalpost')
    expect(text).toContain('AI learning')
    expect(text).toContain('📰 NEWS')
    expect(text).toContain('1.2k') // like 1240
    expect(text).toContain('46') // comment
    expect(text).toContain('37') // coin
    expect(text).toContain('15') // share
  })

  it('点赞按钮：click 触发 toggle-like，组件透传；liked 态带 is-liked 与 aria-pressed', async () => {
    const wrapper = mount(MobilePostCard, { props: { post: makePost() } })
    const button = wrapper.get('button[aria-label="点赞"]')
    expect(button.attributes('aria-pressed')).toBe('false')

    await button.trigger('click')
    expect(wrapper.emitted('toggle-like')).toHaveLength(1)

    await wrapper.setProps({ post: makePost({ liked: true }) })
    const likedButton = wrapper.get('button.u-comm-action.is-liked')
    expect(likedButton.attributes('aria-pressed')).toBe('true')
    expect(likedButton.attributes('aria-label')).toBe('取消点赞')
  })

  it('视频帖：渲染视频封面样式与时长角标', () => {
    const wrapper = mount(MobilePostCard, {
      props: { post: makePost({ kind: 'video', duration: '6:23' }) },
    })
    expect(wrapper.find('.u-comm-media--video').exists()).toBe(true)
    expect(wrapper.text()).toContain('6:23')
  })

  it('无配图帖：不渲染媒体块', () => {
    const wrapper = mount(MobilePostCard, {
      props: { post: makePost({ media: undefined, desc: undefined }) },
    })
    expect(wrapper.find('.u-comm-media').exists()).toBe(false)
  })
})

describe('MobilePostActions', () => {
  it('非点赞项为展示（span），仅点赞为可点 button', () => {
    const wrapper = mount(MobilePostActions, {
      props: { stats: makePost().stats, liked: false },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons).toHaveLength(1)
    expect(wrapper.findAll('.u-comm-action')).toHaveLength(4)
  })
})
