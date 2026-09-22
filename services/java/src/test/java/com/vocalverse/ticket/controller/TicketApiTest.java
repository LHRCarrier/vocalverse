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

    // 未带令牌 → **401 + Envelope{40101}**（2026-09-22 起）
    //
    // 口径变更：SecurityConfig 此前**没有配置 authenticationEntryPoint**，ExceptionTranslationFilter
    // 退回默认 Http403ForbiddenEntryPoint → 匿名请求得到 403（且前端「401 静默续期」钩子失效，见
    // apps/web/src/api/client.ts）。2026-09-22 补上 entry point（401 + 40101）：
    //   - 匿名 / 令牌无效或过期 → 401（JwtAuthFilter 的 40101 与本 entry point 同码同形）；
    //   - 已认证但无权（角色/业务拒绝）→ 仍 403。
    // 对照：AuthFlowTest 的匿名 logout 同步改为 401。
    mockMvc.perform(get("/api/v1/tickets/mine")).andExpect(status().isUnauthorized());
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
