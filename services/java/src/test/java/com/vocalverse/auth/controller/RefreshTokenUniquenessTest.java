package com.vocalverse.auth.controller;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;

/**
 * 回归测试：refresh token 唯一性（2026-09-10 手机实测复现 40904「数据冲突」）。
 *
 * <p>根因：JwtService 令牌无随机字段（秒级精度）→ 同毫秒双登录/双刷新产出相同 refresh 字符串 → SHA-256 相同 → 撞
 * refresh_tokens.token_hash 唯一键。
 *
 * <p>本测试用「相同输入」直接驱动构造器：修复前（无 UUID 因子）同输入必产出同串 → 红； 修复后（UUID 因子）同输入必产出不同串且有随机后缀 → 绿。确定性、零时序依赖。
 */
class RefreshTokenUniquenessTest {

  @Test
  void sameInputProducesDistinctTokens() {
    String token1 = AuthController.buildRefreshToken("same-jwt-part", 1700000000000L);
    String token2 = AuthController.buildRefreshToken("same-jwt-part", 1700000000000L);
    assertNotEquals(token1, token2, "同毫秒双登录不得产出相同 refresh token（40904 根因）");
    assertTrue(token1.startsWith("same-jwt-part-1700000000000-"), "保持既有前缀格式");
    assertTrue(token1.length() > "same-jwt-part-1700000000000-".length() + 20, "含随机因子");
  }
}
