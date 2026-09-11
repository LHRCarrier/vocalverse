package com.vocalverse.console.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.support.AbstractConsoleApiTest;
import com.vocalverse.user.UserEntity;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * 跨端令牌闸门（docs/50 §4.1「{@code aud} 是硬闸」+ §14.2 的 Java 第 7 条）。
 *
 * <h2>为什么这个测试是整件事的重点</h2>
 *
 * <p>控制台与 App 共用同一个 HMAC 密钥（本地回退 {@code JWT_SECRET}；Python 侧需要用同一密钥验签控制台令牌）。
 * 因此**密钥本身不提供任何隔离**，隔离完全由两个 claim 检查承担：
 *
 * <ul>
 *   <li>控制台侧：{@link ConsoleJwtService#parse} 要求 {@code aud=vocalverse-console} 且 {@code
 *       typ=console-access}；
 *   <li>App 侧：{@code JwtAuthFilter.isForeignToken} 拒绝 {@code typ=console-access} 或任何外来 {@code aud}。
 * </ul>
 *
 * <p>这个测试是**唯一**能证明这两道闸门真的存在的证据。尤其是 (b)：控制台令牌的 {@code sub} 是 {@code admin_users.id}，而它可能与某个真实 App
 * 用户的 {@code users.id} 数值相同 —— 没有 App 侧闸门时，审核员可以用自己的控制台令牌冒充那个用户（发帖、读私信、改资料）。
 *
 * <p>(c) 是兼容性回归：既有 App 令牌**没有** {@code aud}，必须继续可用，否则线上所有人被登出。
 */
class ConsoleCrossTokenTest extends AbstractConsoleApiTest {

  private JsonNode getJson(String path, String token) throws Exception {
    MvcResult r = mockMvc.perform(get(path).header("Authorization", bearer(token))).andReturn();
    return json(r);
  }

  /**
   * 断言「被拒」，以 **HTTP 状态** 为主要证据。
   *
   * <p><b>为什么不能只断言 {@code code != 0}</b>（2026-09-10 实测踩坑）：过滤器层与安全层的 401/403 **不是
   * Envelope**（docs/api/envelope.md 的既有登记：过滤器层不经 {@code @RestControllerAdvice}）， 路径不存在时更是 Spring 默认
   * 404 体。这些响应体里**没有 `code` 字段**，而 Jackson 的 {@code MissingNode.asInt()} 返回 **0** —— 于是 {@code
   * assertNotEquals(0, code)} 会在 「确实被拒」的情况下报 `expected: not equal but was: <0>`，把通过的闸门读成失败的闸门。
   *
   * <p>正确写法：状态码是硬证据；**若**响应体带 Envelope（控制台链显式写的 46001 等），再额外校验 code 非 0。
   */
  private void assertRejected(String what, MvcResult r) throws Exception {
    int status = r.getResponse().getStatus();
    assertTrue(status == 401 || status == 403, what + " 应 401/403，实际 " + status);
    JsonNode root = json(r);
    JsonNode code = root.path("code");
    if (!code.isMissingNode() && !code.isNull()) {
      assertNotEquals(0, code.asInt(), what + " 若返回 Envelope，code 必须非 0：" + root);
    }
  }

