package com.vocalverse.auth;

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
 * userId）。
 */
@Service
public class JwtService {

  private final SecretKey key;
  private final long accessTtlSeconds;

  public JwtService(
      @Value("${vocalverse.jwt.secret}") String secret,
      @Value("${vocalverse.jwt.access-ttl-seconds:3600}") long accessTtlSeconds) {
    this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    this.accessTtlSeconds = accessTtlSeconds;
  }

  public String generateAccessToken(Long userId) {
    Instant now = Instant.now();
    return Jwts.builder()
        .subject(String.valueOf(userId))
        .issuedAt(Date.from(now))
        .expiration(Date.from(now.plusSeconds(accessTtlSeconds)))
        .signWith(key)
        .compact();
  }

  /** 解析并验签；失败抛 io.jsonwebtoken.JwtException（由过滤器转 401）。 */
  public Long parseUserId(String token) {
    Claims claims = Jwts.parser().verifyWith(key).build().parseSignedClaims(token).getPayload();
    return Long.parseLong(claims.getSubject());
  }
}
