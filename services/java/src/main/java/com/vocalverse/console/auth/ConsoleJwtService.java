package com.vocalverse.console.auth;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Set;
import java.util.UUID;
import javax.crypto.SecretKey;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

/**
 * 控制台 access token 的签发与校验（docs/50 §4.1）。
 *
 * <p><b>claims 与设计逐字段对齐</b>：{@code sub}(adminUserId) / {@code aud}(vocalverse-console) / {@code
 * iss}(vocalverse-java) / {@code role}(roleCode) / {@code perms}(权限码数组) / {@code
 * typ}(console-access) / {@code jti} / {@code iat} / {@code exp}，access TTL <b>900s</b> （从既有 App 口径
 * 3600s 收紧，只对控制台生效，docs/50 §4.1 补偿项①）。
 *
 * <p>另加两个本实现所需的 claim（不改变上述契约，属**新增**字段）：
 *
 * <ul>
 *   <li>{@code epo} = {@code admin_users.token_epoch}：停用/改权/改密时 +1，使旧令牌**下一个请求即失效** （docs/50 §4.1
 *       补偿项③的三处之一，是本设计核心的即时生效机制）；
 *   <li>{@code sid} = {@code admin_sessions.id}：{@code /auth/logout} 需要「吊销当前会话」而不是「吊销该账号 全部会话」——没有
 *       sid 就只能全撤，会把用户其他设备的登录一起踢掉。
 * </ul>
 *
 * <p><b>签名密钥</b>：{@code VOICEVERSE_CONSOLE_JWT_SECRET}（≥32 字节）。 未配置时**回退到 App 的 {@code
 * JWT_SECRET}**，但该回退是**显式且有据可查**的：
 *
 * <ul>
 *   <li>回退时打一条明确的 WARN，说明「生产必须配置独立密钥」；
 *   <li>{@link #usingFallbackSecret()} 可查询回退状态，供启动自检/测试断言；
 *   <li>回退的原因不是图方便：Python 侧用同一个 HMAC 密钥验签（docs/50 §4.1 要求控制台令牌可被另一服务验证）， 而两服务当前只共享 {@code
 *       JWT_SECRET} 一个值。若强制要求独立密钥，Python 侧就必须同时拿到两个密钥， 那是一次跨服务的配置变更（不在本模块范围内）。
 * </ul>
 *
 * <p><b>跨端混淆不靠密钥差异，靠 aud + typ 双向闸门</b>（这也是为什么回退可以接受）：
 *
 * <ul>
 *   <li>控制台侧：{@link #parse} 强制 {@code aud=vocalverse-console} 且 {@code typ=console-access}；
 *   <li>App 侧：{@code com.vocalverse.config.JwtAuthFilter.isForeignToken} 拒绝任何 {@code
 *       typ=console-access} 或携带外来 {@code aud} 的令牌。
 * </ul>
 *
 * <p>两侧都由 {@code ConsoleCrossTokenTest} 双向验证 —— 回退场景下这些闸门是唯一屏障，因此它们必须在。
 * <b>本类不再有任何「随手共享密钥就能互相冒充」的路径</b>：共享的是密钥，隔离的是受众。
 */
@Service
public class ConsoleJwtService {

  private static final Logger log = LoggerFactory.getLogger(ConsoleJwtService.class);

  public static final String AUDIENCE = "vocalverse-console";
  public static final String ISSUER = "vocalverse-java";
  public static final String TYP_ACCESS = "console-access";

  /** access TTL 固定 900s（docs/50 §4.1；不开放配置，避免被调大后破坏「15 分钟内权限滞后」的上界承诺）。 */
  public static final long ACCESS_TTL_SECONDS = 900L;

  private final SecretKey key;
  private final boolean usingFallbackSecret;

  public ConsoleJwtService(
      @Value("${vocalverse.console.jwt-secret:}") String consoleSecret,
      @Value("${vocalverse.jwt.secret:}") String appSecret) {
    String secret = consoleSecret;
    boolean fallback = false;
    if (secret == null || secret.isBlank()) {
      secret = appSecret;
      fallback = true;
    }
    if (secret == null || secret.getBytes(StandardCharsets.UTF_8).length < 32) {
      throw new IllegalStateException(
          "vocalverse.console.jwt-secret 未配置或过短（≥32 字节）：检查 VOICEVERSE_CONSOLE_JWT_SECRET 环境变量"
              + "（本地可回退 JWT_SECRET，但两者都必须 ≥32 字节）");
    }
    this.key = Keys.hmacShaKeyFor(secret.getBytes(StandardCharsets.UTF_8));
    this.usingFallbackSecret = fallback;
    if (fallback) {
      log.warn(
          "控制台 JWT 未配置独立密钥（VOICEVERSE_CONSOLE_JWT_SECRET 为空）→ 回退使用 JWT_SECRET。"
              + "本地开发可接受（两个服务本就共享该密钥，Python 侧因此可验证控制台令牌）；"
              + "生产环境必须配置独立密钥。跨端令牌混淆由 aud/typ 双向校验阻断，不依赖密钥差异。");
    }
  }

  public boolean usingFallbackSecret() {
    return usingFallbackSecret;
  }

  /** 签发 access token（{@code perms} 为已展开的权限码集合；{@code epo}/{@code sid} 见类注释）。 */
  public String issueAccessToken(
      Long adminUserId,
      String username,
      String roleCode,
      Set<String> permissions,
      int tokenEpoch,
      Long sessionId) {
    Instant now = Instant.now();
    return Jwts.builder()
        .id(UUID.randomUUID().toString())
        .subject(String.valueOf(adminUserId))
        .audience()
        .add(AUDIENCE)
        .and()
        .issuer(ISSUER)
        .claim("role", roleCode)
        .claim("perms", List.copyOf(permissions))
        .claim("typ", TYP_ACCESS)
        .claim("epo", tokenEpoch)
        .claim("sid", sessionId)
        .claim("uname", username)
        .issuedAt(Date.from(now))
        .expiration(Date.from(now.plusSeconds(ACCESS_TTL_SECONDS)))
        .signWith(key)
        .compact();
  }

  /**
   * 解析并校验控制台令牌（验签 + exp + {@code aud} + {@code typ}）。
   *
   * <p>{@code aud}/{@code typ} 任一不符即抛异常 —— 这是「App token 拿不到控制台」的唯一闸门。
   *
   * @throws JwtException 验签失败 / 过期 / aud 不符
   * @throws IllegalArgumentException typ 不符或 sub 非数字
   */
  public Claims parse(String token) {
    Claims claims =
        Jwts.parser()
            .verifyWith(key)
            .requireAudience(AUDIENCE)
            .build()
            .parseSignedClaims(token)
            .getPayload();
    if (!TYP_ACCESS.equals(claims.get("typ", String.class))) {
      throw new IllegalArgumentException("非控制台令牌（typ 不符），拒绝");
    }
    return claims;
  }

  /** token_epoch（{@code epo}）；缺失按 0 处理（0 是建表默认值）。 */
  public static int epochOf(Claims claims) {
    Integer epo = claims.get("epo", Integer.class);
    return epo == null ? 0 : epo;
  }
}
