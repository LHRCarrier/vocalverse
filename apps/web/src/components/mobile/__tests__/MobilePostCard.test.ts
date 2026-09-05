import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'

import MobileCommentsSheet from '@/components/mobile/MobileCommentsSheet.vue'
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
    comments: [{ author: 'Kai', text: 'Nice one.', time: '5 分钟前' }],
    liked: false,
    coined: false,
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

  it('点赞按钮：click 触发 toggle-like；liked 态带 is-liked 与 aria-pressed', async () => {
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

  it('投币 / 分享 / 评论按钮透传事件', async () => {
    const wrapper = mount(MobilePostCard, { props: { post: makePost() } })
    await wrapper.get('button[aria-label="投币"]').trigger('click')
    await wrapper.get('button[aria-label="分享"]').trigger('click')
    await wrapper.get('button[aria-label="评论"]').trigger('click')
    expect(wrapper.emitted('toggle-coin')).toHaveLength(1)
    expect(wrapper.emitted('share')).toHaveLength(1)
    expect(wrapper.emitted('open-comments')).toHaveLength(1)
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
  it('四个操作均为 button（评论/点赞/投币/分享全交互）', () => {
    const wrapper = mount(MobilePostActions, {
      props: { stats: makePost().stats, liked: false, coined: false },
    })
    expect(wrapper.findAll('button')).toHaveLength(4)
  })

  it('投币：click 触发 toggle-coin；coined 态带 is-coined 与 aria-pressed', async () => {
    const wrapper = mount(MobilePostActions, {
      props: { stats: makePost().stats, liked: false, coined: false },
    })
    const button = wrapper.get('button[aria-label="投币"]')
    await button.trigger('click')
    expect(wrapper.emitted('toggle-coin')).toHaveLength(1)

    await wrapper.setProps({ coined: true })
    expect(wrapper.get('button.u-comm-action.is-coined').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('button.u-comm-action.is-coined').attributes('aria-label')).toBe('取消投币')
  })

  it('评论与分享 click 各自触发事件', async () => {
    const wrapper = mount(MobilePostActions, {
      props: { stats: makePost().stats, liked: false, coined: false },
    })
    await wrapper.get('button[aria-label="评论"]').trigger('click')
    await wrapper.get('button[aria-label="分享"]').trigger('click')
    expect(wrapper.emitted('open-comments')).toHaveLength(1)
    expect(wrapper.emitted('share')).toHaveLength(1)
  })
})

describe('MobileCommentsSheet', () => {
  const mountSheet = (comments: CommunityPost['comments']) =>
    mount(MobileCommentsSheet, {
      props: { open: true, title: 'Title', comments },
      global: { stubs: { teleport: true } },
    })

  it('渲染标题与评论列表', () => {
    const wrapper = mountSheet([{ author: 'Kai', text: 'Nice one.', time: '5 分钟前' }])
    expect(wrapper.text()).toContain('Title')
    expect(wrapper.text()).toContain('Kai')
    expect(wrapper.text()).toContain('Nice one.')
  })

  it('空评论：显示空态文案', () => {
    const wrapper = mountSheet([])
    expect(wrapper.text()).toContain('还没有评论')
  })

  it('输入后发送：触发 add-comment 并清空输入；空输入禁发', async () => {
    const wrapper = mountSheet([])
    const send = wrapper.get('button[aria-label="发表评论"]')
    expect(send.attributes('disabled')).toBeDefined()

    await wrapper.get('input').setValue('  Great post!  ')
    expect(send.attributes('disabled')).toBeUndefined()
    await send.trigger('click')

    expect(wrapper.emitted('add-comment')).toEqual([['Great post!']])
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('')
  })

  it('关闭按钮触发 update:open false', async () => {
    const wrapper = mountSheet([])
    await wrapper.get('button[aria-label="关闭评论"]').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })
})
