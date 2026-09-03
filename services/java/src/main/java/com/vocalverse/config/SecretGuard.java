package com.vocalverse.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;

/**
 * 密钥 fail-fast（P0-1 / docs/20:185）：production 环境下拒绝已知默认/过短密钥，防伪造 JWT 与内部回调。
 *
 * <p>仅当 {@code vocalverse.app-env == 'production'} 时触发；development/docker/test（compose 用
 * development）不受影响，避免破坏本地一键起。强制生产在 compose/.env 注入非默认 JWT_SECRET 与
 * SERVICE_TOKEN（两服务须独立且不一致）。
 */
@Configuration
public class SecretGuard {

  private static final String KNOWN_JWT = "vocalverse-dev-jwt-secret-0123456789abcdef";
  private static final String KNOWN_SERVICE = "change-me-internal-service-token";

  public SecretGuard(
      @Value("${vocalverse.app-env:development}") String appEnv,
      @Value("${vocalverse.jwt.secret:}") String jwtSecret,
      @Value("${vocalverse.service-token:}") String serviceToken) {
    if (!"production".equals(appEnv)) {
      return;
    }
    if (jwtSecret.isBlank()
        || KNOWN_JWT.equals(jwtSecret)
        || jwtSecret.length() < 32
        || serviceToken.isBlank()
        || KNOWN_SERVICE.equals(serviceToken)) {
      throw new IllegalStateException(
          "vocalverse.app-env=production requires strong non-default JWT_SECRET and SERVICE_TOKEN (failed fast, P0-1)");
    }
  }
}
