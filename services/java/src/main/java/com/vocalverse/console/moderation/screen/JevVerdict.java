package com.vocalverse.console.moderation.screen;

/**
 * Jev（TypeSafe System One）判定结果（docs/58 §3.2）。
 *
 * <p>三个问题一次并行问出：{@code noul} 是否违规、{@code choice} 违规类型（键与 {@code ModerationService.REASON_CODES}
 * 同值）、{@code score} 严重度（0=无问题 … 3=严重）。
 *
 * <p><b>概率是校准过的，但只在阈值门闸里用</b>：本仓不做自动处置，违规概率 ≥ 阈值只意味着「建一张待审单 交给人工」，所以概率失真最坏是多一次人工复核，不会误伤用户（docs/58
 * §4）。
 */
public record JevVerdict(
    String model,
    double violation,
    String category,
    double categoryConfidence,
    double severity,
    double severityConfidence,
    long latencyMs,
    int inputTokens) {}
