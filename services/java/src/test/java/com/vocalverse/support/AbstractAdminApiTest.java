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

/** 管理端 API 测试公共设施：注册普通用户 + 播种 admin 并登录。 */
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

  /** 播种 admin（role=admin，密码固定）并登录，返回 access token。 */
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
