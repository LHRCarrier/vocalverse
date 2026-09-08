package com.vocalverse.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * J-02 禁用即时生效回归：已签发未过期 token 在 users.status=disabled 后立即 401。
 *
 * <p>修复前：JwtAuthFilter 只验签不查库（application.yml access-ttl=3600），disabled 用户在
 * token 有效窗口（最长 1 小时）内仍可访问全部受保护端点——本测试改前即红（/auth/me 与
 * 社区 feed 仍 200）。本类不挂 @Transactional：禁用必须提交后由过滤器（独立事务）读到。
 */
class DisabledUserAccessTest extends AbstractAdminApiTest {

  @Autowired private com.vocalverse.user.UserRepository userRepo;

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  @Test
  void disabledUserTokenRejectedImmediately_andReenabledRestores() throws Exception {
    String token = registerUser("j02_user");
    long id = users.findByUsernameIgnoreCase("j02_user").orElseThrow().getId();

    // 禁用前：token 正常（200 + code 0）
    MvcResult before =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(token))).andReturn();
    assertEquals(0, json(before).path("code").asInt(), before.toString());

    // 管理端禁用（真实提交；过滤器下次请求在独立事务读到 committed 状态）
    String adminToken = seedAdminAndLogin();
    mockMvc
        .perform(
            patch("/api/v1/admin/users/{id}/status", id)
                .header("Authorization", bearer(adminToken))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"disabled\"}"))
        .andReturn();

    // 同一 token 立即 401（修复前：200 —— 1h 窗口内仍可用）
    MvcResult after =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(token))).andReturn();
    assertEquals(401, after.getResponse().getStatus(), after.toString());
    assertEquals(40101, json(after).path("code").asInt());

    // 社区受保护端点同样 401（而非 200/403）
    MvcResult feed =
        mockMvc
            .perform(get("/api/v1/community/posts").header("Authorization", bearer(token)))
            .andReturn();
    assertEquals(401, feed.getResponse().getStatus(), feed.toString());
    assertEquals(40101, json(feed).path("code").asInt());

    // 重新启用 → 同 token 恢复可用（非作废语义，仅状态门控）
    mockMvc
        .perform(
            patch("/api/v1/admin/users/{id}/status", id)
                .header("Authorization", bearer(adminToken))
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"active\"}"))
        .andReturn();
    MvcResult reenabled =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(token))).andReturn();
    assertEquals(200, reenabled.getResponse().getStatus(), reenabled.toString());
  }

  private String bearer(String token) {
    return "Bearer " + token;
  }
}
