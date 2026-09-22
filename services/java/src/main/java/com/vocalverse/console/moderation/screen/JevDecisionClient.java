package com.vocalverse.console.moderation.screen;

import java.util.Optional;

/**
 * 决策模型客户端（docs/58 §3.2）。
 *
 * <p>抽成接口只有一个理由：**测试要能在不起 HTTP 服务的情况下控制判定**。生产实现是 {@link JevHttpClient}（TypeSafe System One
 * API）；测试用 {@code StubJevDecisionClient}。
 *
 * <p>失败语义：返回 {@link Optional#empty()} = 未启用 / 超时 / 上游错误 / 响应不可解析。
 * 调用方一律**降级放行**（内容保持可见、不建单），绝不把送审失败变成发布失败（docs/58 §4.3）。
 */
public interface JevDecisionClient {

  Optional<JevVerdict> screen(JevScreenRequest request);
}
