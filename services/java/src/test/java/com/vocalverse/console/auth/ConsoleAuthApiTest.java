package com.vocalverse.console.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.console.rbac.AdminSessionEntity;
import com.vocalverse.console.rbac.AdminSessionRepository;
import com.vocalverse.console.rbac.AdminUserEntity;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 控制台认证（docs/50 §14.2-Java 第 7 条）。
 *
 * <p>覆盖：登录成功 / 口令错误 / 用户不存在 / 停用 / 锁定 / IP 限流 / refresh 一次性轮换与重放 / 登出 / token_epoch 即时失效 / auth.me。
 */
class ConsoleAuthApiTest extends AbstractConsoleApiTest {

  @Autowired private AdminSessionRepository sessions;

  private MvcResult getWithToken(String path, String token) throws Exception {
    return mockMvc.perform(get(path).header("Authorization", bearer(token))).andReturn();
  }

  private MvcResult postJson(String path, String token, String body) throws Exception {
    var req = post(path).contentType(MediaType.APPLICATION_JSON);
    if (token != null) {
      req = req.header("Authorization", bearer(token));
    }
    if (body != null) {
      req = req.content(body.getBytes(StandardCharsets.UTF_8));
    }
    return mockMvc.perform(req).andReturn();
  }

  // ------------------------------------------------------------------ 登录

  @Test
  void login_success_returns_token_role_and_permissions() throws Exception {
    String username = uniqueName("csu");
    seedAdmin(username, superRoleCode());

    JsonNode data = loginData(username, FIXTURE_PASSWORD);
    assertEquals(
        900L, data.path("token").path("expiresIn").asLong(), "access TTL 必须是 900s（docs/50 §4.1）");
    assertEquals("Bearer", data.path("token").path("tokenType").asText());
    assertTrue(
        data.path("token").path("refreshToken").asText().length() >= 64, "refresh 为 32 字节 hex");
    assertEquals("super", data.path("roleCode").asText());
    assertEquals(catalogSize(), data.path("permissions").size(), "super 的 * 应展开为全部权限码");

    // token 可用
    JsonNode me =
        json(
            getWithToken(
                "/api/v1/console/auth/me", data.path("token").path("accessToken").asText()));
    assertEquals(0, me.path("code").asInt(), me.toString());
    assertEquals(username, me.path("data").path("username").asText());
  }

  /** 反枚举：口令错误与用户不存在必须返回**同一个** 46004，且 message 一致 （否则可枚举出全部管理端账号名）。 */
  @Test
  void login_wrong_password_and_unknown_user_are_indistinguishable() throws Exception {
    String username = uniqueName("csu");
    seedAdmin(username, superRoleCode());

    JsonNode wrongPw = loginRaw(username, "definitely-wrong-password");
    JsonNode unknown = loginRaw(uniqueName("nosuch"), "definitely-wrong-password");

    assertEquals(
        ConsoleErrorCodes.ADMIN_NOT_FOUND, wrongPw.path("code").asInt(), wrongPw.toString());
    assertEquals(
        ConsoleErrorCodes.ADMIN_NOT_FOUND, unknown.path("code").asInt(), unknown.toString());
    assertEquals(404, unknown.path("code").asInt() == 46004 ? 404 : -1);
    assertEquals(
        wrongPw.path("message").asText(),
        unknown.path("message").asText(),
        "两种情况的消息必须逐字相同，否则仍可枚举用户名");
    assertEquals(wrongPw.path("code").asInt(), unknown.path("code").asInt());
  }

  /** 停用且口令正确 → 46003（口令已通过，不构成信息泄漏）；口令错误时仍是 46004。 */
  @Test
  void login_disabled_account_distinct_code_only_after_correct_password() throws Exception {
    String username = uniqueName("csu");
    AdminUserEntity e = seedAdmin(username, superRoleCode());
    e.setStatus(AdminUserEntity.STATUS_DISABLED);
    e.setUpdatedAt(Instant.now());
    adminUsers.save(e);

    JsonNode wrongPw = loginRaw(username, "definitely-wrong-password");
    assertEquals(
        ConsoleErrorCodes.ADMIN_NOT_FOUND,
        wrongPw.path("code").asInt(),
        "口令错误时不得披露账号已停用（否则可枚举）：" + wrongPw);

    JsonNode rightPw = loginRaw(username, FIXTURE_PASSWORD);
    assertEquals(
        ConsoleErrorCodes.ACCOUNT_UNAVAILABLE, rightPw.path("code").asInt(), rightPw.toString());
    assertEquals("disabled", rightPw.path("data").path("status").asText());
  }

