/**
 * 唱吧 API 层「错误/失败文案映射」测试（M3 唱歌 P0）。
 *
 * 从 `composables/__tests__/sing.test.ts` 迁出（2026-09-10）：这三个函数是 **API 层纯函数**
 * （`api/sing.ts`），与组合式状态机无关；迁出后组合式测试文件回到 `max-lines 350` 门禁内
 * （eslint fe-08：新代码不豁免）。
 *
 * 覆盖：`singErrorMessage`（错误码→文案）、`favoriteErrorMessage`（收藏失败按 HTTP 状态分流，
 * 2026-09-10 真机命中 404）、`singFailureMessage`（P0-5：任务态失败按后端 `code` 映射，
 * 不再依赖 message 字符串匹配——docs/api/error-codes.md:30-31、docs/api/envelope.md）。
 */
import { describe, expect, it } from 'vitest'

import { ApiError } from '@/api/client'
import { favoriteErrorMessage, singErrorMessage, singFailureMessage } from '@/api/sing'

describe('singErrorMessage（docs/api/error-codes.md 文案映射）', () => {
  it('40905 参考旋律未就绪', () => {
    expect(singErrorMessage(new ApiError(40905, 'x', 409))).toContain('参考旋律')
  })
  it('41302 时长超限', () => {
    expect(singErrorMessage(new ApiError(41302, 'x', 413))).toContain('3 分钟')
  })
  it('40002 音频过短', () => {
    expect(singErrorMessage(new ApiError(40002, 'x', 400))).toContain('重录')
  })
  it('42901 限流提示（P0-5 后该码真实可达：全局 handler 翻译 HTTPException(429)）', () => {
    expect(singErrorMessage(new ApiError(42901, 'rate limited', 429))).toContain('5 次')
  })
  it('未知错误回退 message', () => {
    expect(singErrorMessage(new ApiError(50001, '上游超时', 500))).toBe('上游超时')
  })
})

describe('singFailureMessage（P0-5：任务态失败按后端 code 映射，不靠 message 匹配）', () => {
  it('50003（算法失败）→ 固定文案，且不透出内部异常原文', () => {
    expect(
      singFailureMessage({ code: 50003, error: 'audio file missing: /app/data/audio/x.webm' }),
    ).toContain('算法侧异常')
  })
  it('50002（服务内部错误）→ 稍后重试', () => {
    expect(singFailureMessage({ code: 50002, error: 'task lost' })).toContain('稍后重试')
  })
  it('无码 → 回退服务端文案；两者都缺 → 通用文案', () => {
    expect(singFailureMessage({ error: '自定义原因' })).toBe('自定义原因')
    expect(singFailureMessage({})).toBe('评分失败，请重试')
  })
  it('singErrorMessage 同样覆盖 50003/50002', () => {
    expect(singErrorMessage(new ApiError(50003, 'boom', 500))).toContain('算法侧异常')
    expect(singErrorMessage(new ApiError(50002, 'boom', 500))).toContain('稍后重试')
  })
})

describe('favoriteErrorMessage（2026-09-10 实测：收藏失败须能自诊断）', () => {
  it('404 → 后端未重建（今日真机命中：python-api 容器仍是旧代码）', () => {
    // 旧后端的 404 走 envelope 解析失败路径：code=-1 / message='HTTP 404'
    expect(favoriteErrorMessage(new ApiError(-1, 'HTTP 404', 404))).toContain('服务端没有收藏接口')
  })
  it('401 → 登录过期', () => {
    expect(favoriteErrorMessage(new ApiError(40101, 'unauthorized', 401))).toContain('登录已过期')
  })
  it('5xx → 服务端内部错误（提示迁移）', () => {
    expect(favoriteErrorMessage(new ApiError(50001, 'boom', 500))).toContain('迁移 0011')
  })
  it('普通网络错误 → 通用可重试文案', () => {
    expect(favoriteErrorMessage(new Error('network down'))).toBe('收藏操作失败，请重试')
  })
})
