import { describe, expect, it } from 'vitest'

import { resolvePageDir } from '../usePageTransition'

import type { RouteLocationNormalized } from 'vue-router'

const r = (path: string) => ({ path }) as RouteLocationNormalized

describe('resolvePageDir（页面转场方向）', () => {
  it('history position 递增 → forward', () => {
    expect(resolvePageDir(r('/m/home'), r('/m/post/1'), 3, 4)).toBe('forward')
  })

  it('history position 递减（后退）→ back', () => {
    expect(resolvePageDir(r('/m/post/1'), r('/m/home'), 4, 3)).toBe('back')
  })

  it('position 不可用时按层级：更深 → forward', () => {
    expect(resolvePageDir(r('/m/home'), r('/m/post/1'), null, null)).toBe('forward')
  })

  it('position 不可用时按层级：变浅 → back', () => {
    expect(resolvePageDir(r('/m/post/1'), r('/m/home'), null, null)).toBe('back')
  })

  it('同级页面切换（底部 Tab）→ forward', () => {
    expect(resolvePageDir(r('/m/home'), r('/m/search'), null, null)).toBe('forward')
  })
})