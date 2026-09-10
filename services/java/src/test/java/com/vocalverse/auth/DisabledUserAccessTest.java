package com.vocalverse.auth;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * J-02 禁用即时生效回归：已签发未过期 token 在 {@code users.status=disabled} 后立即 401。
 *
 * <p>修复前：JwtAuthFilter 只验签不查库（application.yml access-ttl=3600），disabled 用户在 token 有效窗口（最长 1
 * 小时）内仍可访问全部受保护端点 —— 本测试改前即红（/auth/me 与社区 feed 仍 200）。 本类不挂
 * {@code @Transactional}：禁用必须提交后由过滤器（独立事务）读到。
 *
 * <h2>2026-09-10 适配（旧管理端退役）</h2>
 *
 * <p>本用例原来靠 {@code PATCH /api/v1/admin/users/{id}/status} 禁用 App 用户（旧管理端的 {@code
 * AdminUserController}）。该端点随旧管理端退役，但「停用 App 用户」这个**能力**并未消失 —— 它现在归控制台（{@code
 * ConsoleUserController} 的 {@code PATCH /api/v1/console/users/{id}/status}）。
 *
 * <p>所以本类改为继承 {@link AbstractConsoleApiTest}：被验证的**被测行为完全没变** （App 侧过滤器对 disabled 用户立即
 * 401），只是「谁去改状态」换成了控制台。 用控制台改状态比在测试里直接写库更强 —— 它同时证明那条控制台路径真的能改到 App 用户可见的状态（否则会以「状态没改成」的方式红）。
 */
class DisabledUserAccessTest extends AbstractConsoleApiTest {

  @Autowired private com.vocalverse.user.UserRepository userRepo;

  /** 走 /auth/register + /auth/login 拿 App token（不依赖 AbstractAdminApiTest）。 */
  private String registerAppUser(String username) throws Exception {
    String body =
        String.format(
            "{\"username\":\"%s\",\"password\":\"password123\",\"nickname\":\"%s\",\"ageGroup\":\"adult\"}",
            username, username);
    MvcResult reg =
        mockMvc
            .perform(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(
        0,
        json(reg).path("code").asInt(),
        "注册应成功：" + reg.getResponse().getContentAsString(StandardCharsets.UTF_8));
    MvcResult login =
        mockMvc
            .perform(
                org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post(
                        "/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"username\":\"%s\",\"password\":\"password123\"}", username)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    String token = json(login).path("data").path("accessToken").asText();
    assertEquals(
        false,
        token.isBlank(),
        "App 登录应成功：" + login.getResponse().getContentAsString(StandardCharsets.UTF_8));
    return token;
  }

  /** 用控制台禁用/启用 App 用户。 */
  private void setUserStatus(String consoleToken, long userId, String status) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                patch("/api/v1/console/users/{id}/status", userId)
                    .header("Authorization", bearer(consoleToken))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(String.format("{\"status\":\"%s\"}", status)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(0, root.path("code").asInt(), "控制台停用/启用 App 用户应成功（退役后这是唯一封禁路径）：" + root);
  }

  @Test
  void disabledUserTokenRejectedImmediately_andReenabledRestores() throws Exception {
    String username = uniqueName("j02u");
    String token = registerAppUser(username);
    long id = userRepo.findByUsernameIgnoreCase(username).orElseThrow().getId();

    // 禁用前：token 正常（200 + code 0）
    MvcResult before =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(token))).andReturn();
    assertEquals(0, json(before).path("code").asInt(), before.toString());

    String consoleToken = seedAdminAndLogin(uniqueName("csu"), superRoleCode());

    // 控制台禁用（真实提交；过滤器下次请求在独立事务读到 committed 状态）
    setUserStatus(consoleToken, id, "disabled");

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
    setUserStatus(consoleToken, id, "active");
    MvcResult reenabled =
        mockMvc.perform(get("/auth/me").header("Authorization", bearer(token))).andReturn();
    assertEquals(200, reenabled.getResponse().getStatus(), reenabled.toString());

    // 停用写必须留审计（旧面完全没有留痕）
    JsonNode logs =
        json(
            mockMvc
                .perform(
                    get("/api/v1/console/audit-logs?action=console.user.status")
                        .header("Authorization", bearer(consoleToken)))
                .andReturn());
    assertEquals(0, logs.path("code").asInt(), logs.toString());
    assertEquals(2, logs.path("data").path("total").asLong(), "禁用 + 启用应各留一行审计：" + logs);
  }
}
