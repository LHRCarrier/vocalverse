package com.vocalverse.config;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import javax.crypto.SecretKey;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * JWT 签发/校验（HS256；与 Python 侧 app/core/auth.py 手写验签对齐： base64url 无 padding + 标准 exp/iat；sub =
 * userId；role 为 2026-09 新增 claim，Python 验签不读取，向后兼容）。
 */
@Service
public class JwtService {

  private final SecretKey key;
  private final long accessTtlSeconds;

  public JwtService(
      @Value("${vocalverse.jwt.secret}") String secret,
      @Value("${vocalverse.jwt.access-ttl-seconds:3600}") long accessTtlSeconds) {
    // docs/19 P0-9：密钥缺失/过短 → 启动即失败（fail-fast），不复用仓库默认值。
    // docs/06 §11：≥32 字节为 JJWT 硬性要求；空串会在首次签名时才炸，改为显式早抛。
    if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
      throw new IllegalStateException(
          "vocalverse.jwt.secret 未配置或过短（≥32 字节）：检查 JWT_SECRET 环境变量（docs/19 P0-9）");
    }
    this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    this.accessTtlSeconds = accessTtlSeconds;
  }

  /** 签发 access token；role 值取 users.role（user/admin），写入 claim 供管理端授权（docs/06 §9.6）。 */
  public String generateAccessToken(Long userId, String role) {
    Instant now = Instant.now();
    return Jwts.builder()
        .subject(String.valueOf(userId))
        .claim("role", role)
        .issuedAt(Date.from(now))
        .expiration(Date.from(now.plusSeconds(accessTtlSeconds)))
        .signWith(key)
        .compact();
  }

  /** 解析并验签；失败抛 io.jsonwebtoken.JwtException（由过滤器转 401）。 */
  public Claims parse(String token) {
    return Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
  }

  public Long parseUserId(String token) {
    return Long.parseLong(parse(token).getSubject());
  }
}
