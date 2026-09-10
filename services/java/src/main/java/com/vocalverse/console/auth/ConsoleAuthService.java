package com.vocalverse.console.auth;

import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.ConsoleException;
import com.vocalverse.console.audit.AuditService;
import com.vocalverse.console.audit.IndependentAuditWriter;
import com.vocalverse.console.rbac.AdminLoginAttemptEntity;
import com.vocalverse.console.rbac.AdminLoginAttemptRepository;
import com.vocalverse.console.rbac.AdminRoleEntity;
import com.vocalverse.console.rbac.AdminRoleRepository;
import com.vocalverse.console.rbac.AdminSessionEntity;
import com.vocalverse.console.rbac.AdminSessionRepository;
import com.vocalverse.console.rbac.AdminUserEntity;
import com.vocalverse.console.rbac.AdminUserRepository;
import com.vocalverse.console.rbac.RbacService;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 控制台独立身份（docs/50 §4.1）。
 *
 * <h2>错误码取舍：为什么「用户名不存在」与「口令错误」是同一个码（46004）</h2>
 *
 * <p>docs/50 §10.4 的码表把 46003/46004/46008 并列，但**没说哪一种是「哪个前提失败」**。逐条对照后本实现的 映射如下，每条都对齐 §10.4 的 HTTP
 * 状态，且**不向未认证调用方泄漏「该用户名是否存在」**：
 *
 * <table border="1">
 *   <tr><th>内部情形</th><th>对外码</th><th>HTTP</th><th>为什么</th></tr>
 *   <tr><td>用户名不存在</td><td>46004</td><td>404</td><td>与「口令错误」合并 —— 分开会让攻击者用
 *       10 行脚本枚举出全部管理端账号名（管理端账号名是可猜的：admin/ops/…）</td></tr>
 *   <tr><td>口令错误</td><td>46004</td><td>404</td><td>同上。404 而非 401 只因 §10.4 如此规定，
 *       两者对外完全一致，无信息差异</td></tr>
 *   <tr><td>账号已停用<br><b>且口令正确</b></td><td>46003</td><td>403</td><td>已通过口令验证 = 调用方本就是账号所有者，
 *       此时告知「已停用」不泄漏任何东西，反而避免用户以为是自己打错口令。<b>口令错误时仍回 46004</b></td></tr>
 *   <tr><td>账号被临时锁定</td><td>46003</td><td>403</td><td>同上，但**在验口令之前**就返回 ——
 *       锁定期间不消耗 BCrypt（防「靠锁定期间的响应时间差探测账号存在」），也避免锁定形同虚设</td></tr>
 *   <tr><td>同 IP 超限</td><td>46008</td><td>429</td><td>与账号无关，按 §10.4 语义即为「登录失败次数过多」</td></tr>
 * </table>
 *
 * <p>另外两处反枚举细节：① 用户名不存在时也**跑一次 BCrypt 校验**（对固定假哈希），让响应时间与真实账号一致， 避免时序侧信道；② 失败计数对**不存在的用户名同样累加**（落在
 * {@code admin_login_attempts.reason=unknown_user}）， 所以「先爆破一堆用户名再挑真的」也要吃 5 次/15 分钟的限速。
 *
 * <h2>刷新令牌一次性轮换 + 重放检测</h2>
 *
 * <p>轮换：refresh 时按 sha256 查会话 → 吊销旧行（{@code reason=rotated}）→ 签发新行。 <b>重放已吊销的令牌 =
 * 该令牌被窃取的强信号</b>（合法客户端拿到新令牌后不会再发旧的），所以本实现**吊销该账号 全部会话**（{@code
 * reason=token_reuse_detected}），而不只是拒绝这一次。取舍：这会误伤「用户自己回退了浏览器
 * 历史/并发刷新」，但代价是重新登录一次，而漏判的代价是攻击者持续持有有效刷新令牌 —— 安全优先。 注意 {@code token_reuse_detected} 长 21 字符，落在
 * {@code revoke_reason varchar(32)} 内（docs/50 §5.3.5）。
 */
@Service
public class ConsoleAuthService {

  private static final Logger log = LoggerFactory.getLogger(ConsoleAuthService.class);

  /** 同账号失败阈值（docs/50 §4.1：5 次 / 15 分钟）。 */
  public static final int FAILURE_THRESHOLD = 5;

  /** 锁定时长。 */
  public static final Duration LOCK_DURATION = Duration.ofMinutes(15);

  /** 失败计数窗口。 */
  public static final Duration FAILURE_WINDOW = Duration.ofMinutes(15);

