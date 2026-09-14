package com.vocalverse.console.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import io.jsonwebtoken.Claims;
import java.util.Set;
import org.junit.jupiter.api.Test;

/**
 * 控制台 access TTL 的**可配置**行为（2026-09-10）。
 *
 * <h2>为什么要有这个开关</h2>
 *
 * <p>原先 TTL 是写死的常量 {@code ACCESS_TTL_SECONDS = 900}，联调时每 15 分钟就要重登一次， 很影响测试节奏。但把这个值直接改成 3 小时又会**推翻
 * docs/50 §4.1 的安全口径**： 它同时是「权限/停用变更最长滞后多久」的上界（令牌里的 {@code perms} 在有效期内不刷新， 即时失效靠 {@code
 * token_epoch}），生产必须保持 15 分钟。
 *
 * <p>所以做成配置项 {@code vocalverse.console.access-ttl-seconds} （环境变量 {@code
 * VOICEVERSE_CONSOLE_ACCESS_TTL_SECONDS}），**默认仍是 900**， 本地要用 3 小时就在根 {@code .env} 里写
 * 10800；启动日志对非默认值打 WARN。
 *
 * <p>本测试钉住三件事：默认值不变、覆盖值真的进了 {@code exp}（不只是显示数字）、 非法值 fail-fast。
 */
class ConsoleAccessTtlTest {

  private static final String SECRET = "0123456789abcdef0123456789abcdef0123456789abcdef";

  @Test
  void default_ttl_stays_900_seconds() {
    ConsoleJwtService svc =
        new ConsoleJwtService(SECRET, SECRET, ConsoleJwtService.DEFAULT_ACCESS_TTL_SECONDS);
    assertEquals(900L, ConsoleJwtService.DEFAULT_ACCESS_TTL_SECONDS, "docs/50 §4.1 的默认值不得被改动");
    assertEquals(900L, svc.accessTtlSeconds());
  }

  @Test
  void custom_ttl_lands_in_both_claims_and_accessor() {
    ConsoleJwtService svc = new ConsoleJwtService(SECRET, SECRET, 10800L); // 3 小时
    assertEquals(10800L, svc.accessTtlSeconds());

    String token = svc.issueAccessToken(1L, "admin", "super", Set.of("ops:metric:read"), 0, 1L);
    Claims claims = svc.parse(token);
    long expMinusIat =
        claims.getExpiration().toInstant().getEpochSecond()
            - claims.getIssuedAt().toInstant().getEpochSecond();
    // 关键：不只是 accessor 报数字，**令牌的 exp 必须真的按它来** ——
    // 否则登录响应的 expiresIn 与实际过期时间会不一致（前端会按前者安排续期）。
    assertEquals(10800L, expMinusIat, "exp - iat 必须等于配置的 TTL");
  }

  @Test
  void non_positive_ttl_fails_fast() {
    assertThrows(IllegalArgumentException.class, () -> new ConsoleJwtService(SECRET, SECRET, 0L));
    assertThrows(IllegalArgumentException.class, () -> new ConsoleJwtService(SECRET, SECRET, -1L));
  }
}
