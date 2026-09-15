package com.vocalverse.user.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

/**
 * 用户自助资料（社区 S3 · docs/47 §4.2）：PATCH /api/v1/users/me + GET /auth/me 回带 avatarUrl。
 *
 * <p>覆盖：改昵称/handle/tint/头像 → /auth/me 立即可见；外链头像拒绝；handle 冲突 40904； 无 token 401；空 body 幂等不改。
 */
@Transactional
class UserMeApiTest extends AbstractAdminApiTest {

  private static final int CODE_OK = 0;

  private String bearer(String token) {
    return "Bearer " + token;
  }

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private JsonNode patchMe(String token, String body) throws Exception {
    return json(
        mockMvc
            .perform(
                patch("/api/v1/users/me")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn());
  }

  private JsonNode authMe(String token) throws Exception {
    return json(
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(token))).andReturn());
  }

  @Test
  void patchMe_updatesProfileAndAuthMeReflectsIt() throws Exception {
    String token = registerUser("me_a");
    // 初始：注册用户无头像
    assertNull(authMe(token).path("data").path("avatarUrl").textValue());

    JsonNode root =
        patchMe(
            token,
            "{\"nickname\":\"新昵称\",\"handle\":\"newhandle\",\"tint\":\"#123456\","
                + "\"avatarUrl\":\"/api/v1/media/abcdef0123456789abcdef0123456789\"}");
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    assertEquals("新昵称", root.path("data").path("nickname").asText());
    assertEquals("newhandle", root.path("data").path("handle").asText());
    assertEquals(
        "/api/v1/media/abcdef0123456789abcdef0123456789",
        root.path("data").path("avatarUrl").asText());

    // /auth/me 必须同步（前端抽屉/资料页读它）
    JsonNode me = authMe(token).path("data");
    assertEquals("新昵称", me.path("nickname").asText());
    assertEquals("newhandle", me.path("handle").asText());
    assertEquals("/api/v1/media/abcdef0123456789abcdef0123456789", me.path("avatarUrl").asText());
  }

  @Test
  void patchMe_rejectsExternalAvatar() throws Exception {
    String token = registerUser("me_ext");
    MvcResult r =
        mockMvc
            .perform(
                patch("/api/v1/users/me")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"avatarUrl\":\"https://evil.example.com/a.png\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(422, r.getResponse().getStatus());
    // ResponseStatusException 422 → 42201（GlobalExceptionHandler 映射）
    assertEquals(42201, json(r).path("code").asInt());
    // 非法值不得落库
    assertNull(authMe(token).path("data").path("avatarUrl").textValue());
  }

  @Test
  void patchMe_handleConflictReturns40904() throws Exception {
    String tokenA = registerUser("me_b1");
    String tokenB = registerUser("me_b2");
    assertEquals(CODE_OK, patchMe(tokenA, "{\"handle\":\"samehandle\"}").path("code").asInt());

    MvcResult r =
        mockMvc
            .perform(
                patch("/api/v1/users/me")
                    .header("Authorization", bearer(tokenB))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"handle\":\"SameHandle\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(409, r.getResponse().getStatus());
    assertEquals(40904, json(r).path("code").asInt());
  }

  @Test
  void patchMe_requiresAuth() throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                patch("/api/v1/users/me")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"nickname\":\"x\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    // 匿名访问受保护端点：Spring Security 6 默认 AccessDenied → 403（401 仅来自 JwtAuthFilter，
    // 见 AuthFlowTest:194 既有约定）
    assertEquals(403, r.getResponse().getStatus());
  }

  @Test
  void patchMe_emptyBodyIsNoop() throws Exception {
    String token = registerUser("me_noop");
    String before = authMe(token).path("data").path("nickname").asText();
    assertEquals(CODE_OK, patchMe(token, "{}").path("code").asInt());
    assertEquals(before, authMe(token).path("data").path("nickname").asText());
  }

  @Test
  void feedAuthorCarriesAvatarUrl() throws Exception {
    // 作者头像随 AuthorView 一次带回（docs/47 §4.2：不新增请求）
    String token = registerUser("me_feed");
    patchMe(token, "{\"avatarUrl\":\"/api/v1/media/ffffffffffffffffffffffffffffffff\"}");
    assertEquals(
        CODE_OK,
        json(mockMvc
                .perform(
                    post("/api/v1/community/posts")
                        .header("Authorization", bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                            "{\"body\":\"hello\",\"kind\":\"article\",\"domain\":\"news\"}"
                                .getBytes(StandardCharsets.UTF_8)))
                .andReturn())
            .path("code")
            .asInt());

    JsonNode item =
        json(mockMvc
                .perform(get("/api/v1/community/posts").header("Authorization", bearer(token)))
                .andReturn())
            .path("data")
            .path("items")
            .get(0);
    assertEquals(
        "/api/v1/media/ffffffffffffffffffffffffffffffff",
        item.path("author").path("avatarUrl").asText());
  }
}