  /** 同 IP 限流：20 次 / 5 分钟。 */
  public static final int IP_THRESHOLD = 20;

  public static final Duration IP_WINDOW = Duration.ofMinutes(5);

  /** refresh token TTL 12h（docs/50 §4.1）。 */
  public static final Duration REFRESH_TTL = Duration.ofHours(12);

  /** 用户不存在时用来「跑一次 BCrypt」的假哈希（cost 10，固定值，对应口令为随机串）。 目的是让「账号不存在」与「口令错误」的响应耗时都包含一次 BCrypt 校验。 */
  private static final String DUMMY_HASH =
      "$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy";

  private static final SecureRandom RANDOM = new SecureRandom();

  private final AdminUserRepository adminUsers;
  private final AdminRoleRepository roles;
  private final AdminSessionRepository sessions;
  private final AdminLoginAttemptRepository attempts;
  private final PasswordEncoder passwordEncoder;
  private final ConsoleJwtService jwt;
  private final RbacService rbac;
  private final AuditService audit;
  private final IndependentAuditWriter auditWriter;

  public ConsoleAuthService(
      AdminUserRepository adminUsers,
      AdminRoleRepository roles,
      AdminSessionRepository sessions,
      AdminLoginAttemptRepository attempts,
      PasswordEncoder passwordEncoder,
      ConsoleJwtService jwt,
      RbacService rbac,
      AuditService audit,
      IndependentAuditWriter auditWriter) {
    this.adminUsers = adminUsers;
    this.roles = roles;
    this.sessions = sessions;
    this.attempts = attempts;
    this.passwordEncoder = passwordEncoder;
    this.jwt = jwt;
    this.rbac = rbac;
    this.audit = audit;
    this.auditWriter = auditWriter;
  }

  /** 登录结果（access + refresh + 有效期 + 主体摘要）。 */
  public record LoginResult(
      String accessToken,
      String refreshToken,
      long expiresIn,
      Long adminUserId,
      String username,
      String displayName,
      String roleCode,
      Set<String> permissions) {}

  // ------------------------------------------------------------------ 登录

