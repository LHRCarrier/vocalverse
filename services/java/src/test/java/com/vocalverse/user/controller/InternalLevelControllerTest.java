package com.vocalverse.user.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.vocalverse.support.AbstractAdminApiTest;
import com.vocalverse.user.UserProfileEntity;
import com.vocalverse.user.UserProfileRepository;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

/**
 * 入学测试档位回写（docs/18 §3-J1 / docs/21 §5）：POST /internal/level 幂等 PUT。
 *
 * <p>覆盖 C2/P0-6（字段名 userId + service-token 头）与 C9（幂等：旧 levelAt 不覆盖新档）。
 */
class InternalLevelControllerTest extends AbstractAdminApiTest {

  private static final String SERVICE_TOKEN = "change-me-internal-service-token";

  @Autowired private UserProfileRepository profiles;

  private long registerUserAndGetId(String name) throws Exception {
    String token = registerUser(name);
    String me =
        mockMvc
            .perform(get("/auth/me").header("Authorization", "Bearer " + token))
            .andReturn()
            .getResponse()
            .getContentAsString();
    return objectMapper.readTree(me).path("data").path("userId").asLong();
  }

  @Test
  void levelCallbackUpdatesProfile() throws Exception {
    long uid = registerUserAndGetId("lv" + System.nanoTime() % 1000000);
    Instant now = Instant.now();
    mockMvc
        .perform(
            post("/internal/level")
                .header("Authorization", "Bearer " + SERVICE_TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        "{\"userId\":%d,\"level\":\"L3\",\"source\":\"placement\",\"levelAt\":\"%s\"}",
                        uid, now)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data").value(uid));

    UserProfileEntity profile = profiles.findByUserId(uid).orElseThrow();
    org.assertj.core.api.Assertions.assertThat(profile.getCefrLevel()).isEqualTo("L3");
    org.assertj.core.api.Assertions.assertThat(profile.getCefrLevelSource()).isEqualTo("placement");
    org.assertj.core.api.Assertions.assertThat(profile.getCefrLevelAt()).isNotNull();
  }

  @Test
  void olderLevelAtIsIgnoredForIdempotency() throws Exception {
    long uid = registerUserAndGetId("lv2" + System.nanoTime() % 1000000);
    // 先落一个较新的档位 L4（levelAt = now）
    mockMvc
        .perform(
            post("/internal/level")
                .header("Authorization", "Bearer " + SERVICE_TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        "{\"userId\":%d,\"level\":\"L4\",\"source\":\"placement\",\"levelAt\":\"%s\"}",
                        uid, Instant.now())))
        .andExpect(status().isOk());
    // 再来一个 levelAt 更早（1 小时前）的 L2 —— 应被幂等忽略
    Instant earlier = Instant.now().minusSeconds(3600);
    mockMvc
        .perform(
            post("/internal/level")
                .header("Authorization", "Bearer " + SERVICE_TOKEN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    String.format(
                        "{\"userId\":%d,\"level\":\"L2\",\"source\":\"placement\",\"levelAt\":\"%s\"}",
                        uid, earlier)))
        .andExpect(status().isOk());

    UserProfileEntity profile = profiles.findByUserId(uid).orElseThrow();
    org.assertj.core.api.Assertions.assertThat(profile.getCefrLevel()).isEqualTo("L4");
  }

  @Test
  void levelCallbackWithoutTokenIsUnauthorized() throws Exception {
    long uid = registerUserAndGetId("lv3" + System.nanoTime() % 1000000);
    mockMvc
        .perform(
            post("/internal/level")
                .contentType(MediaType.APPLICATION_JSON)
                .content(String.format("{\"userId\":%d,\"level\":\"L2\"}", uid)))
        .andExpect(status().isUnauthorized());
  }
}
