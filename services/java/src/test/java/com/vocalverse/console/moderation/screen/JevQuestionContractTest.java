package com.vocalverse.console.moderation.screen;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.vocalverse.console.moderation.ModerationService;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

/**
 * Jev 条款判据与控制台原因码的**契约测试**（docs/58 §3.2 / docs/59）。
 *
 * <p>判据链路是「内容 → 命中《社区规范》条款（R1~R9）→ 条款映射成原因码」，本条把三件事钉死：
 *
 * <ol>
 *   <li>choice 选项 = R1~R9 + {@code none}（漏一个 → 该类违规永远判不出或永远误判）；
 *   <li>条款→原因码映射**恰好覆盖** {@code ModerationService.REASON_CODES}（少一个 → 该类会被落成 other， 前端筛选与统计静默失真）；
 *   <li>映射键都是真实条款（写错字 → 映射永远不命中）。
 * </ol>
 */
class JevQuestionContractTest {

  @Test
  void clauseOptionsAreR1ToR9PlusNone() {
    assertEquals(
        new LinkedHashSet<>(List.of("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "none")),
        JevHttpClient.clauseCriteria().keySet(),
        "Jev 的条款选项必须恰好是 R1~R9 + none");
  }

  @Test
  void clauseMappingCoversAllReasonCodesExactly() {
    Map<String, String> mapping = JevHttpClient.clauseToReason();
    assertEquals(
        new LinkedHashSet<>(ModerationService.REASON_CODES),
        new LinkedHashSet<>(mapping.values()),
        "条款→原因码映射必须与 ModerationService.REASON_CODES 完全一致");
    for (String clause : mapping.keySet()) {
      assertTrue(
          JevHttpClient.clauseCriteria().containsKey(clause), "映射里的条款号必须在 choice 选项里：" + clause);
    }
  }
}
