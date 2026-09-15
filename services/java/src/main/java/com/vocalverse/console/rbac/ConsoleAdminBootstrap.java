package com.vocalverse.console.rbac;

import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Locale;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.annotation.Order;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

/**
 * 首个管理员的**一次性** bootstrap（docs/50 §8 讨论的「没有账号就什么都做不了」问题的落地）。
 *
 * <p>触发条件（全部满足才建号）：{@code admin_users} **表为空** 且 配置的 username/password 均非空白。
 *
 * <h2>为什么这样设计（三条安全约束）</h2>
 *
 * <ol>
 *   <li><b>opt-in</b>：默认 {@code VOICEVERSE_CONSOLE_BOOTSTRAP_USERNAME/PASSWORD} 为空 → <b>什么都不做</b>。
 *       绝不会出现「默认 admin/admin123」这种生产事故（这是同类系统最常见的入口漏洞）；
 *   <li><b>一次性</b>：只在表为空时生效。表里已有账号（哪怕只有一个）就不再建 —— 否则每次重启都会 把口令重置回环境变量里的值，等于把「口令轮换」变成「重启即回退」；
 *   <li><b>弱口令拒建</b>：长度 < 10、或等于常见弱口令清单、或与用户名相同 → <b>拒绝创建并明确说明原因</b> （日志含「为什么拒绝」，而不是静默跳过 ——
 *       静默会让运维以为建好了，然后对着登录页 46004 抓瞎）。
 * </ol>
 *
 * <p>口令只在环境变量里，日志**只打用户名**，绝不打口令或哈希（docs/50 §9.3 红线）。
 *
 * <p>顺序：{@code @Order(20)}，在 {@link RbacBootstrap}（{@code @Order(10)}）之后 —— 需要先有 super 角色。
 *
 * <p><b>测试专用夹具</b>：{@code com.vocalverse.support.AbstractConsoleApiTest} 直接调 {@link
 * com.vocalverse.console.auth.ConsoleAuthService} 依赖的仓库/编码器自建账号并登录，不走本 bootstrap （测试不该依赖「表为空」+
 * 环境变量这种一次性前提）。
 */
@Component
@Order(20)
public class ConsoleAdminBootstrap implements ApplicationRunner {

  private static final Logger log = LoggerFactory.getLogger(ConsoleAdminBootstrap.class);

  /** 明确拒绝的弱口令（小写比较；长度不足 10 的也一律拒绝，本清单只补「够长但众所周知」的）。 */
  private static final java.util.Set<String> WEAK_PASSWORDS =
      java.util.Set.of(
          "password",
          "password1",
          "password123",
          "administrator",
          "adminadmin",
          "qwertyuiop",
          "1234567890",
          "12345678901",
          "letmein123",
          "changeme123",
          "vocalverse",
          "vocalverse1");

  private static final int PASSWORD_MIN = 10;

  private final AdminUserRepository adminUsers;
  private final AdminRoleRepository roles;
  private final PasswordEncoder passwordEncoder;
  private final String username;
  private final String password;
  private final String displayName;

  public ConsoleAdminBootstrap(
      AdminUserRepository adminUsers,
      AdminRoleRepository roles,
      PasswordEncoder passwordEncoder,
      @Value("${vocalverse.console.bootstrap.username:}") String username,
      @Value("${vocalverse.console.bootstrap.password:}") String password,
      @Value("${vocalverse.console.bootstrap.display-name:}") String displayName) {
    this.adminUsers = adminUsers;
    this.roles = roles;
    this.passwordEncoder = passwordEncoder;
    this.username = username;
    this.password = password;
    this.displayName = displayName;
  }

  @Override
  @Transactional
  public void run(ApplicationArguments args) {
    if (isBlank(username) && isBlank(password)) {
      log.info(
          "控制台首个管理员 bootstrap 未启用（VOICEVERSE_CONSOLE_BOOTSTRAP_USERNAME/PASSWORD 为空）——"
              + "这是默认且推荐的状态；如需建号请显式配置后重启一次");
      return;
    }
    if (isBlank(username) || isBlank(password)) {
      log.error(
          "控制台 bootstrap 跳过：VOICEVERSE_CONSOLE_BOOTSTRAP_USERNAME 与 PASSWORD 必须**同时**配置"
              + "（只配一个无法判断意图，拒绝猜测）");
      return;
    }
    if (adminUsers.count() > 0) {
      log.info("控制台 bootstrap 跳过：admin_users 已有 {} 个账号（一次性语义，避免每次重启覆盖口令）", adminUsers.count());
      return;
    }

    String reason = weakPasswordReason(username, password);
    if (reason != null) {
      log.error(
          "控制台 bootstrap **拒绝创建账号** username={}：{}。"
              + "生产环境禁止用弱口令/默认口令建管理员号（这是同类系统最常见的入口漏洞）。"
              + "请设置足够强度的口令后重启，或改用 SQL/管理流程手工建号。",
          username,
          reason);
      return;
    }

    String roleCode = BuiltinRoles.SUPER;
    AdminRoleEntity role =
        roles
            .findByCode(roleCode)
            .orElseThrow(
                () -> new IllegalStateException("super 角色缺失：RbacBootstrap（@Order(10)）应先于本类执行"));

    Instant now = Instant.now();
    AdminUserEntity e = new AdminUserEntity();
    e.setUsername(username.trim());
    e.setDisplayName(isBlank(displayName) ? username.trim() : displayName.trim());
    e.setPasswordHash(passwordEncoder.encode(password));
    e.setRoleId(role.getId());
    e.setStatus(AdminUserEntity.STATUS_ACTIVE);
    e.setFailedAttempts((short) 0);
    e.setTokenEpoch(0);
    e.setCreatedBy(null);
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    AdminUserEntity saved = adminUsers.save(e);

    // 只打用户名与 id：口令与哈希绝不进日志（docs/50 §9.3）
    log.warn(
        "控制台首个管理员账号已创建：id={} username={} role={} —— 请立即登录并修改口令，"
            + "随后清空 VOICEVERSE_CONSOLE_BOOTSTRAP_PASSWORD 环境变量",
        saved.getId(),
        saved.getUsername(),
        roleCode);
  }

  /** 返回拒绝原因；null = 通过。 */
  static String weakPasswordReason(String username, String password) {
    if (password.length() < PASSWORD_MIN) {
      return "口令长度不足 " + PASSWORD_MIN + " 位（docs/50 §4.1 下限）";
    }
    if (WEAK_PASSWORDS.contains(password.toLowerCase(Locale.ROOT))) {
      return "口令在已知弱口令清单中";
    }
    if (password.equalsIgnoreCase(username)) {
      return "口令与用户名相同（docs/50 §4.1 明确禁止）";
    }
    if (password.getBytes(StandardCharsets.UTF_8).length < PASSWORD_MIN) {
      return "口令字节长度不足（多字节字符场景）";
    }
    return null;
  }

  private static boolean isBlank(String s) {
    return s == null || s.isBlank();
  }
}
