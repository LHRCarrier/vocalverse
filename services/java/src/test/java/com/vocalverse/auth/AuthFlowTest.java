package com.vocalverse.auth;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/** 认证最小集流程测试（docs/18 §3-J1）：注册 → 登录 → me → 刷新 rotation。 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthFlowTest {

  @Autowired private MockMvc mockMvc;
  @Autowired private ObjectMapper objectMapper;

  @Test
  void fullAuthFlow() throws Exception {
    // 注册
    String registerBody =
        """
        {"username":"alice","email":"a@test.com","password":"password123","nickname":"Alice","ageGroup":"adult"}
        """;
    String registerResp =
        mockMvc
            .perform(
                post("/manage/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(registerBody))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value(0))
            .andReturn()
            .getResponse()
            .getContentAsString();
    JsonNode token = objectMapper.readTree(registerResp).path("data");
    String access = token.path("accessToken").asText();
    assert !access.isEmpty();

    // me（JWT）
    mockMvc
        .perform(get("/manage/auth/me").header("Authorization", "Bearer " + access))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.username").value("alice"));

    // refresh（rotation：旧 refresh 失效）
    String refreshToken = token.path("refreshToken").asText();
    String refreshResp =
        mockMvc
            .perform(
                post("/manage/auth/refresh")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"refreshToken\":\"" + refreshToken + "\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    JsonNode refreshed = objectMapper.readTree(refreshResp).path("data");
    assert !refreshed.path("accessToken").asText().isEmpty();
    assert !refreshed.path("refreshToken").asText().equals(refreshToken);

    // 旧 refresh 已吊销
    mockMvc
        .perform(
            post("/manage/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refreshToken + "\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void loginRejectsBadPassword() throws Exception {
    mockMvc
        .perform(
            post("/manage/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"wrong-password\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void internalLevelRequiresServiceToken() throws Exception {
    mockMvc
        .perform(
            post("/manage/internal/level")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"userId\":1,\"level\":\"L2\"}"))
        .andExpect(status().isUnauthorized());
  }
}
