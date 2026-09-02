package com.vocalverse.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

/** 工单（docs/06 §9.6）：用户提交/查看 + 管理侧列表/前向流转。 */
class TicketApiTest extends AbstractAdminApiTest {

  @Test
  void userSubmitsAndAdminAdvances() throws Exception {
    String userToken = registerUser("carol");
    String adminToken = seedAdminAndLogin();

    // 用户提交（kind=bug）
    String created =
        mockMvc
            .perform(
                post("/api/v1/tickets")
                    .header("Authorization", "Bearer " + userToken)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"kind\":\"bug\",\"title\":\"录音按钮失灵\",\"content\":\"点开始没反应\"}"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.status").value("open"))
            .andReturn()
            .getResponse()
            .getContentAsString();
    long ticketId = objectMapper.readTree(created).path("data").path("id").asLong();

    // 用户只能看到自己的工单
    mockMvc
        .perform(get("/api/v1/tickets/mine").header("Authorization", "Bearer " + userToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.length()").value(1));

    // 用户无权访问管理侧
    mockMvc
        .perform(get("/api/v1/admin/tickets").header("Authorization", "Bearer " + userToken))
        .andExpect(status().isForbidden());

    // 管理侧：open → processing（认领 + 回复）→ resolved（落时间）→ closed
    mockMvc
        .perform(
            patch("/api/v1/admin/tickets/{id}", ticketId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"processing\",\"adminReply\":\"已定位到问题\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("processing"))
        .andExpect(jsonPath("$.data.adminId").exists());
    mockMvc
        .perform(
            patch("/api/v1/admin/tickets/{id}", ticketId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"resolved\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.resolvedAt").exists());
    mockMvc
        .perform(
            patch("/api/v1/admin/tickets/{id}", ticketId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"closed\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("closed"));

    // 回退流转 → 400
    mockMvc
        .perform(
            patch("/api/v1/admin/tickets/{id}", ticketId)
                .header("Authorization", "Bearer " + adminToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"status\":\"open\"}"))
        .andExpect(status().isBadRequest());

    // 管理侧列表过滤
    mockMvc
        .perform(
            get("/api/v1/admin/tickets")
                .param("status", "closed")
                .header("Authorization", "Bearer " + adminToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items[0].kind").value("bug"));
  }

  @Test
  void contentCorrectionKeepsTarget() throws Exception {
    String userToken = registerUser("dave");
    mockMvc
        .perform(
            post("/api/v1/tickets")
                .header("Authorization", "Bearer " + userToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"kind\":\"content_correction\",\"targetType\":\"song\",\"targetId\":12,"
                        + "\"content\":\"翻译不准\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.targetType").value("song"))
        .andExpect(jsonPath("$.data.targetId").value(12));

    // 非法 kind → 400
    mockMvc
        .perform(
            post("/api/v1/tickets")
                .header("Authorization", "Bearer " + userToken)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"kind\":\"spam\",\"content\":\"x\"}"))
        .andExpect(status().isBadRequest());
  }
}