  /** 造一个 App 用户并登录，返回 access token（走真实 /auth/login，不用手工签令牌）。 */
  private String appUserToken(String username) throws Exception {
    String body =
        String.format(
            "{\"username\":\"%s\",\"password\":\"password123\",\"nickname\":\"%s\",\"ageGroup\":\"adult\"}",
            username, username);
    MvcResult reg =
        mockMvc
            .perform(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(
        0,
        json(reg).path("code").asInt(),
        "注册应成功：" + reg.getResponse().getContentAsString(StandardCharsets.UTF_8));
    MvcResult login =
        mockMvc
            .perform(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"username\":\"%s\",\"password\":\"password123\"}", username)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode data = json(login).path("data");
    String token = data.path("accessToken").asText();
    assertFalse(token.isBlank(), "App 登录应返回 accessToken：" + json(login));
    return token;
  }

  // ------------------------------------------------------------------ (a)

  /** (a) App 令牌打控制台端点 → 46001（且不是 Spring 默认错误体）。 */
  @Test
  void app_token_rejected_on_console_endpoints() throws Exception {
    String appToken = appUserToken(uniqueName("appu"));

    JsonNode me = getJson("/api/v1/console/auth/me", appToken);
    assertEquals(
        ConsoleErrorCodes.UNAUTHENTICATED, me.path("code").asInt(), "App 令牌不得通过控制台鉴权：" + me);

    // 受权限保护的端点同样拒绝（先在过滤器层就拦掉，不会走到权限拦截器）
    JsonNode audit = getJson("/api/v1/console/audit-logs", appToken);
    assertEquals(ConsoleErrorCodes.UNAUTHENTICATED, audit.path("code").asInt(), audit.toString());

    MvcResult raw =
        mockMvc
            .perform(get("/api/v1/console/audit-logs").header("Authorization", bearer(appToken)))
            .andReturn();
    assertFalse(
        raw.getResponse().getContentAsString(StandardCharsets.UTF_8).contains("timestamp"),
        "不得是 Spring 默认错误体");
  }

  /**
   * (a′) 最危险的一种：控制台 {@code sub} 与某个真实 App 用户 id **数值相同**。
   *
   * <p>光靠「App 令牌被拒」不能说明问题 —— 必须证明「控制台令牌冒充 App 用户」也被拒， 否则控制台令牌仍可读该用户的数据。这里把 adminUserId 直接对齐到那个 App
   * 用户 id。
   */
  @Test
  @org.springframework.transaction.annotation.Transactional
  void console_token_with_matching_sub_cannot_impersonate_app_user() throws Exception {
    // 场景：控制台账号的 id 与某个**真实 App 用户**的 id 数值相同 —— 要证的是这种同名 sub
    // 也不能让控制台令牌变成那个用户。
    //
    // ⚠️ 怎么造这个场景本身就是个坑（2026-09-11 CI 两连红才收敛）：
    // `users.id` 与 `admin_users.id` 是两条**独立**的自增序列，"数值相同"只能显式指定 id。而
    //   ① 借用某个已注册 App 用户的 id → 该 id 可能已在 admin_users 里被别的测试占用
    //      （`Unique index or primary key violation: PRIMARY KEY ON admin_users(ID)`，CI 撞在 id=18）；
    //   ② 逐个注册新 App 用户去"撞"一个空闲 id → admin_users 稠密时连开 30 个也全被占（CI 第二轮就是这么红的）。
    // 两种都是**顺序依赖**：本地顺序不撞、CI 撞。所以改成按构造取：
    //   取两表 `max(id)` 的更大者 + 1000 —— 这个数值在两表里**不可能**已有行，
    //   两侧各原生插一行把它钉住，用例意图（sub 相同）一字不动，且不再依赖执行顺序。
    seedRbac();
    long sharedId = nextFreeSharedId();
    String appUsername = uniqueName("appu");
    insertAppUserWithExplicitId(sharedId, appUsername);
    AdminUserEntityRow row =
        insertAdminWithExplicitId(sharedId, uniqueName("csu"), superRoleCode());
    String consoleToken = login(row.username(), FIXTURE_PASSWORD);

    // 控制台令牌在控制台上可用
    assertEquals(0, getJson("/api/v1/console/auth/me", consoleToken).path("code").asInt());

    // 但拿它打 App 端点必须是「未认证」，绝不能变成那个 App 用户
    MvcResult r =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(consoleToken))).andReturn();
    assertRejected("控制台令牌绝不能通过 App 鉴权（sub 数值相同也不行）", r);
    assertFalse(
        json(r).path("data").path("username").asText("").equals(appUsername), "绝不能返回那个 App 用户的资料");
  }

  // ------------------------------------------------------------------ (b)

  /** (b) 控制台令牌打既有 App 端点 → 被拒（不得当作 App 用户）。 */
  @Test
  void console_token_rejected_on_existing_app_endpoints() throws Exception {
    String consoleToken = seedAdminAndLogin(uniqueName("csu"), superRoleCode());
    assertEquals(0, getJson("/api/v1/console/auth/me", consoleToken).path("code").asInt());

    for (String path :
        new String[] {
          // 说明：`/api/v1/users/me` 只支持 PATCH（UserController 只有 @PatchMapping("/me")），用 GET 探会命中
          // NoResourceFoundException → 40401「资源不存在」——那是「路径不存在」而非「令牌被拒」，
          // 会让本用例变成假通过（任何令牌都 40401）。故只用真正要求 App 身份的端点。
          "/auth/me", "/api/v1/community/posts", "/api/v1/tickets"
        }) {
      MvcResult r =
          mockMvc.perform(get(path).header("Authorization", bearer(consoleToken))).andReturn();
      assertRejected(path + " 不得接受控制台令牌", r);
    }
  }

  /**
   * (b′) 控制台令牌也拿不到旧管理端的 ADMIN 权限。
   *
   * <p>注意断言口径：`/api/v1/admin/**` 的**控制器已随旧管理端退役全部删除**，所以这个路径现在返回 **404**（不是
   * 401/403）——「控制台令牌在这里什么也拿不到」正是要证明的事。因此本用例断言 「不是 2xx 成功」，而不是套用 {@link #assertRejected}（它要求
   * 401/403）。
   */
  @Test
  void console_token_cannot_reach_legacy_admin_endpoints() throws Exception {
    String consoleToken = seedAdminAndLogin(uniqueName("csu"), superRoleCode());
    MvcResult r =
        mockMvc
            .perform(get("/api/v1/admin/songs").header("Authorization", bearer(consoleToken)))
            .andReturn();
    int status = r.getResponse().getStatus();
    assertTrue(
        status >= 400,
        "旧管理端路径必须失败（已退役 → 期望 404），实际 " + status + "：" + r.getResponse().getContentAsString());
    JsonNode code = json(r).path("code");
    if (!code.isMissingNode() && !code.isNull()) {
      assertNotEquals(0, code.asInt(), "若返回 Envelope，code 必须非 0");
    }
  }

  // ------------------------------------------------------------------ (c)

  /** (c) 既有 App 令牌（无 aud claim）继续可用 —— 加 aud 闸门不能把在线用户踢下线。 */
  @Test
  void legacy_app_token_without_aud_still_works() throws Exception {
    String appUsername = uniqueName("appu");
    String appToken = appUserToken(appUsername);

    // 既有令牌确实没有 aud（否则本测试的前提就不成立）
    io.jsonwebtoken.Claims claims = appJwt.parse(appToken);
    assertTrue(
        claims.get("aud") == null, "既有 App 令牌不应带 aud（带了说明签发侧改了行为，会登出所有在线用户）：" + claims.get("aud"));
    assertEquals(null, claims.get("typ", String.class), "既有 App 令牌不应带 typ=console-access");

    JsonNode me = getJson("/auth/me", appToken);
    assertEquals(0, me.path("code").asInt(), "无 aud 的既有 App 令牌必须继续可用：" + me);
    assertEquals(appUsername, me.path("data").path("username").asText());
  }

  /** (c′) App 令牌里带**本服务受众**的 aud 也应放行（为将来加 aud 留的兼容位）。 */
  @Test
  void app_token_with_app_audience_is_accepted() throws Exception {
    String appUsername = uniqueName("appu");
    appUserToken(appUsername);
    UserEntity u = users.findByUsernameIgnoreCase(appUsername).orElseThrow();

    String tokenWithAud =
        io.jsonwebtoken.Jwts.builder()
            .subject(String.valueOf(u.getId()))
            .audience()
            .add("vocalverse-app")
            .and()
            .claim("role", u.getRole())
            .issuedAt(java.util.Date.from(Instant.now()))
            .expiration(java.util.Date.from(Instant.now().plusSeconds(600)))
            .signWith(appJwtKey())
            .compact();

    JsonNode me = getJson("/auth/me", tokenWithAud);
    assertEquals(0, me.path("code").asInt(), "带 App 受众的令牌应放行：" + me);
  }

  /** (d) 造一个带**外来** aud 的 App 签名令牌（非 console typ）→ App 侧也必须拒绝。 */
  @Test
  void app_signed_token_with_foreign_audience_rejected() throws Exception {
    String appUsername = uniqueName("appu");
    appUserToken(appUsername);
    UserEntity u = users.findByUsernameIgnoreCase(appUsername).orElseThrow();

    String foreign =
        io.jsonwebtoken.Jwts.builder()
            .subject(String.valueOf(u.getId()))
            .audience()
            .add("some-other-service")
            .and()
            .claim("role", u.getRole())
            .issuedAt(java.util.Date.from(Instant.now()))
            .expiration(java.util.Date.from(Instant.now().plusSeconds(600)))
            .signWith(appJwtKey())
            .compact();

    MvcResult r =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(foreign))).andReturn();
    assertRejected("外来 aud 必须被拒（否则任何同密钥服务的令牌都能冒充用户）", r);
  }

  // ------------------------------------------------------------------ 辅助

  @org.springframework.beans.factory.annotation.Autowired
  private com.vocalverse.user.UserRepository users;

  @org.springframework.beans.factory.annotation.Autowired
  private com.vocalverse.config.JwtService appJwt;

  @org.springframework.beans.factory.annotation.Autowired
  private jakarta.persistence.EntityManager em;

  /**
   * 与本仓 application-test.yml 的 {@code vocalverse.jwt.secret} 一致。
   *
   * <p>测试里手工签令牌（模拟既有 App 令牌 / 外来 aud 令牌）必须用同一个密钥，否则签出来的令牌 在验签阶段就被拒，测试会「通过」但什么也没验证到（假绿）。
   */
  private javax.crypto.SecretKey appJwtKey() {
    return io.jsonwebtoken.security.Keys.hmacShaKeyFor(
        "vocalverse-dev-jwt-secret-0123456789abcdef".getBytes(StandardCharsets.UTF_8));
  }

  private record AdminUserEntityRow(Long id, String username) {}

  /**
   * 取一个在 {@code users} 与 {@code admin_users} 里都**不可能已存在**的 id。
   *
   * <p>两表 id 是独立序列，"两张表里都存在且数值相同"这个场景必须显式指定 id； 而"借某个已存在行的 id"会撞主键、且撞不撞取决于测试执行顺序（CI 两连红的根因）。 取两表
   * max(id) 之上的一段（+1000，留出同一用例外的余量）即可**按构造**避免冲突： identity 序列的当前值远小于它，测试期间也不会有人插到那里。
   */
  private long nextFreeSharedId() {
    Number maxUsers =
        (Number) em.createNativeQuery("SELECT COALESCE(MAX(id), 0) FROM users").getSingleResult();
    Number maxAdmins =
        (Number)
            em.createNativeQuery("SELECT COALESCE(MAX(id), 0) FROM admin_users").getSingleResult();
    return Math.max(maxUsers.longValue(), maxAdmins.longValue()) + 1000L;
  }

  /** 用原生 SQL 插入指定 id 的 {@code users} 行（显式 id 插入 IDENTITY 列，H2/PG 均支持）。 */
  private void insertAppUserWithExplicitId(long id, String username) {
    Instant now = Instant.now();
    // 必填列照 `UserEntity` 的 `nullable = false` 抄：username / password_hash / nickname / role / status
    // / created_at / updated_at（`email` 可空）。少一列就是 H2 的 "NULL not allowed for column ..."。
    em.createNativeQuery(
            "INSERT INTO users (id, username, password_hash, nickname, role, status,"
                + " created_at, updated_at)"
                + " VALUES (:id, :u, :h, :u, 'user', 'active', :now, :now)")
        .setParameter("id", id)
        .setParameter("u", username)
        .setParameter("h", passwordEncoder.encode(FIXTURE_PASSWORD))
        .setParameter("now", now)
        .executeUpdate();
    em.clear();
  }

  /** 用原生 SQL 插入指定 id 的 admin_users 行（显式 id 插入 IDENTITY 列，H2/PG 均支持）。 */
  private AdminUserEntityRow insertAdminWithExplicitId(Long id, String username, String roleCode) {
    var role = adminRoles.findByCode(roleCode).orElseThrow();
    String hash = passwordEncoder.encode(FIXTURE_PASSWORD);
    Instant now = Instant.now();
    em.createNativeQuery(
            "INSERT INTO admin_users (id, username, display_name, password_hash, role_id, status,"
                + " failed_attempts, token_epoch, created_at, updated_at)"
                + " VALUES (:id, :u, :u, :h, :r, 'active', 0, 0, :now, :now)")
        .setParameter("id", id)
        .setParameter("u", username)
        .setParameter("h", hash)
        .setParameter("r", role.getId())
        .setParameter("now", now)
        .executeUpdate();
    em.clear();
    return new AdminUserEntityRow(id, username);
  }
}
