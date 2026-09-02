package com.vocalverse.user.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.vocalverse.support.AbstractAdminApiTest;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

/** 用户管理（docs/06 §9.6）：列表/详情/禁用启用/档案；admin 角色守门。 */
class AdminUserApiTest extends AbstractAdminApiTest {

  @Test
  void nonAdminCannotAccessAdminApi() throws Exception {
    String userToken = registerUser("bob");
    mockMvc
        .perform(get("/api/v1/admin/users").header("Authorization", "Bearer " + userToken))
        .andExpect(status().isForbidden());
  }

  @Test
  void adminManagesUsers() throws Exception {
    String adminToken = seedAdminAndLogin();
    // 注册普通用户并取其 id（用户名唯一，防共享 H2 context 残留）
    String aliceName = "alice" + System.nanoTime() % 1000000;
    String aliceToken = registerUser(aliceName);
    String meResp =
        mockMvc
            .perform(get("/auth/me").header("Authorization", "Bearer " + aliceToken))
            .andReturn()
            .getResponse()
            .getContentAsString();
    long aliceId = objectMapper.readTree(meResp).path("data").path("userId").asLong();

    // 列表 + 搜索
    mockMvc
        .perform(
            get("/api/v1/admin/users")
                .param("search", aliceName)
                .header("Authorization", "Bearer " + adminToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items[0].username").value(aliceName))
        .andExpect(jsonPath("$.data.total").value(1));

    // 详情（含档案）
    mockMvc
        .perform(
            get("/api/v1/admin/users/{id}", aliceId)
                .header("Authorization", "Bearer " + adminToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.username").value(aliceName))
        .andExpect(jsonPath("$.data.cefrLevel").value("L1"));

    // 禁用：alice 随即无法登录
    mockMvc
        .perform(
            patch("/api/v1/admin/users/{id}/status", aliceId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"disabled\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("disabled"));
    mockMvc
        .perform(
            post("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format("{\"username\":\"%s\",\"password\":\"password123\"}", aliceName)))
        .andExpect(status().isUnauthorized());

    // 档案修改：人工改档 → source=manual + cefrLevelAt 落
    mockMvc
        .perform(
            patch("/api/v1/admin/users/{id}/profile", aliceId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"cefrLevel\":\"L3\",\"voiceRate\":\"slow\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.cefrLevel").value("L3"))
        .andExpect(jsonPath("$.data.cefrLevelSource").value("manual"))
        .andExpect(jsonPath("$.data.voiceRate").value("slow"));

    // 非法状态值 → 400
    mockMvc
        .perform(
            patch("/api/v1/admin/users/{id}/status", aliceId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"banned\"}"))
        .andExpect(status().isBadRequest());
  }
}
