package com.vocalverse.common;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * J-08 错误体统一回归：所有错误响应必须为 Envelope{code, message, data}（消灭 Spring 默认错误体
 * {timestamp,status,error,path}——前端按 Envelope 统一解包）。
 *
 * <p>改前失败证据：此前仅 community 包有 @RestControllerAdvice，Auth/Admin/Ticket/Content 等域抛
 * ResponseStatusException / 校验失败 → 默认错误体缺 code/message 字段，本文件断言即红。
 */
class ErrorEnvelopeTest extends AbstractAdminApiTest {

  private JsonNode json(MvcResult r) throws Exception {
    return objectMapper.readTree(r.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  /** 断言：HTTP 状态 + 错误体三字段齐全 + 业务码。 */
  private void assertEnvelope(MvcResult r, int http, int code) throws Exception {
    assertEquals(http, r.getResponse().getStatus(), r.toString());
    JsonNode n = json(r);
    assertTrue(n.has("code") && n.has("message"), "非 Envelope 错误体：" + r.toString());
    assertEquals(code, n.path("code").asInt(), r.toString());
    assertTrue(n.get("data").isNull(), "错误响应 data 应为 null：" + r.toString());
  }

  @Test
  void authErrors_areEnvelope() throws Exception {
    // 登录密码错 401 → 40101（改前：默认错误体无 code）
    assertEnvelope(
        mockMvc
            .perform(
                post("/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":\"nobody\",\"password\":\"wrong\"}"))
            .andReturn(),
        401,
        40101);

    // 重复用户名注册 409 → 40904（「已登记未抛出」接线；改前默认错误体）
    registerUser("j08_dup");
    assertEnvelope(
        mockMvc
            .perform(
                post("/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"username\":\"j08_dup\",\"password\":\"password123\",\"nickname\":\"x\",\"ageGroup\":\"adult\"}"))
            .andReturn(),
        409,
        40904);

    // 无效 refresh 401 → 40101
    assertEnvelope(
        mockMvc
            .perform(
                post("/auth/refresh")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"refreshToken\":\"not-a-token\"}"))
            .andReturn(),
        401,
        40101);
  }

  @Test
  void adminNotFound_isEnvelope40401() throws Exception {
    String admin = seedAdminAndLogin();
    assertEnvelope(
        mockMvc
            .perform(get("/api/v1/admin/users/99999999").header("Authorization", "Bearer " + admin))
            .andReturn(),
        404,
        40401);
  }

  @Test
  void validation_42201_globally_and_42203_in_community() throws Exception {
    String token = registerUser("j08_val");
    // 非社区（工单 kind 非法）→ 400/42201（全局兜底 handler）
    assertEnvelope(
        mockMvc
            .perform(
                post("/api/v1/tickets")
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"kind\":\"spam\",\"content\":\"x\"}"))
            .andReturn(),
        400,
        42201);
    // 社区（kind=checkin 非法）→ 400/42203（community 专属 Advice 特例保持）
    MvcResult communityCreate =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"body\":\"x\",\"kind\":\"checkin\",\"domain\":\"news\"}"))
            .andReturn();
    assertEnvelope(communityCreate, 400, 42203);
  }

  @Test
  void malformedBody_isEnvelope40001() throws Exception {
    String token = registerUser("j08_body");
    assertEnvelope(
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{not-json"))
            .andReturn(),
        400,
        40001);
  }

  @Test
  void methodNotAllowed_isEnvelope40501() throws Exception {
    String token = registerUser("j08_mna");
    // 建帖（借用社区 40402 之外的成功路径）：PUT /coins 不存在 → 405
    long postId = createPost(token);
    assertEnvelope(
        mockMvc
            .perform(
                delete("/api/v1/community/posts/" + postId + "/coins")
                    .header("Authorization", "Bearer " + token))
            .andReturn(),
        405,
        40501);
  }

  @Test
  void unknownPath_isEnvelope40401() throws Exception {
    String token = registerUser("j08_path");
    assertEnvelope(
        mockMvc
            .perform(get("/api/v1/community/nowhere").header("Authorization", "Bearer " + token))
            .andReturn(),
        404,
        40401);
  }

  private long createPost(String token) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", "Bearer " + token)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"title\":\"T\",\"body\":\"Hello world practice\",\"kind\":\"article\",\"domain\":\"news\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(0, root.path("code").asInt(), root.toString());
    return root.path("data").path("id").asLong();
  }

  private String bearer(String token) {
    return "Bearer " + token;
  }
}
