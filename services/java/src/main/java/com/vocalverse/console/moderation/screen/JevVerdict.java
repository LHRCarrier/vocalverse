package com.vocalverse.console.moderation.screen;

/**
 * Jev（TypeSafe System One）判定结果（docs/58 §3.2）。
 *
 * <p>三个问题一次并行问出：{@code noul} 是否违规、{@code choice} 命中《社区规范》哪一条（R1~R9，见 {@code docs/59}）、{@code score}
 * 严重度（0=无问题 … 3=严重）。
 *
 * <p>{@code clause} 是规范条款号，{@code category} 由它派生成控制台的原因码（spam|abuse|…）—— 映射表在 {@link
 * JevHttpClient#CLAUSE_TO_REASON}，测试把「映射值覆盖全部原因码」钉死。
 *
 * <p><b>概率是校准过的，但只在阈值门闸里用</b>：本仓不做自动处置，违规概率 ≥ 阈值只意味着「建一张待审单 交给人工」，所以概率失真最坏是多一次人工复核，不会误伤用户（docs/58
 * §4）。
 */
public record JevVerdict(
    String model,
    double violation,
    String clause,
    String category,
    double clauseConfidence,
    double severity,
    double severityConfidence,
    long latencyMs,
    int inputTokens) {}
