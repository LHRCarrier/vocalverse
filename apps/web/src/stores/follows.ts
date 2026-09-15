/**
 * 关注 store（2026-09-09 组长拍板：关注好友能力收敛进通知中心「关注」tab）
 * 演示帧：initial 列表 + follow() 关注动作（顶部插入新动态 + unread）；M3 接真实关注关系（Java 用户关系表 + 帖子 JOIN）。
 */
import { defineStore } from 'pinia'
import { reactive } from 'vue'

export interface FollowActivity {
  name: string
  tint: string
  text: string
  when: string
  unread: boolean
}

const INITIAL: FollowActivity[] = [
  { name: 'Kai', tint: '#16303a', text: '发布了新帖：How I memorize 100 new words a month — the shadowing method', when: '10:05', unread: true },
  { name: 'Momo', tint: '#3a2440', text: '发布了新帖：6 Minute English: Why do we procrastinate?', when: '09:41', unread: true },
  { name: 'Teacher Lee', tint: '#232044', text: '更新了影子跟读素材：2 篇入门', when: '昨天', unread: false },
  { name: 'BBC Learning English', tint: '#2b4a3a', text: '发布了新视频：Dorm life at MIT', when: '周二', unread: false },
]

export const useFollowStore = defineStore('follows', () => {
  const activities = reactive<FollowActivity[]>(INITIAL.map((a) => ({ ...a })))

  /** 关注某人（演示：顶部插入动态 + 未读）——M3 换真实 follow 接口 */
  function follow(name: string, tint: string, text: string) {
    activities.unshift({ name, tint, text, when: '刚刚', unread: true })
  }

  return { activities, follow }
})
