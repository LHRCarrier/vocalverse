package com.vocalverse.support;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.vocalverse.user.UserEntity;
import com.vocalverse.user.UserRepository;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

/**
 * **App 侧**测试公共设施：注册普通用户（同时种子一个 App 管理员账号）。
 *
 * <h2>2026-09-10 变更说明（旧管理端退役后）</h2>
 *
 * <p>本类的名字与 {@code seedAdminAndLogin()} 来自旧管理端时代：那时「管理端」= {@code users.role='admin'} + {@code
 * /api/v1/admin/**}。旧管理端的 HTTP 面已整体退役（控制台是唯一管理面，身份是独立的 {@code admin_users}），所以：
 *
 * <ul>
 *   <li>{@link #seedAdminAndLogin()} 现在**只**用于「种一个 App 侧管理员用户并拿到 App token」， 不再有任何端点要求 {@code
 *       ROLE_ADMIN}（{@code SecurityConfig} 的 {@code hasRole("ADMIN")} 匹配已随退役删除）。保留它是因为 {@code
 *       users.role} 的语义未被改动 （属用户域迁移，不在本次范围），种子的值仍是合法数据；
 *   <li><b>控制台测试请用 {@link AbstractConsoleApiTest}</b>（独立身份 + 权限矩阵）， 不要在本类上加控制台断言 ——
 *       那是上一轮把两种身份混在一起的老问题。
 * </ul>
 *
 * <p>本类被 14 个既有测试类继承（社区/私信/用户/错误 envelope 等），其 {@link #registerUser(String)} 是那些用例的真实依赖，因此**不能删除**；
 * 删掉会让 14 个与本变更加无关的测试类一起编译失败。
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
public abstract class AbstractAdminApiTest {

  @Autowired protected MockMvc mockMvc;
  @Autowired protected ObjectMapper objectMapper;
  @Autowired protected UserRepository users;
  @Autowired protected PasswordEncoder passwordEncoder;

  private static final String ADMIN_PASSWORD = "admin12345";

  /** 走 /auth/register 注册普通用户，返回 access token。 */
  protected String registerUser(String username) throws Exception {
    String body =
        String.format(
            "{\"username\":\"%s\",\"password\":\"password123\",\"nickname\":\"%s\",\"ageGroup\":\"adult\"}",
            username, username);
    String resp =
        mockMvc
            .perform(
                post("/auth/register")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn()
            .getResponse()
            .getContentAsString();
    return objectMapper.readTree(resp).path("data").path("accessToken").asText();
  }

  /**
   * 播种一个 **App 侧**管理员用户（{@code users.role='admin'}）并走 App 登录，返回 App access token。
   *
   * <p>注意：自 2026-09-10 旧管理端退役后，**没有任何端点再要求 {@code ROLE_ADMIN}**。 需要控制台身份请用 {@link
   * AbstractConsoleApiTest#seedAdminAndLogin(String, String)}。
   */
  protected String seedAdminAndLogin() throws Exception {
    String adminName = "admin" + System.nanoTime() % 1000000;
    Instant now = Instant.now();
    UserEntity admin = new UserEntity();
    admin.setUsername(adminName);
    admin.setPasswordHash(passwordEncoder.encode(ADMIN_PASSWORD));
    admin.setNickname("Admin");
    admin.setRole("admin");
    admin.setStatus("active");
    admin.setCreatedAt(now);
    admin.setUpdatedAt(now);
    users.save(admin);

    String resp =
        mockMvc
            .perform(
                post("/auth/login")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                            "{\"username\":\"%s\",\"password\":\"%s\"}",
                            adminName, ADMIN_PASSWORD)))
            .andReturn()
            .getResponse()
            .getContentAsString();
    JsonNode data = objectMapper.readTree(resp).path("data");
    return data.path("accessToken").asText();
  }
}