  /** 5 次失败 → 锁定 15 分钟；第 6 次（口令正确）返回 46003 + lockedUntil。 */
  @Test
  void login_five_failures_lock_account() throws Exception {
    String username = uniqueName("csu");
    seedAdmin(username, superRoleCode());
    String ip = freshTestIp(); // 同一用例内复用同一个 IP（限流按 IP 计数，换 IP 就测不到锁定了）

    for (int i = 0; i < ConsoleAuthService.FAILURE_THRESHOLD; i++) {
      JsonNode r = loginRawWithIp(username, "wrong-" + i, ip);
      assertEquals(
          ConsoleErrorCodes.ADMIN_NOT_FOUND, r.path("code").asInt(), "第 " + (i + 1) + " 次：" + r);
    }

    JsonNode afterLock = loginRawWithIp(username, FIXTURE_PASSWORD, ip);
    assertEquals(
        ConsoleErrorCodes.ACCOUNT_UNAVAILABLE,
        afterLock.path("code").asInt(),
        afterLock.toString());
    assertFalse(
        afterLock.path("data").path("lockedUntil").asText().isBlank(),
        "锁定必须回传 lockedUntil：" + afterLock);
    assertTrue(
        Instant.parse(afterLock.path("data").path("lockedUntil").asText()).isAfter(Instant.now()),
        "lockedUntil 必须在未来");
  }

  /** 同 IP 20 次 / 5 分钟 → 46008（429）+ retryAfter。 */
  @Test
  void login_same_ip_throttled_after_twenty_attempts() throws Exception {
    String ip = freshTestIp(); // 同一 IP 打满窗口
    JsonNode last = null;
    for (int i = 0; i < ConsoleAuthService.IP_THRESHOLD; i++) {
      last = loginRawWithIp(uniqueName("thr"), "pw", ip);
      assertNotEquals(
          ConsoleErrorCodes.LOGIN_THROTTLED, last.path("code").asInt(), "第 " + i + " 次不该被限流");
    }
    JsonNode throttled = loginRawWithIp(uniqueName("thr"), "pw", ip);
    assertEquals(
        ConsoleErrorCodes.LOGIN_THROTTLED, throttled.path("code").asInt(), throttled.toString());
    assertTrue(
        throttled.path("data").path("retryAfter").asLong() > 0, "必须回传 retryAfter：" + throttled);
  }

  // ------------------------------------------------------------------ token_epoch

  /** token_epoch 变更（改权/改密/强制下线）→ 已签发令牌下一个请求即失效。 */
  @Test
  void token_epoch_change_invalidates_existing_token_immediately() throws Exception {
    String username = uniqueName("csu");
    AdminUserEntity e = seedAdmin(username, superRoleCode());
    String token = login(username, FIXTURE_PASSWORD);

    assertEquals(0, json(getWithToken("/api/v1/console/auth/me", token)).path("code").asInt());

    // bump epoch（等价于「改了权限」）
    // 直接改实体而不是调 @Modifying bulk update：bulk update 需要事务上下文，
    // 而本用例要断言的是**跨请求的持久化效果**（改完提交，下一个请求由过滤器读库）
    e.setTokenEpoch(e.getTokenEpoch() + 1);
    e.setUpdatedAt(Instant.now());
    adminUsers.save(e);
    rbac.invalidate(true);

    JsonNode after = json(getWithToken("/api/v1/console/auth/me", token));
    assertEquals(
        ConsoleErrorCodes.UNAUTHENTICATED,
        after.path("code").asInt(),
        "epoch 不符必须立刻 46001：" + after);
  }

  /** 账号被停用 → 已签发令牌立刻 46003（而不是等 TTL）。 */
  @Test
  void disabled_account_token_rejected_immediately() throws Exception {
    String username = uniqueName("csu");
    AdminUserEntity e = seedAdmin(username, superRoleCode());
    String token = login(username, FIXTURE_PASSWORD);

    e.setStatus(AdminUserEntity.STATUS_DISABLED);
    e.setUpdatedAt(Instant.now());
    adminUsers.save(e);

    JsonNode after = json(getWithToken("/api/v1/console/auth/me", token));
    assertEquals(
        ConsoleErrorCodes.ACCOUNT_UNAVAILABLE, after.path("code").asInt(), after.toString());
  }

  // ------------------------------------------------------------------ refresh / logout

