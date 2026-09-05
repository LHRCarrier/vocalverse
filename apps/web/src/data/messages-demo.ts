/**
 * 私信演示数据（2026-09-05 组长拍板：底部 tab「我的」→「私信」；演示帧，本地收发不回传）
 * M3 真实消息流接入时删除本文件并换接口数据源（docs/34 同款口径）。
 */
export interface DemoMessage {
  from: 'me' | 'them'
  text: string
  time: string
}

export interface DemoConversation {
  id: number
  name: string
  handle: string
  tint: string
  lastMsg: string
  time: string
  unread: boolean
  history: DemoMessage[]
  /** 演示自动回复轮换池（发送后 1.2s 弹出下一条） */
  replies: string[]
}

export function createDemoConversations(): DemoConversation[] {
  return [
    {
      id: 1,
      name: 'Kai',
      handle: '@kai_learns',
      tint: '#16303a',
      lastMsg: 'Great point! I will check it out tonight.',
      time: '10:42',
      unread: true,
      history: [
        { from: 'them', text: 'That article we talked about — you read it yet?', time: '10:31' },
        { from: 'me', text: 'Almost done. The classrooms part is wild.', time: '10:40' },
        { from: 'them', text: 'Great point! I will check it out tonight.', time: '10:42' },
      ],
      replies: [
        'True — and the shadowing routine helps me a lot too.',
        'Let us practice a role-play about it tomorrow!',
        'Nice, keep me posted on your progress.',
      ],
    },
    {
      id: 2,
      name: 'Momo',
      handle: '@momo_english',
      tint: '#3a2440',
      lastMsg: 'The 6-minute episode was so good 🎧',
      time: '昨天',
      unread: false,
      history: [
        { from: 'them', text: 'The 6-minute episode was so good 🎧', time: '昨天' },
        { from: 'me', text: 'Subscribed to the podcast yet?', time: '昨天' },
      ],
      replies: ['Right? The vocabulary recap at the end is gold.'],
    },
    {
      id: 3,
      name: 'Teacher Lee',
      handle: '@leeenglish',
      tint: '#232044',
      lastMsg: 'Try 10 minutes shadowing before breakfast.',
      time: '周三',
      unread: false,
      history: [
        { from: 'me', text: 'How do you fit shadowing into a busy day?', time: '周三' },
        { from: 'them', text: 'Try 10 minutes shadowing before breakfast.', time: '周三' },
      ],
      replies: ['Consistency beats intensity — small daily wins.'],
    },
    {
      id: 4,
      name: 'BBC Learning English',
      handle: '@bbcle',
      tint: '#2b4a3a',
      lastMsg: 'New episode: Why do we procrastinate?',
      time: '周二',
      unread: false,
      history: [
        { from: 'them', text: 'New episode: Why do we procrastinate?', time: '周二' },
      ],
      replies: ['Glad you enjoyed it — see you in the next episode!'],
    },
  ]
}