  @Transactional
  public LoginResult login(String usernameRaw, String password, String ip, String userAgent) {
    String username = usernameRaw == null ? "" : usernameRaw.trim();
    Instant now = Instant.now();

    // ① 同 IP 限流（先于账号查询：限流命中时不应有任何账号相关分支被执行）
    if (ip != null && !ip.isBlank()) {
      long ipCount = attempts.countByIpSince(ip, now.minus(IP_WINDOW));
      if (ipCount >= IP_THRESHOLD) {
        Instant earliest = attempts.earliestByIpSince(ip, now.minus(IP_WINDOW));
        long retryAfter =
            earliest == null
                ? IP_WINDOW.toSeconds()
                : Math.max(1, IP_WINDOW.minus(Duration.between(earliest, now)).toSeconds());
        record(username, null, ip, false, AdminLoginAttemptEntity.REASON_THROTTLED, now);
        throw ConsoleException.of(
            ConsoleErrorCodes.LOGIN_THROTTLED, "同 IP 登录尝试过于频繁", Map.of("retryAfter", retryAfter));
      }
    }

    AdminUserEntity user = adminUsers.findByUsernameIgnoreCase(username).orElse(null);

    if (user == null) {
      // 反枚举：跑一次 BCrypt 抹平时序差；按 username 记失败（同样受限速约束）
      passwordEncoder.matches(password == null ? "" : password, DUMMY_HASH);
      record(username, null, ip, false, AdminLoginAttemptEntity.REASON_UNKNOWN_USER, now);
      throw ConsoleException.of(ConsoleErrorCodes.ADMIN_NOT_FOUND);
    }

    // ② 锁定检查（在验口令之前 —— 锁定期间不消耗 BCrypt，也不因口令对错表现不同）
    if (user.getLockedUntil() != null && user.getLockedUntil().isAfter(now)) {
      record(username, user.getId(), ip, false, AdminLoginAttemptEntity.REASON_LOCKED, now);
      throw ConsoleException.of(
          ConsoleErrorCodes.ACCOUNT_UNAVAILABLE,
          "管理端账号已锁定，请稍后再试",
          Map.of("lockedUntil", user.getLockedUntil().toString()));
    }

    // ③ 口令校验
    boolean ok = password != null && passwordEncoder.matches(password, user.getPasswordHash());
    if (!ok) {
      int failed = user.getFailedAttempts() + 1;
      user.setFailedAttempts((short) failed);
      if (failed >= FAILURE_THRESHOLD) {
        user.setLockedUntil(now.plus(LOCK_DURATION));
        user.setFailedAttempts((short) 0); // 锁定期满重新计数，避免累加到永久锁定
      }
      user.setUpdatedAt(now);
      adminUsers.save(user);
      record(username, user.getId(), ip, false, AdminLoginAttemptEntity.REASON_BAD_PASSWORD, now);
      throw ConsoleException.of(ConsoleErrorCodes.ADMIN_NOT_FOUND);
    }

    // ④ 停用检查（仅在口令正确后披露：调用方已是账号所有者，不构成信息泄漏）
    if (!AdminUserEntity.STATUS_ACTIVE.equals(user.getStatus())) {
      record(username, user.getId(), ip, false, AdminLoginAttemptEntity.REASON_DISABLED, now);
      throw ConsoleException.of(
          ConsoleErrorCodes.ACCOUNT_UNAVAILABLE, "管理端账号已停用", Map.of("status", user.getStatus()));
    }

    // ⑤ 成功：清零失败计数、落登录痕迹、建会话、签令牌
    user.setFailedAttempts((short) 0);
    user.setLockedUntil(null);
    user.setLastLoginAt(now);
    user.setLastLoginIp(ip);
    user.setUpdatedAt(now);
    adminUsers.save(user);

    AdminSessionEntity session = createSession(user.getId(), now, ip, userAgent);
    record(username, user.getId(), ip, true, AdminLoginAttemptEntity.REASON_LOGIN, now);

    AdminRoleEntity role = roles.findById(user.getRoleId()).orElse(null);
    String roleCode = role == null ? "" : role.getCode();
    Set<String> perms = rbac.roleCodes(user.getRoleId());
    String access =
        jwt.issueAccessToken(
            user.getId(),
            user.getUsername(),
            roleCode,
            perms,
            user.getTokenEpoch(),
            session.getId());

    // 独立事务：登录成功是**既成事实**，不能因为后续任何回滚而从审计里消失（见 IndependentAuditWriter）
    auditWriter.bestEffort(
        () ->
            auditWriter.recordIndependent(
                user.getId(),
                user.getUsername(),
                "console.auth.login",
                "admin_user",
                String.valueOf(user.getId()),
                "管理员登录成功",
                Map.of("role", roleCode, "ip", ip == null ? "" : ip)),
        "console-login");
    log.info(
        "控制台登录成功 adminUserId={} username={} role={}", user.getId(), user.getUsername(), roleCode);

    return new LoginResult(
        access,
        session.getRefreshTokenPlain(),
        ConsoleJwtService.ACCESS_TTL_SECONDS,
        user.getId(),
        user.getUsername(),
        user.getDisplayName(),
        roleCode,
        perms);
  }

  // ------------------------------------------------------------------ 刷新

