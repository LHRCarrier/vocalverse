package com.vocalverse.support;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.common.dto.Envelope;
import com.vocalverse.console.auth.ConsoleJwtService;
import com.vocalverse.console.rbac.AdminRoleEntity;
import com.vocalverse.console.rbac.AdminRolePermissionEntity;
import com.vocalverse.console.rbac.AdminRolePermissionRepository;
import com.vocalverse.console.rbac.AdminRoleRepository;
import com.vocalverse.console.rbac.AdminUserEntity;
import com.vocalverse.console.rbac.AdminUserRepository;
import com.vocalverse.console.rbac.BuiltinRoles;
import com.vocalverse.console.rbac.PermissionCatalog;
import com.vocalverse.console.rbac.RbacBootstrap;
import com.vocalverse.console.rbac.RbacService;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 控制台 API 测试公共设施（docs/50 §14.2 的 Java 清单 7~12 条）。
 *
 * <p>不复用 {@link AbstractAdminApiTest}：那个基类播种的是 **App 用户**（{@code users} + role=admin），
 * 而控制台是**独立身份**（{@code admin_users}）。两者混在一个基类里会让「控制台测试其实在用 App 身份」 这种错误长期不可见。
 *
 * <h2>为什么手工播种而不是走 ConsoleAdminBootstrap</h2>
 *
 * <p>bootstrap 的前置条件是「{@code admin_users} 表为空」+ 环境变量，属于**生产一次性**路径。 测试依赖它意味着：同一 JVM
 * 里第二个测试类就建不出账号了（表已非空）。所以测试夹具直接建行 + 调登录接口， 这也正是 docs/50 §8 要求的「test-only fixture path」。
 *
 * <p>角色/权限目录走 {@link RbacBootstrap}（幂等），保证测试用的权限矩阵与生产 seed 完全一致 —— 手工在测试里写权限矩阵会让「seed 写错了」这类缺陷测不出来。
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public abstract class AbstractConsoleApiTest {

  @Autowired protected MockMvc mockMvc;
  @Autowired protected com.fasterxml.jackson.databind.ObjectMapper objectMapper;
  @Autowired protected AdminUserRepository adminUsers;
  @Autowired protected AdminRoleRepository adminRoles;
  @Autowired protected AdminRolePermissionRepository rolePermissions;
  @Autowired protected PasswordEncoder passwordEncoder;
  @Autowired protected ConsoleJwtService consoleJwt;
  @Autowired protected RbacService rbac;
  @Autowired protected RbacBootstrap rbacBootstrap;

  /** 夹具口令（真实 BCrypt 哈希；不是环境变量）。 */
  public static final String FIXTURE_PASSWORD = "console-fixture-pw-1";

  /** 唯一化用户名（避免跨测试类/跨方法撞 uq_admin_users_username_lower）。 */
  private static final AtomicLong SEQ = new AtomicLong(System.nanoTime() % 1_000_000L);

  protected static String uniqueName(String prefix) {
    return prefix + SEQ.incrementAndGet();
  }

  // ------------------------------------------------------------------ 夹具

  /** 触发幂等 seed（权限目录 + 4 内置角色），使 rbac 可用。 */
  protected void seedRbac() {
    rbacBootstrap.run(null);
  }

  protected AdminRoleEntity role(String code) {
    seedRbac();
    return adminRoles
        .findByCode(code)
        .orElseThrow(() -> new IllegalStateException("内置角色缺失：" + code));
  }

  /**
   * 建一个管理端账号（fixture 路径）。
   *
   * @param roleCode 内置角色 code（super/ops/operator/moderator）
   */
  protected AdminUserEntity seedAdmin(String username, String roleCode) {
    AdminRoleEntity r = role(roleCode);
    Instant now = Instant.now();
    AdminUserEntity e = new AdminUserEntity();
    e.setUsername(username);
    e.setDisplayName(username);
    e.setPasswordHash(passwordEncoder.encode(FIXTURE_PASSWORD));
    e.setRoleId(r.getId());
    e.setStatus(AdminUserEntity.STATUS_ACTIVE);
    e.setFailedAttempts((short) 0);
    e.setTokenEpoch(0);
    e.setCreatedAt(now);
    e.setUpdatedAt(now);
    return adminUsers.save(e);
  }

  /** 建账号并登录，返回 access token。 */
  protected String seedAdminAndLogin(String username, String roleCode) throws Exception {
    seedAdmin(username, roleCode);
    return login(username, FIXTURE_PASSWORD);
  }

  // ------------------------------------------------------------------ 请求助手

  protected String bearer(String token) {
    return "Bearer " + token;
  }

  protected JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  /**
   * POST /api/v1/console/auth/login，返回完整 Envelope JSON。
   *
   * <p>用一次性 IP（{@link #freshTestIp()}）：见下方关于限流窗口污染的说明。
   */
  protected JsonNode loginRaw(String username, String password) throws Exception {
    return loginRawWithIp(username, password, freshTestIp());
  }

  /**
   * 每次调用一个**新的** X-Forwarded-For，避免测试之间互相污染同 IP 限流窗口。
   *
   * <p>踩坑（实测）：控制台登录有「同 IP 20 次 / 5 分钟」限流，而它的计数落在**共享的 H2 库**里，
   * 默认 remoteAddr 恒为同一个值 → 整个测试套件跑下来前 20 次登录成功、之后**所有**控制台测试
   * 全部 46008（包括那些根本不测限流的用例）。这不是偶发：只要套件里再有第 21 次登录就必然发生。
   * 单测里「每个用例用自己的 IP」既隔离了限流状态，又不削弱限流用例本身
   * （{@code login_same_ip_throttled_after_twenty_attempts} 显式钉一个固定 IP 并打满窗口）。
   */
  private static final AtomicLong IP_SEQ = new AtomicLong(1);

  /** 测试默认 IP：每次不同，保证不撞限流窗口。 */
  protected static String freshTestIp() {
    long n = IP_SEQ.incrementAndGet();
    return "10." + ((n / 65536) % 250 + 1) + "." + ((n / 256) % 250 + 1) + "." + (n % 250 + 1);
  }

  /** 登录并断言成功，返回 access token（用一次性 IP，避免污染限流窗口）。 */
  protected String login(String username, String password) throws Exception {
    return loginWithIp(username, password, freshTestIp());
  }

  /**
   * 带 {@code X-Forwarded-For} 的登录。
   *
   * <p>IP 限流用例必须能控制 IP：{@code ConsoleRequestContext.clientIp()} 取 XFF 第一跳 （网关已设置该头，直连时用
   * remoteAddr）。默认 MockMvc 的 remoteAddr 是 {@code 127.0.0.1}， 若限流用例占满它，同 JVM 内其他类的登录会被误伤 ——
   * 所以限流用例一律显式伪造 XFF。
   */
  protected JsonNode loginRawWithIp(String username, String password, String ip) throws Exception {
    var req =
        post("/api/v1/console/auth/login")
            .contentType(MediaType.APPLICATION_JSON)
            .content(
                objectMapper.writeValueAsBytes(Map.of("username", username, "password", password)));
    if (ip != null) {
      req = req.header("X-Forwarded-For", ip);
    }
    MvcResult r = mockMvc.perform(req).andReturn();
    return json(r);
  }

  protected String loginWithIp(String username, String password, String ip) throws Exception {
    JsonNode root = loginRawWithIp(username, password, ip);
    assertEquals(0, root.path("code").asInt(), "登录应成功：" + root);
    return root.path("data").path("token").path("accessToken").asText();
  }

  /** 登录并返回整个 data（含 refreshToken）。 */
  protected JsonNode loginData(String username, String password) throws Exception {
    JsonNode root = loginRaw(username, password);
    assertEquals(0, root.path("code").asInt(), "登录应成功：" + root);
    return root.path("data");
  }

  protected static Envelope<?> envelope(int code, String message) {
    return Envelope.error(code, message);
  }

  // ------------------------------------------------------------------ 权限目录自证

  /** 权限码 → id（测试里手工造自定义角色用）。 */
  protected Map<String, Long> permissionIds(List<String> codes) {
    Map<String, Long> out = new LinkedHashMap<>();
    for (String code : codes) {
      out.put(code, rbac.requirePermissionId(code));
    }
    return out;
  }

  /** 建一个只持有指定权限码的自定义角色（RBAC 拒绝用例用）。 */
  protected AdminRoleEntity customRole(String code, List<String> permissionCodes) {
    seedRbac();
    Instant now = Instant.now();
    AdminRoleEntity r = new AdminRoleEntity();
    r.setCode(code);
    r.setName(code);
    r.setDescription("test role");
    r.setBuiltin(false);
    r.setRank((short) 50);
    r.setCreatedAt(now);
    r.setUpdatedAt(now);
    r = adminRoles.save(r);
    Map<String, Long> ids = permissionIds(permissionCodes);
    for (Long pid : ids.values()) {
      rolePermissions.save(new AdminRolePermissionEntity(r.getId(), pid, now));
    }
    rbac.invalidate(true);
    return r;
  }

  /** 权限目录大小（自证用；须为 35）。 */
  protected int catalogSize() {
    return PermissionCatalog.size();
  }

  protected String superRoleCode() {
    return BuiltinRoles.SUPER;
  }
}
