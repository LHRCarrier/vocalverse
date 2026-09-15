package com.vocalverse.auth;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.ticket.TicketRepository;
import com.vocalverse.user.UserRepository;
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
  @Autowired private TicketRepository ticketRepository;
  @Autowired private UserRepository users;

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
                post("/auth/register")
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
        .perform(get("/auth/me").header("Authorization", "Bearer " + access))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.username").value("alice"));

    // refresh（rotation：旧 refresh 失效）
    String refreshToken = token.path("refreshToken").asText();
    String refreshResp =
        mockMvc
            .perform(
                post("/auth/refresh")
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
            post("/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refreshToken + "\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void loginRejectsBadPassword() throws Exception {
    mockMvc
        .perform(
            post("/auth/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"username\":\"alice\",\"password\":\"wrong-password\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void internalLevelRequiresServiceToken() throws Exception {
    mockMvc
        .perform(
            post("/internal/level")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"userId\":1,\"level\":\"L2\"}"))
        .andExpect(status().isUnauthorized());
  }

  @Test
  void forgotPasswordCreatesTicketAndHidesExistence() throws Exception {
    String username = "forgot_" + System.nanoTime() % 1000000;
    mockMvc
        .perform(
            post("/auth/register")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    ("{\"username\":\""
                            + username
                            + "\",\"password\":\"password123\","
                            + "\"nickname\":\"Forgot\",\"ageGroup\":\"adult\"}")
                        .getBytes(java.nio.charset.StandardCharsets.UTF_8)))
        .andExpect(status().isOk());

    // 存在用户：落工单 + 统一「已收到申请」文案（中文按非空/相等性断言，规避源码编码差）
    String resp1 =
        mockMvc
            .perform(
                post("/auth/forgot")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":\"" + username + "\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assert objectMapper.readTree(resp1).path("data").asText().length() > 10 : resp1;

    // 不存在用户：同响应（防枚举——message 一致）
    String resp2 =
        mockMvc
            .perform(
                post("/auth/forgot")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":\"nobody_xyz\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assert objectMapper
        .readTree(resp2)
        .path("data")
        .asText()
        .equals(objectMapper.readTree(resp1).path("data").asText());

    // 工单已落库（feedback / open）
    var tickets =
        ticketRepository.findByUserIdOrderByIdDesc(
            users.findByUsernameIgnoreCase(username).orElseThrow().getId());
    assert !tickets.isEmpty();
    assert tickets.get(0).getKind().equals("feedback");
    assert tickets.get(0).getTitle().equals("密码重置申请");
    assert tickets.get(0).getStatus().equals("open");
  }

  @Test
  void logoutRevokesAllRefreshTokens() throws Exception {
    // 注册 + 再登录一次 → 该用户持两份 refresh token（验证「全部吊销」而非仅吊销当次）
    String username = "logout_" + System.nanoTime() % 1000000;
    String registerResp =
        mockMvc
            .perform(
                post("/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        ("{\"username\":\""
                                + username
                                + "\",\"password\":\"password123\","
                                + "\"nickname\":\"Logout\",\"ageGroup\":\"adult\"}")
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8)))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    String refresh1 =
        objectMapper.readTree(registerResp).path("data").path("refreshToken").asText();
    String loginResp =
        mockMvc
            .perform(
                post("/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"username\":\"" + username + "\",\"password\":\"password123\"}"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    JsonNode loginData = objectMapper.readTree(loginResp).path("data");
    String access2 = loginData.path("accessToken").asText();
    String refresh2 = loginData.path("refreshToken").asText();

    // 无令牌调用 logout → 403（匿名访问受保护端点：Spring Security 6 默认 AccessDenied → 403；
    // 401 仅来自 ServiceTokenFilter 显式 sendError 与 ResponseStatusException，见既有用例）
    mockMvc.perform(post("/auth/logout")).andExpect(status().isForbidden());

    // 带 access token 登出 → 吊销全部
    mockMvc
        .perform(post("/auth/logout").header("Authorization", "Bearer " + access2))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.code").value(0));

    // 两份 refresh 均已失效（含注册期签发的 refresh1 —— 即「退出登录后 30 天窗口内不得续命」）
    mockMvc
        .perform(
            post("/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh1 + "\"}"))
        .andExpect(status().isUnauthorized());
    mockMvc
        .perform(
            post("/auth/refresh")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"refreshToken\":\"" + refresh2 + "\"}"))
        .andExpect(status().isUnauthorized());
  }
}
