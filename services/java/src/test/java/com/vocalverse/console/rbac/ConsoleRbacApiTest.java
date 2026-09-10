package com.vocalverse.console.rbac;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * RBAC 拒绝与角色守卫（docs/50 §14.2-Java 第 8 条 + §4.2 + §10.2）。
 *
 * <p>重点：(1) 缺权限码 → 46002 且 {@code data.required} 回传**具体**的码； (2) {@code super} 的 {@code *} 通配生效；(3)
 * 反提权（不能改自己的角色、不能自己给自己发 super）； (4) 内置角色不可删。
 */
class ConsoleRbacApiTest extends AbstractConsoleApiTest {

  private MvcResult perform(
      org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder req, String token)
      throws Exception {
    return mockMvc.perform(req.header("Authorization", bearer(token))).andReturn();
  }

  private JsonNode getJson(String path, String token) throws Exception {
    return json(perform(get(path), token));
  }

  private JsonNode postJson(String path, String token, String body) throws Exception {
    return json(
        perform(
            post(path)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body.getBytes(StandardCharsets.UTF_8)),
            token));
  }

  private JsonNode patchJson(String path, String token, String body) throws Exception {
    return json(
        perform(
            org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch(path)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body.getBytes(StandardCharsets.UTF_8)),
            token));
  }

  // ------------------------------------------------------------------ 46002

  /** 缺码 → 46002 + data.required；且该拒绝会落审计（result=denied）。 */
  @Test
  void missing_permission_returns_46002_with_required_code() throws Exception {
    // 只给「看内容」的码，不给审计读
    String roleCode = uniqueName("role");
    customRole(roleCode, List.of(PermissionCatalog.CONTENT_SONG_READ));
    String token = seedAdminAndLogin(uniqueName("csu"), roleCode);

    JsonNode denied = getJson("/api/v1/console/audit-logs", token);
    assertEquals(
        ConsoleErrorCodes.PERMISSION_DENIED, denied.path("code").asInt(), denied.toString());
    assertEquals(
        PermissionCatalog.CONSOLE_AUDIT_READ,
        denied.path("data").path("required").asText(),
        "必须回传所需的具体权限码：" + denied);

    // 允许的端点正常
    assertEquals(0, getJson("/api/v1/console/content/songs", token).path("code").asInt());
  }

  /** super 的 {@code *} 通配展开 → 全端点可访问（含后续新增的码）。 */
  @Test
  void super_wildcard_grants_everything() throws Exception {
    String username = uniqueName("csu");
    seedAdmin(username, superRoleCode());
    String token = login(username, FIXTURE_PASSWORD);

    for (String path :
        List.of(
            "/api/v1/console/admins",
            "/api/v1/console/roles",
            "/api/v1/console/permissions",
            "/api/v1/console/audit-logs",
            "/api/v1/console/moderation/cases",
            "/api/v1/console/content/songs",
            "/api/v1/console/content/publish-events")) {
      assertEquals(0, getJson(path, token).path("code").asInt(), path + " 应可访问（super 通配）");
    }
  }

  /** 内置 4 角色的权限边界逐个核对（防止 seed 矩阵写错）。 */
  @Test
  void builtin_roles_have_expected_boundaries() throws Exception {
    String opsToken = seedAdminAndLogin(uniqueName("cso"), "ops");
    assertEquals(0, getJson("/api/v1/console/audit-logs", opsToken).path("code").asInt(), "运维有审计读");
    assertEquals(
        ConsoleErrorCodes.PERMISSION_DENIED,
        getJson("/api/v1/console/content/songs", opsToken).path("code").asInt(),
        "运维不该有内容读");

    String opToken = seedAdminAndLogin(uniqueName("cso"), "operator");
    assertEquals(
        0, getJson("/api/v1/console/content/songs", opToken).path("code").asInt(), "运营有歌曲读");
    assertEquals(
        ConsoleErrorCodes.PERMISSION_DENIED,
        getJson("/api/v1/console/moderation/cases", opToken).path("code").asInt(),
        "运营不该有审核队列读");

    String modToken = seedAdminAndLogin(uniqueName("csm"), "moderator");
    assertEquals(
        0, getJson("/api/v1/console/moderation/cases", modToken).path("code").asInt(), "审核有队列读");
    assertEquals(
        0, getJson("/api/v1/console/content/songs", modToken).path("code").asInt(), "审核有歌曲只读");
    assertEquals(
        ConsoleErrorCodes.PERMISSION_DENIED,
        getJson("/api/v1/console/admins", modToken).path("code").asInt(),
        "审核不该能看管理员账号");
  }

  // ------------------------------------------------------------------ 反提权

  /** 不能修改自己的 roleId（否则任何持 console:admin:write 的角色一次请求即可自我提权）。 */
  @Test
  void cannot_change_own_role() throws Exception {
    String roleCode = uniqueName("role");
    customRole(
        roleCode,
        List.of(PermissionCatalog.CONSOLE_ADMIN_WRITE, PermissionCatalog.CONSOLE_ROLE_READ));
    String username = uniqueName("csu");
    AdminUserEntity me = seedAdmin(username, roleCode);
    String token = login(username, FIXTURE_PASSWORD);
    var superRole = adminRoles.findByCode(superRoleCode()).orElseThrow();

    JsonNode r =
        patchJson(
            "/api/v1/console/admins/" + me.getId(),
            token,
            objectMapper.writeValueAsString(Map.of("roleId", superRole.getId())));

    assertEquals(ConsoleErrorCodes.INVALID_PARAM, r.path("code").asInt(), "必须被拒：" + r);
    assertEquals(
        roleCode,
        adminRoles
            .findById(adminUsers.findById(me.getId()).orElseThrow().getRoleId())
            .orElseThrow()
            .getCode(),
        "角色不得被改动");
  }

  /** 非 super 不能给他人发 super（否则 console:admin:write 等于 super）。 */
  @Test
  void non_super_cannot_grant_super_role() throws Exception {
    String roleCode = uniqueName("role");
    customRole(roleCode, List.of(PermissionCatalog.CONSOLE_ADMIN_WRITE));
    String actorToken = seedAdminAndLogin(uniqueName("csu"), roleCode);
    var victim = seedAdmin(uniqueName("csv"), "ops");
    var superRole = adminRoles.findByCode(superRoleCode()).orElseThrow();

    JsonNode r =
        patchJson(
            "/api/v1/console/admins/" + victim.getId(),
            actorToken,
            objectMapper.writeValueAsString(Map.of("roleId", superRole.getId())));

    assertEquals(ConsoleErrorCodes.INVALID_PARAM, r.path("code").asInt(), "必须被拒：" + r);
    assertEquals(
        "ops",
        adminRoles
            .findById(adminUsers.findById(victim.getId()).orElseThrow().getRoleId())
            .orElseThrow()
            .getCode(),
        "受害者角色不得被提升为 super");
  }

  /** super 可以发 super（正例，证明上面不是「一律拒绝」的假实现）。 */
  @Test
  void super_can_grant_super_role() throws Exception {
    String superToken = seedAdminAndLogin(uniqueName("csu"), superRoleCode());
    var victim = seedAdmin(uniqueName("csv"), "ops");
    var superRole = adminRoles.findByCode(superRoleCode()).orElseThrow();

    JsonNode r =
        patchJson(
            "/api/v1/console/admins/" + victim.getId(),
            superToken,
            objectMapper.writeValueAsString(Map.of("roleId", superRole.getId())));

    assertEquals(0, r.path("code").asInt(), "super 应能授权：" + r);
    assertEquals("super", r.path("data").path("roleCode").asText());
  }

  /** 不能停用自己（会把控制台锁死）。 */
  @Test
  void cannot_disable_self() throws Exception {
    String username = uniqueName("csu");
    AdminUserEntity me = seedAdmin(username, superRoleCode());
    String token = login(username, FIXTURE_PASSWORD);

    JsonNode r =
        patchJson("/api/v1/console/admins/" + me.getId(), token, "{\"status\":\"disabled\"}");
    assertEquals(ConsoleErrorCodes.INVALID_PARAM, r.path("code").asInt(), r.toString());
  }

  // ------------------------------------------------------------------ 角色守卫

  /** 内置角色不可删（46006）；有成员的自定义角色也不可删。 */
  @Test
  void builtin_role_cannot_be_deleted() throws Exception {
    String token = seedAdminAndLogin(uniqueName("csu"), superRoleCode());
    for (String code : List.of("super", "ops", "operator", "moderator")) {
      var role = adminRoles.findByCode(code).orElseThrow();
      JsonNode r = json(perform(delete("/api/v1/console/roles/" + role.getId()), token));
      assertEquals(ConsoleErrorCodes.ROLE_NOT_DELETABLE, r.path("code").asInt(), code + "：" + r);
    }
  }

  @Test
  void role_with_members_cannot_be_deleted() throws Exception {
    String roleCode = uniqueName("role");
    customRole(roleCode, List.of(PermissionCatalog.CONTENT_SONG_READ));
    var role = adminRoles.findByCode(roleCode).orElseThrow();
    seedAdmin(uniqueName("csv"), roleCode);
    String token = seedAdminAndLogin(uniqueName("csu"), superRoleCode());

    JsonNode r = json(perform(delete("/api/v1/console/roles/" + role.getId()), token));
    assertEquals(ConsoleErrorCodes.ROLE_NOT_DELETABLE, r.path("code").asInt(), r.toString());
  }

  /** 内置角色的 code 不可改（改掉 super 会让权限控制台自锁）。 */
  @Test
  void builtin_role_code_cannot_be_changed() throws Exception {
    String token = seedAdminAndLogin(uniqueName("csu"), superRoleCode());
    var superRole = adminRoles.findByCode(superRoleCode()).orElseThrow();

    JsonNode r =
        patchJson("/api/v1/console/roles/" + superRole.getId(), token, "{\"code\":\"super2\"}");
    assertNotEquals(0, r.path("code").asInt(), "内置角色 code 不得修改：" + r);
    assertTrue(adminRoles.findByCode(superRoleCode()).isPresent(), "super 角色必须仍然存在");
  }

  /** 权限目录端点按 module 分组返回，总条数 = 35。 */
  @Test
  void permissions_endpoint_groups_by_module() throws Exception {
    String token = seedAdminAndLogin(uniqueName("csu"), superRoleCode());
    JsonNode r = getJson("/api/v1/console/permissions", token);
    assertEquals(0, r.path("code").asInt(), r.toString());

    int total = 0;
    for (JsonNode group : r.path("data")) {
      total += group.path("permissions").size();
    }
    assertEquals(catalogSize(), total, "目录端点必须回传全部权限码：" + r.path("data"));
    assertTrue(total == 36, "目录条数（推导见 PermissionCatalog 类注释）：" + total);
  }
}
