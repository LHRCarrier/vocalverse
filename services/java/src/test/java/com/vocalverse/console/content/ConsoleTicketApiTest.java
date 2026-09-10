package com.vocalverse.console.content;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

/**
 * 控制台工单面（退役旧管理端后，这是**唯一**的工单处理路径）。
 *
 * <p>本类承接原 {@code TicketApiTest} 里管理侧的断言（认领+回复 / resolved 落时间 / closed 终态 / 非法回退 400 /
 * 列表过滤），只是把目标端点从 {@code /api/v1/admin/tickets} 换成 {@code
 * /api/v1/console/content/tickets}，并补上旧面没有的审计断言。
 */
class ConsoleTicketApiTest extends AbstractConsoleApiTest {

  private JsonNode postJson(String path, String token, String body) throws Exception {
    return json(
        mockMvc
            .perform(
                post(path)
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn());
  }

  private JsonNode patchJson(String path, String token, String body) throws Exception {
    return json(
        mockMvc
            .perform(
                patch(path)
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn());
  }

  private JsonNode getJson(String path, String token) throws Exception {
    return json(mockMvc.perform(get(path).header("Authorization", bearer(token))).andReturn());
  }

  /** 造一个工单（走 App 侧 forgot 流程，最省事且不新增测试专用端点）。 */
  private long seedTicket(String username, String kind) throws Exception {
    String body =
        String.format(
            "{\"username\":\"%s\",\"password\":\"password123\",\"nickname\":\"%s\",\"ageGroup\":\"adult\"}",
            username, username);
    mockMvc.perform(
        post("/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .content(body.getBytes(StandardCharsets.UTF_8)));
    if ("feedback".equals(kind)) {
      mockMvc.perform(
          post("/auth/forgot")
              .contentType(MediaType.APPLICATION_JSON)
              .content(
                  String.format("{\"username\":\"%s\"}", username)
                      .getBytes(StandardCharsets.UTF_8)));
    }
    return -1;
  }

  @Test
  void fullForwardFlow_claim_reply_resolve_close() throws Exception {
    String appUser = uniqueName("tku");
    seedTicket(appUser, "feedback");
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");

    // 列表（运营有 content:ticket:read）
    JsonNode list = getJson("/api/v1/console/content/tickets", token);
    assertEquals(0, list.path("code").asInt(), list.toString());
    long ticketId = list.path("data").path("items").get(0).path("id").asLong();
    assertEquals("open", list.path("data").path("items").get(0).path("status").asText());

    // 详情（旧面没有对应端点，控制台补齐）
    JsonNode detail = getJson("/api/v1/console/content/tickets/" + ticketId, token);
    assertEquals(0, detail.path("code").asInt(), detail.toString());
    assertEquals(ticketId, detail.path("data").path("id").asLong());

    // open → processing（认领 + 回复）
    JsonNode processing =
        patchJson(
            "/api/v1/console/content/tickets/" + ticketId,
            token,
            "{\"status\":\"processing\",\"adminReply\":\"已定位到问题\"}");
    assertEquals(0, processing.path("code").asInt(), processing.toString());
    assertEquals("processing", processing.path("data").path("status").asText());
    assertEquals(
        "已定位到问题",
        processing.path("data").path("adminReply").asText(),
        "adminReply 必须被保存（回复用户是工单的全部意义）");
    assertTrue(
        processing.path("data").path("adminId").asLong() > 0, "首次回复应认领 admin_id：" + processing);

    // processing → resolved（落 resolvedAt）
    JsonNode resolved =
        patchJson(
            "/api/v1/console/content/tickets/" + ticketId, token, "{\"status\":\"resolved\"}");
    assertEquals(0, resolved.path("code").asInt(), resolved.toString());
    assertTrue(
        !resolved.path("data").path("resolvedAt").isMissingNode()
            && !resolved.path("data").path("resolvedAt").isNull(),
        "resolved 必须落 resolvedAt：" + resolved);

    // resolved → closed
    JsonNode closed =
        patchJson("/api/v1/console/content/tickets/" + ticketId, token, "{\"status\":\"closed\"}");
    assertEquals(0, closed.path("code").asInt(), closed.toString());
    assertEquals("closed", closed.path("data").path("status").asText());

    // 回退 → 400（沿用既有 40001 路径，不新增错误码）
    JsonNode backward =
        patchJson("/api/v1/console/content/tickets/" + ticketId, token, "{\"status\":\"open\"}");
    assertNotEquals(0, backward.path("code").asInt(), "状态机禁回退：" + backward);
    assertEquals(
        "closed",
        getJson("/api/v1/console/content/tickets/" + ticketId, token)
            .path("data")
            .path("status")
            .asText(),
        "被拒后状态不得改动");

    // 状态过滤（旧面能力，保留）
    JsonNode closedList = getJson("/api/v1/console/content/tickets?status=closed", token);
    assertEquals(0, closedList.path("code").asInt());
    assertTrue(closedList.path("data").path("total").asLong() >= 1);
  }

  /** kind 过滤（控制台新增能力，运营处理「内容纠误」的主要用法）。 */
  @Test
  void list_filter_by_kind() throws Exception {
    seedTicket(uniqueName("tkf"), "feedback");
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");

    JsonNode feedback = getJson("/api/v1/console/content/tickets?kind=feedback", token);
    assertEquals(0, feedback.path("code").asInt(), feedback.toString());
    assertTrue(feedback.path("data").path("total").asLong() >= 1);

    JsonNode bug = getJson("/api/v1/console/content/tickets?kind=bug", token);
    assertEquals(0, bug.path("code").asInt());
    assertEquals(0, bug.path("data").path("total").asLong(), "没有 bug 工单时应为 0：" + bug);
  }

  /** 工单写必须落审计（旧面完全没有留痕）。 */
  @Test
  void ticket_update_writes_audit_row() throws Exception {
    seedTicket(uniqueName("tka"), "feedback");
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");

    long id =
        getJson("/api/v1/console/content/tickets", token)
            .path("data")
            .path("items")
            .get(0)
            .path("id")
            .asLong();
    assertEquals(
        0,
        patchJson("/api/v1/console/content/tickets/" + id, token, "{\"status\":\"processing\"}")
            .path("code")
            .asInt());

    JsonNode logs = getJson("/api/v1/console/audit-logs?action=content.ticket.update", token);
    assertEquals(0, logs.path("code").asInt(), logs.toString());
    assertTrue(logs.path("data").path("total").asLong() >= 1, "工单写必须留审计（docs/50 §9.3）：" + logs);
    assertEquals("ticket", logs.path("data").path("items").get(0).path("targetType").asText());
  }

  /** 只读角色不能改工单（46002 + required）。 */
  @Test
  void ticket_write_requires_write_permission() throws Exception {
    seedTicket(uniqueName("tkr"), "feedback");
    String roleCode = uniqueName("role");
    customRole(
        roleCode,
        java.util.List.of(com.vocalverse.console.rbac.PermissionCatalog.CONTENT_TICKET_READ));
    String token = seedAdminAndLogin(uniqueName("csu"), roleCode);

    long id =
        getJson("/api/v1/console/content/tickets", token)
            .path("data")
            .path("items")
            .get(0)
            .path("id")
            .asLong();
    JsonNode denied =
        patchJson("/api/v1/console/content/tickets/" + id, token, "{\"status\":\"processing\"}");
    assertEquals(
        ConsoleErrorCodes.PERMISSION_DENIED, denied.path("code").asInt(), denied.toString());
    assertEquals(
        com.vocalverse.console.rbac.PermissionCatalog.CONTENT_TICKET_WRITE,
        denied.path("data").path("required").asText());
  }
}
