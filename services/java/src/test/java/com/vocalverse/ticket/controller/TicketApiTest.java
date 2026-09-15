package com.vocalverse.ticket.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.vocalverse.support.AbstractAdminApiTest;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

/**
 * 工单**用户侧**（docs/06 §9.6）：用户提交 / 只看自己的 / 入参校验。
 *
 * <p>2026-09-10 拆分说明：本文件原含「用户提交 + 管理侧前向流转」一个大用例，其中管理侧断言打的是 {@code
 * /api/v1/admin/tickets}（旧管理端）。旧管理端已整体退役，管理侧断言**搬迁**到 {@code
 * com.vocalverse.console.content.ConsoleTicketApiTest}（打控制台 {@code PATCH
 * /api/v1/console/content/tickets/{id}}），覆盖范围不缩水： 认领 + 回复、resolved 落时间、closed 终态、非法回退 400、列表过滤都在那边。
 *
 * <p>本文件保留的用例全部只打用户侧端点（{@code /api/v1/tickets/**}），是真正的 App 契约。
 */
class TicketApiTest extends AbstractAdminApiTest {

  @Test
  void userSubmitsAndSeesOnlyOwnTickets() throws Exception {
    String userToken = registerUser("carol");

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

    mockMvc
        .perform(get("/api/v1/tickets/mine").header("Authorization", "Bearer " + userToken))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.length()").value(1))
        .andExpect(jsonPath("$.data[0].id").value(ticketId));

    // 未带令牌 → **403**（不是 401）
    //
    // 这是本服务的既有约定，不是笔误：SecurityConfig **没有配置 authenticationEntryPoint**，
    // 因此 ExceptionTranslationFilter 退回到默认的 Http403ForbiddenEntryPoint —— 匿名请求得到 403。
    // 对照：AuthFlowTest 里 401 用于「带了令牌但令牌无效/过期」（JwtAuthFilter 显式写 401 + 40101），
    // 而匿名（完全不带 Authorization 头）是 403。同类先例还有 AuthFlowTest.java:196 的匿名 logout。
    //
    // ⚠️ 本断言曾在控制台改造中被误改成 isUnauthorized()，导致该用例红（docs/51 §1.6 同类：改测试容易引入假绿/假红）。
    // 改这里的期望值前，先确认 SecurityConfig 是否补了 entry point —— 补了才应该是 401。
    mockMvc.perform(get("/api/v1/tickets/mine")).andExpect(status().isForbidden());
  }

  /** 内容纠误必须保留 targetType/targetId（运营要据此定位到具体内容）。 */
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