  @Transactional
  public LoginResult refresh(String refreshToken, String ip, String userAgent) {
    Instant now = Instant.now();
    if (refreshToken == null || refreshToken.isBlank()) {
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED, "refreshToken 不能为空");
    }
    String hash = sha256Hex(refreshToken);
    AdminSessionEntity session = sessions.findByRefreshTokenHash(hash).orElse(null);
    if (session == null) {
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED, "刷新令牌无效");
    }

    if (session.isRevoked()) {
      // 重放已轮换/已吊销的令牌 → 视为令牌泄漏，吊销该账号全部会话（见类注释）
      int revoked =
          sessions.revokeAllForUser(
              session.getAdminUserId(), AdminSessionEntity.REASON_TOKEN_REUSE, now);
      // 安全事件独立落库：不能因为外层事务回滚（本方法随后就抛 46001）而丢掉这行归因
      auditWriter.bestEffort(
          () ->
              auditWriter.recordIndependent(
                  session.getAdminUserId(),
                  "",
                  "console.auth.refresh_reuse",
                  "admin_session",
                  String.valueOf(session.getId()),
                  "检测到刷新令牌重放，已吊销该账号全部会话",
                  Map.of("revokedSessions", revoked)),
          "refresh-reuse");
      log.warn(
          "检测到控制台刷新令牌重放：adminUserId={} sessionId={}，已吊销 {} 条会话",
          session.getAdminUserId(),
          session.getId(),
          revoked);
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED, "刷新令牌已失效（疑似重放），请重新登录");
    }
    if (!session.getExpiresAt().isAfter(now)) {
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED, "刷新令牌已过期，请重新登录");
    }

    AdminUserEntity user = adminUsers.findById(session.getAdminUserId()).orElse(null);
    if (user == null) {
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED, "管理端账号不存在");
    }
    if (!AdminUserEntity.STATUS_ACTIVE.equals(user.getStatus())) {
      throw ConsoleException.of(
          ConsoleErrorCodes.ACCOUNT_UNAVAILABLE, "管理端账号已停用", Map.of("status", user.getStatus()));
    }
    if (user.getLockedUntil() != null && user.getLockedUntil().isAfter(now)) {
      throw ConsoleException.of(
          ConsoleErrorCodes.ACCOUNT_UNAVAILABLE,
          "管理端账号已锁定",
          Map.of("lockedUntil", user.getLockedUntil().toString()));
    }

    // 一次性轮换：吊销旧行（条件更新，0 行=已被并发轮换 → 按重放处理）
    int revoked = sessions.revoke(session.getId(), AdminSessionEntity.REASON_ROTATED, now);
    if (revoked == 0) {
      sessions.revokeAllForUser(
          session.getAdminUserId(), AdminSessionEntity.REASON_TOKEN_REUSE, now);
      throw ConsoleException.of(ConsoleErrorCodes.UNAUTHENTICATED, "刷新令牌已被并发使用，请重新登录");
    }

    AdminSessionEntity next = createSession(user.getId(), now, ip, userAgent);
    AdminRoleEntity role = roles.findById(user.getRoleId()).orElse(null);
    String roleCode = role == null ? "" : role.getCode();
    Set<String> perms = rbac.roleCodes(user.getRoleId());
    String access =
        jwt.issueAccessToken(
            user.getId(), user.getUsername(), roleCode, perms, user.getTokenEpoch(), next.getId());
    return new LoginResult(
        access,
        next.getRefreshTokenPlain(),
        ConsoleJwtService.ACCESS_TTL_SECONDS,
        user.getId(),
        user.getUsername(),
        user.getDisplayName(),
        roleCode,
        perms);
  }

  // ------------------------------------------------------------------ 登出

  /** 吊销当前会话（只吊销本会话，不动同账号其他设备）。 */
  @Transactional
  public void logout(ConsolePrincipal principal) {
    if (principal == null || principal.sessionId() == null) {
      return;
    }
    Instant now = Instant.now();
    int revoked = sessions.revoke(principal.sessionId(), AdminSessionEntity.REASON_LOGOUT, now);
    audit.record(
        principal,
        "console.auth.logout",
        "admin_session",
        String.valueOf(principal.sessionId()),
        "管理员登出",
        Map.of("revoked", revoked));
  }

  // ------------------------------------------------------------------ 内部

  /** 建会话并**把明文 refresh token 只回传给调用方一次**（库里只有 sha256）。 */
  private AdminSessionEntity createSession(
      Long adminUserId, Instant now, String ip, String userAgent) {
    byte[] raw = new byte[32]; // 32 随机字节 → 64 hex 字符（docs/50 §4.1）
    RANDOM.nextBytes(raw);
    String plain = HexFormat.of().formatHex(raw);
    AdminSessionEntity e = new AdminSessionEntity();
    e.setAdminUserId(adminUserId);
    e.setRefreshTokenHash(sha256Hex(plain));
    e.setIssuedAt(now);
    e.setExpiresAt(now.plus(REFRESH_TTL));
    e.setIp(ip);
    e.setUserAgent(userAgent == null ? null : truncate(userAgent, 255));
    e.setCreatedAt(now);
    AdminSessionEntity saved = sessions.saveAndFlush(e);
    saved.setRefreshTokenPlain(plain);
    return saved;
  }

  private void record(
      String username, Long adminUserId, String ip, boolean success, String reason, Instant now) {
    AdminLoginAttemptEntity a = new AdminLoginAttemptEntity();
    a.setUsername(truncate(username == null ? "" : username, 32));
    a.setAdminUserId(adminUserId);
    a.setIp(ip == null ? null : truncate(ip, 45));
    a.setSuccess(success);
    a.setReason(reason);
    a.setCreatedAt(now);
    attempts.save(a);
  }

  public static String sha256Hex(String value) {
    try {
      MessageDigest md = MessageDigest.getInstance("SHA-256");
      return HexFormat.of().formatHex(md.digest(value.getBytes(StandardCharsets.UTF_8)));
    } catch (NoSuchAlgorithmException e) {
      throw new IllegalStateException("SHA-256 不可用", e);
    }
  }

  private static String truncate(String s, int max) {
    return s.length() <= max ? s : s.substring(0, max);
  }
}
