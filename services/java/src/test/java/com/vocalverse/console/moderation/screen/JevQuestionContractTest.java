package com.vocalverse.console.moderation.screen;

import static org.junit.jupiter.api.Assertions.assertEquals;

import com.vocalverse.console.moderation.ModerationService;
import java.util.LinkedHashSet;
import org.junit.jupiter.api.Test;

/**
 * Jev 问题定义与控制台原因码的**契约测试**（docs/58 §3.2）。
 *
 * <p>choice 选项键与 {@code ModerationService.REASON_CODES} 逐字同值，是为了不维护一张映射表 ——
 * 但「不用映射表」只有在两者始终相等时才成立。这个用例把等式钉死：将来谁给原因码加了新值而忘了加 Jev 选项， CI 会红，而不是线上把新类型全部判成 {@code other}。
 */
class JevQuestionContractTest {

  @Test
  void categoryOptionsMatchReasonCodesExactly() {
    assertEquals(
        new LinkedHashSet<>(ModerationService.REASON_CODES),
        JevHttpClient.categoryCriteria().keySet(),
        "Jev 的违规类型选项必须与 ModerationService.REASON_CODES 完全一致（含顺序）");
  }
}
