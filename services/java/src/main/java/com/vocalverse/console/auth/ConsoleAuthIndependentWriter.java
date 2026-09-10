package com.vocalverse.console.auth;

import com.vocalverse.console.rbac.AdminLoginAttemptEntity;
import com.vocalverse.console.rbac.AdminLoginAttemptRepository;
import com.vocalverse.console.rbac.AdminSessionRepository;
import com.vocalverse.console.rbac.AdminUserEntity;
import com.vocalverse.console.rbac.AdminUserRepository;
import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/**
 * 认证域的**独立事务写入器**：登录尝试流水、账号失败计数/锁定、会话族吊销。
 *
 * <h2>为什么这些写入不能待在业务事务里（2026-09-10 实测缺陷）</h2>
 *
 * <p>{@link ConsoleAuthService#login} 与 {@link ConsoleAuthService#refresh} 都是
 * {@code @Transactional}， 而它们在写完之后**必然要抛 {@code ConsoleException} 表示"拒绝"**；{@code ConsoleException}
 * 是 {@link RuntimeException}，所以 Spring 会把**整个事务**回滚 —— 连同刚刚写下的那行流水、刚累加的失败
 * 计数、刚盖上的锁定时间、刚吊销的会话。结果是三处安全控制在生产上**完全是空的**，而代码读起来每一处 都对（现象与原因离得很远，是本次最值得记的一条）：
 *
 * <table border="1">
 *   <tr><th>被静默回滚的写入</th><th>后果</th><th>谁先发现</th></tr>
 *   <tr><td>{@code admin_login_attempts} 失败流水</td><td>窗口计数恒为 0 → 同 IP 限流（20 次/5 分钟）
 *       永不触发，撞库可无限打</td><td>{@code ConsoleAuthApiTest#login_same_ip_throttled_after_twenty_attempts}</td></tr>
 *   <tr><td>{@code admin_users.failed_attempts} / {@code locked_until}</td><td>失败计数永远停在 0 →
 *       5 次锁号永不触发，**口令爆破不受任何限制**</td>
 *       <td>{@code ConsoleAuthApiTest#login_five_failures_lock_account}</td></tr>
 *   <tr><td>{@code admin_sessions} 会话族吊销</td><td>重放旧 refresh 虽然回了 46001，但新 refresh 仍然
 *       可用 → 「检测到令牌泄漏就吊销全部会话」形同虚设；更糟的是那行审计（走独立事务）**如实写着
 *       "已吊销 N 条会话"，而实际一条都没吊销**</td>
 *       <td>{@code ConsoleAuthApiTest#refresh_rotates_and_reuse_revokes_whole_family}</td></tr>
 * </table>
 *
 * <p>修法与 {@code IndependentAuditWriter} 同源、同理由：**「拒绝」是预期内的业务结果，而发生过的
 * 认证事件是既成事实**，不该因为这次请求以异常收场就从库里消失。所以这些写入各自开一个 {@code REQUIRES_NEW} 事务立即提交，与调用方的事务成败无关。
 *
 * <p><b>为什么单独一个类而不是在 {@code ConsoleAuthService} 里加几个 {@code REQUIRES_NEW} 私有方法</b>： ① Spring
 * 的事务代理不拦自调用，写在同类里等于没写；② 与 {@code IndependentAuditWriter} 同样的理由 ——
 * 把「事务内」与「事务外」两种语义分到两个类，让每一类都能被一句话审查完（本类：所有方法都在独立事务里写）。
 */
@Service
public class ConsoleAuthIndependentWriter {

  private final AdminUserRepository adminUsers;
  private final AdminLoginAttemptRepository attempts;
  private final AdminSessionRepository sessions;

  public ConsoleAuthIndependentWriter(
      AdminUserRepository adminUsers,
      AdminLoginAttemptRepository attempts,
      AdminSessionRepository sessions) {
    this.adminUsers = adminUsers;
    this.attempts = attempts;
    this.sessions = sessions;
  }

  /** 口令失败的处置结果：是否已触发锁定 / 锁定到什么时候（供日志与审计引用）。 */
  public record FailureOutcome(boolean locked, Instant lockedUntil) {}

  /**
   * 记一行登录尝试流水（成功或失败都记），**独立事务立即提交**。
   *
   * <p>限流与锁定都只认这张表的窗口计数（docs/50 §5.3.6，Redis 不参与），所以这行必须落库 ——
   * 包括「用户名不存在」的尝试：先爆破一堆用户名再挑真的，同样要吃限速（反枚举的反制措施）。
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public void recordAttempt(
      String username, Long adminUserId, String ip, boolean success, String reason, Instant now) {
    insertAttempt(username, adminUserId, ip, success, reason, now);
  }

  /**
   * 口令错误：落一行 {@code bad_password} 流水 **并** 累加账号失败计数，达到阈值即落锁。
   *
   * <p>计数与锁定在**同一个独立事务**里完成：两者必须同生共死，否则会出现「计数够了但没锁上」 （下一个请求再数一次仍然够，行为上表现为延迟一次锁定）。阈值与锁定时长取自 {@link
   * ConsoleAuthService} 的常量（策略只有一处定义，测试也钉的是那里）。流水行由私有的 {@code insertAttempt} 直接写在本事务里 —— **不是**调
   * {@code recordAttempt}：同类自调用不会走事务代理， 那种写法会让人误以为这里开了第二个事务。
   *
   * <p>锁上之后把计数清零：锁定期满后重新计数，避免旧失败累加到"永久锁定"（原实现的取舍，保留）。
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public FailureOutcome recordPasswordFailure(
      String username, Long adminUserId, String ip, Instant now) {
    Instant lockedUntil = null;
    AdminUserEntity user =
        adminUserId == null ? null : adminUsers.findById(adminUserId).orElse(null);
    if (user != null) {
      int failed = user.getFailedAttempts() + 1;
      if (failed >= ConsoleAuthService.FAILURE_THRESHOLD) {
        lockedUntil = now.plus(ConsoleAuthService.LOCK_DURATION);
        user.setLockedUntil(lockedUntil);
        user.setFailedAttempts((short) 0);
      } else {
        user.setFailedAttempts((short) failed);
      }
      user.setUpdatedAt(now);
      adminUsers.save(user);
    }
    insertAttempt(
        username, adminUserId, ip, false, AdminLoginAttemptEntity.REASON_BAD_PASSWORD, now);
    return new FailureOutcome(lockedUntil != null, lockedUntil);
  }

  /**
   * 吊销某账号**全部**未吊销会话（重放检测 / 并发轮换）。
   *
   * <p>调用方随后必然抛 46001，所以这里必须是独立事务 —— 否则"检测到令牌泄漏"的处理会被自己的 拒绝异常回滚掉，只剩一行说已吊销的审计。
   *
   * @return 实际吊销的行数
   */
  @Transactional(propagation = Propagation.REQUIRES_NEW)
  public int revokeAllSessions(Long adminUserId, String reason, Instant now) {
    return sessions.revokeAllForUser(adminUserId, reason, now);
  }

  /** 插一行尝试流水（无事务注解：跑在调用方的事务里，见 {@code recordPasswordFailure} 的说明）。 */
  private void insertAttempt(
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

  private static String truncate(String s, int max) {
    return s.length() <= max ? s : s.substring(0, max);
  }
}
