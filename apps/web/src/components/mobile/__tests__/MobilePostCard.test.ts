import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'

import MobileCommentsSheet from '@/components/mobile/MobileCommentsSheet.vue'
import MobilePostActions from '@/components/mobile/MobilePostActions.vue'
import MobilePostCard from '@/components/mobile/MobilePostCard.vue'

import type { CommunityPostView } from '@/types/community'

const mocks = vi.hoisted(() => ({ fetchComments: {} as ReturnType<typeof vi.fn>, addComment: {} as ReturnType<typeof vi.fn> }))

vi.mock('@/api/community', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/community')>()
  mocks.fetchComments = vi.fn().mockResolvedValue({ items: [], nextCursor: null, hasMore: false })
  mocks.addComment = vi.fn().mockResolvedValue({
    id: 99,
    author: { id: 2, nickname: 'Kai', handle: null, tint: null, level: 'L2' },
    body: 'Great post!',
    createdAt: new Date().toISOString(),
    replyToNickname: null,
  })
  return { ...actual, fetchComments: mocks.fetchComments, addComment: mocks.addComment }
})

function makePost(overrides: Partial<CommunityPostView> = {}): CommunityPostView {
  return {
    id: 1,
    author: { id: 1, nickname: 'VocalVerse News', handle: 'vocalverse', tint: '#37546e', level: 'L4' },
    kind: 'article',
    domain: 'news',
    title: "Inside China's English learning boom",
    body: 'Education experts say AI partners are changing how students practice speaking.',
    media: null,
    createdAt: new Date().toISOString(),
    likeCount: 1240,
    commentCount: 46,
    coinCount: 37,
    shareCount: 15,
    liked: false,
    coined: false,
    checkinOverall: null,
    checkinPracticeCount: null,
    checkinDate: null,
    ...overrides,
  }
}

function mountCard(post: CommunityPostView) {
  return mount(MobilePostCard, {
    props: { post, tintGradient: 'linear-gradient(135deg, #37546e, #6e96b4)' },
    global: { plugins: [createPinia()] },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
  mocks.fetchComments?.mockClear()
  mocks.addComment?.mockClear()
})

describe('MobilePostCard', () => {
  it('渲染作者 / 标题 / 摘要 / 互动计数（千位缩写 1.2k / LV 展示）', () => {
    const wrapper = mountCard(makePost())
    const text = wrapper.text()
    expect(text).toContain('VocalVerse News')
    expect(text).toContain('@vocalverse')
    expect(text).toContain('LV4')
    expect(text).toContain('English learning')
    expect(text).toContain('新闻稿') // domain 存储值 → 展示文案映射（A-03）
    expect(text).toContain('1.2k') // like 1240
    expect(text).toContain('46') // comment
    expect(text).toContain('37') // coin
    expect(text).toContain('15') // share
  })

  it('打卡卡：整体分 / 今日次数 / 日期渲染', () => {
    const wrapper = mountCard(
      makePost({
        kind: 'checkin',
        domain: null,
        checkinOverall: 88.5,
        checkinPracticeCount: 3,
        checkinDate: '2026-09-06',
      }),
    )
    const text = wrapper.text()
    expect(text).toContain('今日打卡')
    expect(text).toContain('今日综合分') // overall 取整展示（toFixed(0)）
    expect(text).toContain('3 次口语练习')
    expect(text).toContain('2026-09-06')
  })

  it('点赞按钮：click 触发 toggle-like；liked 态带 is-liked 与 aria-pressed', async () => {
    const wrapper = mountCard(makePost())
    const button = wrapper.get('button[aria-label="点赞"]')
    expect(button.attributes('aria-pressed')).toBe('false')

    await button.trigger('click')
    expect(wrapper.emitted('toggle-like')).toHaveLength(1)

    await wrapper.setProps({ post: makePost({ liked: true }) })
    const likedButton = wrapper.get('button.u-comm-action.is-liked')
    expect(likedButton.attributes('aria-pressed')).toBe('true')
    expect(likedButton.attributes('aria-label')).toBe('取消点赞')
  })

  it('支持 / 分享 / 评论按钮透传事件；已支持态 aria 锁定（不可取消）', async () => {
    const wrapper = mountCard(makePost())
    await wrapper.get('button[aria-label="支持"]').trigger('click')
    await wrapper.get('button[aria-label="分享"]').trigger('click')
    await wrapper.get('button[aria-label="评论"]').trigger('click')
    expect(wrapper.emitted('coin')).toHaveLength(1)
    expect(wrapper.emitted('share')).toHaveLength(1)
    expect(wrapper.emitted('open-comments')).toHaveLength(1)

    await wrapper.setProps({ post: makePost({ coined: true }) })
    const coinedBtn = wrapper.get('button[aria-label="已支持（不可取消）"]')
    expect(coinedBtn.attributes('aria-pressed')).toBe('true')
  })

  it('视频帖：渲染视频封面样式与时长角标（seconds → m:ss）', () => {
    const wrapper = mountCard(
      makePost({ kind: 'video', media: { type: 'video', durationS: 383 } }),
    )
    // 2026-09-09（社区 S3）：单媒体渲染下沉到 MobileMediaGrid（类名 u-media--video）
    expect(wrapper.find('.u-media--video').exists()).toBe(true)
    expect(wrapper.text()).toContain('6:23')
  })

  it('S1 种子形状（duration_s snake_case）也能出时长角标（修复前角标恒为空，docs/48 B8）', () => {
    const wrapper = mountCard(
      makePost({ kind: 'video', media: { type: 'video', duration_s: 383 } }),
    )
    expect(wrapper.text()).toContain('6:23')
  })

  it('多图帖：列表卡只渲首图 + 「+N」角标（feed 放大防护）', () => {
    const wrapper = mountCard(
      makePost({
        media: {
          type: 'image',
          items: [
            { id: 'a', url: '/api/v1/media/a' },
            { id: 'b', url: '/api/v1/media/b' },
            { id: 'c', url: '/api/v1/media/c' },
          ],
        },
      }),
    )
    expect(wrapper.findAll('.u-media-grid__cell')).toHaveLength(1)
    expect(wrapper.text()).toContain('+2')
  })

  it('整卡可点 → 跳详情页（修复「点帖子无查看方式」）', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/m/post/:postId', component: { template: '<div />' } }],
    })
    await router.push('/m/home')
    await router.isReady()
    const wrapper = mount(MobilePostCard, {
      props: { post: makePost(), tintGradient: 'linear-gradient(#000,#fff)' },
      global: { plugins: [router] },
    })
    await wrapper.get('.u-comm-item__tap').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/m/post/1')
  })

  it('无配图帖：不渲染媒体块（标题隐藏分支同样适用）', () => {
    const wrapper = mountCard(makePost({ media: null, body: null, title: null }))
    expect(wrapper.find('.u-media').exists()).toBe(false)
    expect(wrapper.find('.u-media-grid').exists()).toBe(false)
    expect(wrapper.find('h3.u-comm-item__title').exists()).toBe(false)
  })
})

