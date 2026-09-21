import { describe, expect, it } from 'vitest'

import { NAV_ICON_NAMES } from '@/components/layout/navIcons'
import { NAV_GROUPS } from '@/router/nav'

/**
 * 回归：导航项声明的 icon 必须在 NavIcon 的显式映射里有登记。
 *
 * 背景（2026-09-21）：新增「场景卡」菜单时写了 `icon: 'dice'` 但忘了登记映射，
 * NavIcon 对未知图标名**静默渲染空位**（设计如此，避免白屏）——结果侧栏那一项没有图标，
 * 只能靠肉眼发现。此用例把这类漏登记变成构建期红灯。
 */
describe('控制台导航图标登记', () => {
  it('每个导航项的 icon 都在 NavIcon 映射内', () => {
    const missing: string[] = []
    for (const group of NAV_GROUPS) {
      for (const item of group.items) {
        if (!NAV_ICON_NAMES.includes(item.icon)) {
          missing.push(`${group.key}/${item.label} → ${item.icon}`)
        }
      }
    }
    expect(missing, `未登记的导航图标：${missing.join('；')}`).toEqual([])
  })
})