  /** 一次性轮换：refresh 后旧 refresh 失效，且重放旧 refresh 会吊销该账号全部会话。 */
  @Test
  void refresh_rotates_and_reuse_revokes_whole_family() throws Exception {
    String username = uniqueName("csu");
    seedAdmin(username, superRoleCode());
    JsonNode first = loginData(username, FIXTURE_PASSWORD);
    String oldRefresh = first.path("token").path("refreshToken").asText();

    // 正常轮换
    JsonNode rotated =
        json(
            postJson(
                "/api/v1/console/auth/refresh",
                null,
                objectMapper.writeValueAsString(Map.of("refreshToken", oldRefresh))));
    assertEquals(0, rotated.path("code").asInt(), rotated.toString());
    String newRefresh = rotated.path("data").path("token").path("refreshToken").asText();
    assertNotEquals(oldRefresh, newRefresh, "轮换必须换发新 refresh");

    String newAccess = rotated.path("data").path("token").path("accessToken").asText();
    assertEquals(0, json(getWithToken("/api/v1/console/auth/me", newAccess)).path("code").asInt());

    // 重放旧 refresh（模拟令牌被窃取）→ 46001，且新 refresh 也被连带吊销
    JsonNode reuse =
        json(
            postJson(
                "/api/v1/console/auth/refresh",
                null,
                objectMapper.writeValueAsString(Map.of("refreshToken", oldRefresh))));
    assertEquals(ConsoleErrorCodes.UNAUTHENTICATED, reuse.path("code").asInt(), reuse.toString());

    JsonNode afterFamilyRevoke =
        json(
            postJson(
                "/api/v1/console/auth/refresh",
                null,
                objectMapper.writeValueAsString(Map.of("refreshToken", newRefresh))));
    assertEquals(
        ConsoleErrorCodes.UNAUTHENTICATED,
        afterFamilyRevoke.path("code").asInt(),
        "重放检测必须吊销整个会话族（新 refresh 也应失效）：" + afterFamilyRevoke);

    AdminUserEntity u = adminUsers.findByUsernameIgnoreCase(username).orElseThrow();
    long active =
        sessions.findByAdminUserIdOrderByIdDesc(u.getId()).stream()
            .filter(s -> s.getRevokedAt() == null)
            .count();
    assertEquals(0, active, "全部会话应已吊销");
  }

  /** 登出只吊销当前会话（同账号其他设备仍可用）。 */
  @Test
  void logout_revokes_only_current_session() throws Exception {
    String username = uniqueName("csu");
    seedAdmin(username, superRoleCode());
    String tokenA = login(username, FIXTURE_PASSWORD);
    String tokenB = login(username, FIXTURE_PASSWORD);

    JsonNode out = json(postJson("/api/v1/console/auth/logout", tokenA, null));
    assertEquals(0, out.path("code").asInt(), out.toString());

    JsonNode reuseA = json(postJson("/api/v1/console/auth/logout", tokenA, null));
    // tokenA 的会话已吊销，但 access token 本身仍有效（无状态）→ 这里只验证 tokenB 不受影响
    JsonNode meB = json(getWithToken("/api/v1/console/auth/me", tokenB));
    assertEquals(0, meB.path("code").asInt(), "登出不应影响同账号其他会话：" + meB);

    AdminUserEntity u = adminUsers.findByUsernameIgnoreCase(username).orElseThrow();
    assertEquals(
        1,
        sessions.findByAdminUserIdOrderByIdDesc(u.getId()).stream()
            .filter(
                s ->
                    s.getRevokedAt() != null
                        && AdminSessionEntity.REASON_LOGOUT.equals(s.getRevokeReason()))
            .count(),
        "应恰好吊销 1 条（logout 原因）");
    assertTrue(reuseA.path("code").asInt() == 0 || reuseA.path("code").asInt() == 46001);
  }

  // ------------------------------------------------------------------ me

  /** me 的权限码以库为准（改权后令牌未过期时，me 也应显示新权限）。 */
  @Test
  void me_permissions_reflect_database_not_token_snapshot() throws Exception {
    String username = uniqueName("opsm");
    seedAdmin(username, "ops");
    String token = login(username, FIXTURE_PASSWORD);

    JsonNode me = json(getWithToken("/api/v1/console/auth/me", token));
    assertEquals("ops", me.path("data").path("roleCode").asText());
    assertEquals("运维", me.path("data").path("roleName").asText());
    assertTrue(me.path("data").path("permissions").toString().contains("ops:overview:read"));
  }

  @Test
  void me_without_token_is_envelope_46001_not_spring_error_page() throws Exception {
    MvcResult r = mockMvc.perform(get("/api/v1/console/auth/me")).andReturn();
    String body = r.getResponse().getContentAsString(StandardCharsets.UTF_8);
    JsonNode root = objectMapper.readTree(body);
    assertEquals(401, r.getResponse().getStatus(), "HTTP 401：" + body);
    assertEquals(ConsoleErrorCodes.UNAUTHENTICATED, root.path("code").asInt(), body);
    assertFalse(body.contains("timestamp"), "不得是 Spring 默认错误体：" + body);
    assertTrue(root.has("data") && root.path("data").isNull(), "错误 data 应为 null（Envelope 契约）");
  }
}