describe('MobilePostActions', () => {
  it('四个操作均为 button（评论/点赞/支持/分享全交互）', () => {
    const wrapper = mount(MobilePostActions, {
      props: { likeCount: 1, commentCount: 1, coinCount: 1, shareCount: 1, liked: false, coined: false },
    })
    expect(wrapper.findAll('button')).toHaveLength(4)
  })

  it('支持：click 触发 coin；已支持态 aria 为不可取消', async () => {
    const wrapper = mount(MobilePostActions, {
      props: { likeCount: 1, commentCount: 1, coinCount: 1, shareCount: 1, liked: false, coined: true },
    })
    const button = wrapper.get('button[aria-label="已支持（不可取消）"]')
    await button.trigger('click')
    expect(wrapper.emitted('coin')).toHaveLength(1)
    expect(wrapper.get('button.u-comm-action.is-coined').attributes('aria-pressed')).toBe('true')
  })
})

describe('MobileCommentsSheet', () => {
  const mountSheet = (commentCount: number) =>
    mount(MobileCommentsSheet, {
      props: { open: true, postId: 1, title: 'Title', commentCount },
      global: { stubs: { teleport: true }, plugins: [createPinia()] },
    })

  it('渲染标题与「共 N 条」，空列表显示空态文案', async () => {
    const wrapper = mountSheet(46)
    await flushPromises()
    expect(wrapper.text()).toContain('Title')
    expect(wrapper.text()).toContain('· 46')
    expect(wrapper.text()).toContain('还没有评论')
  })

  it('重新打开（重挂载）会重新拉取——immediate watch 回归（评论消失 BUG）', async () => {
    const wrapper = mountSheet(46)
    await flushPromises()
    expect(mocks.fetchComments).toHaveBeenCalledTimes(1)

    // 模拟父级 v-if 关闭卸载 → 重开重挂载（open 值无变化，immediate 也必须重新请求）
    wrapper.unmount()
    const wrapper2 = mountSheet(46)
    await flushPromises()
    expect(mocks.fetchComments).toHaveBeenCalledTimes(2)

    // 切帖（postId 变化，open 保持 true）→ 重新拉取该帖评论
    await wrapper2.setProps({ postId: 2 })
    await flushPromises()
    expect(mocks.fetchComments).toHaveBeenCalledTimes(3)
  })

  it('输入后发送：触发 add-comment 并清空输入；空输入禁发', async () => {
    const wrapper = mountSheet(0)
    await flushPromises()
    const send = wrapper.get('button[aria-label="发表评论"]')
    expect(send.attributes('disabled')).toBeDefined()

    await wrapper.get('input').setValue('  Great post!  ')
    expect(send.attributes('disabled')).toBeUndefined()
    await send.trigger('click')
    await flushPromises()

    expect(wrapper.emitted('update-count')).toBeTruthy()
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('')
  })

  it('关闭按钮触发 update:open false', async () => {
    const wrapper = mountSheet(0)
    await flushPromises()
    await wrapper.get('button[aria-label="关闭评论"]').trigger('click')
    expect(wrapper.emitted('update:open')).toEqual([[false]])
  })
})
