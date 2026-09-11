package com.vocalverse.console.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import com.vocalverse.config.JwtService;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.Date;
import java.util.Set;
import javax.crypto.SecretKey;
import org.junit.jupiter.api.Test;

/**
 * 令牌算法必须**恒为 HS256**（2026-09-10 实测缺陷的回归测试）。
 *
 * <h2>这个坑长什么样</h2>
 *
 * <p>JJWT 的 {@code Keys.hmacShaKeyFor(bytes)} 会**按密钥长度**决定算法：≥64 字节 → HmacSHA512、 ≥48 字节 →
 * HmacSHA384、≥32 字节 → HmacSHA256；而 {@code .signWith(key)}（不带算法参数）用的 就是 key 自带的那个。Python 侧 {@code
 * app/core/auth.py} 是**手写验签**，只算 HMAC-SHA256， 且不看 header 的 {@code alg}。于是只要密钥长度 ≥48 字节，两端算法就不一致：
 *
 * <pre>
 *   Java 密钥 = 48 个 hex 字符（=48 字节）→ 签 HS384
 *   Python                               → 按 HS256 验 → 全部 46001 "bad signature"
 * </pre>
 *
 * <p>而 `.env` 模板写的要求是"≥32 字节"，最自然的选法「64 个 hex 字符」= 64 字节更是直接落进 HS512 档 —— 也就是说**照着模板配就可能踩**。报错只说
 * "bad signature"，完全不提算法， 让人往"密钥不一致"方向排查（本轮实测就这么绕了几轮）。
 *
 * <p>修法是签发处显式钉死 {@code Jwts.SIG.HS256} + 解析处拒绝非 HS256。本测试把两条都钉住： 用**会导致自动选 HS384/HS512
 * 的密钥长度**构造服务，断言签出来的仍是 HS256、且能被自己解析； 同时断言手工签的 HS384 令牌会被拒（否则会出现"Java 认、Python 不认"的半可用令牌）。
 */
class JwtAlgorithmPinningTest {

  /** 48 字节：JJWT 会自动选 HmacSHA384 的长度（就是本轮踩到的那个）。 */
  private static final String SECRET_48 = "0123456789abcdef0123456789abcdef0123456789abcdef";

  /** 64 字节：会自动选 HmacSHA512 的长度（`openssl rand -hex 32` 的自然产物）。 */
  private static final String SECRET_64 = SECRET_48 + "0123456789abcdef";

  private static String algOf(String token) {
    String header = token.split("\\.")[0];
    String json =
        new String(
            Base64.getUrlDecoder().decode(header + "=".repeat((4 - header.length() % 4) % 4)),
            StandardCharsets.UTF_8);
    return json.replaceAll(".*\"alg\"\\s*:\\s*\"([^\"]+)\".*", "$1");
  }

  private static ConsoleJwtService consoleService(String secret) {
    // 三个构造参数：控制台密钥 + App 密钥（回退用）+ access TTL。测试里给同一密钥，避免回退分支干扰。
    return new ConsoleJwtService(secret, secret, ConsoleJwtService.DEFAULT_ACCESS_TTL_SECONDS);
  }

  @Test
  void console_token_alg_is_hs256_even_when_secret_length_would_pick_hs384_or_hs512() {
    for (String secret : new String[] {SECRET_48, SECRET_64}) {
      ConsoleJwtService svc = consoleService(secret);
      String token = svc.issueAccessToken(1L, "admin", "super", Set.of("ops:metric:read"), 0, 2L);
      assertEquals(
          "HS256",
          algOf(token),
          "密钥 "
              + secret.length()
              + " 字节时 JJWT 会改选 HS384/HS512，必须显式钉死 HS256"
              + "（否则 Python 侧按 HS256 验签，所有控制台端点 46001）");
      // 自签自验也要通（解析侧同样只接受 HS256）
      Claims claims = svc.parse(token);
      assertEquals("1", claims.getSubject());
    }
  }

  @Test
  void app_token_alg_is_hs256_even_when_secret_length_would_pick_hs384_or_hs512() {
    for (String secret : new String[] {SECRET_48, SECRET_64}) {
      JwtService svc = new JwtService(secret, 3600);
      String token = svc.generateAccessToken(42L, "user");
      assertEquals(
          "HS256", algOf(token), "App 令牌同样要钉住 HS256：Python 的 get_current_user_id 也用手写 HS256 验签");
      assertEquals(42L, svc.parseUserId(token));
    }
  }

  @Test
  void console_parse_rejects_hs384_token_signed_with_the_same_key() {
    ConsoleJwtService svc = consoleService(SECRET_48);
    SecretKey key = Keys.hmacShaKeyFor(SECRET_48.getBytes(StandardCharsets.UTF_8));
    String hs384 =
        Jwts.builder()
            .subject("1")
            .audience()
            .add(ConsoleJwtService.AUDIENCE)
            .and()
            .issuer(ConsoleJwtService.ISSUER)
            .claim("typ", "console-access")
            .issuedAt(new Date())
            .expiration(new Date(System.currentTimeMillis() + 60_000))
            .signWith(key, Jwts.SIG.HS384)
            .compact();
    assertEquals("HS384", algOf(hs384), "前置条件：这枚令牌确实是 HS384");

    IllegalArgumentException ex =
        assertThrows(IllegalArgumentException.class, () -> svc.parse(hs384));
    assertTrue(ex.getMessage().contains("HS256"), "拒绝理由必须点出算法要求，否则会误导成密钥问题：" + ex.getMessage());
  }

  @Test
  void app_parse_rejects_hs512_token_signed_with_the_same_key() {
    JwtService svc = new JwtService(SECRET_64, 3600);
    SecretKey key = Keys.hmacShaKeyFor(SECRET_64.getBytes(StandardCharsets.UTF_8));
    String hs512 =
        Jwts.builder()
            .subject("42")
            .issuedAt(new Date())
            .expiration(new Date(System.currentTimeMillis() + 60_000))
            .signWith(key, Jwts.SIG.HS512)
            .compact();
    assertEquals("HS512", algOf(hs512), "前置条件：这枚令牌确实是 HS512");
    assertThrows(JwtException.class, () -> svc.parse(hs512));
  }
}
