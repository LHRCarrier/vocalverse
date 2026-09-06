package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * /internal/checkin 契约测试（docs/21 §4 · H2）：service-token 鉴权、camelCase 键名、 幂等
 * upsert（每日一卡：practice_count 递增、overall 取最佳）。
 *
 * <p>部分唯一索引（uq_posts_checkin）为 PG 专属（H2 建不出），DB 级守护由 alembic check + service 层幂等承担（docs/40 §5 回退项，与
 * CommunityApiTest 同口径）。
 */
class InternalCheckinApiTest extends AbstractAdminApiTest {

  private static final String SERVICE_TOKEN = "change-me-internal-service-token";

  @Autowired private PostRepository posts;

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  @Test
  void checkin_upsert_idempotent_and_best_overall() throws Exception {
    registerUser("checkin_user");
    Long userId = users.findByUsernameIgnoreCase("checkin_user").orElseThrow().getId();
    String day = "2026-09-06";

    // 首卡：插入
    MvcResult r1 =
        mockMvc
            .perform(
                post("/internal/checkin")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        checkinBody(userId, day, 80.0, 82.0, 78.0, 79.0, 6, 200)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(0, json(r1).path("code").asInt(), json(r1).toString());
    long postId = json(r1).path("data").asLong();

    // 同日二次完成：同卡复用 + practice_count=2 + overall 取最佳（90 > 80）
    MvcResult r2 =
        mockMvc
            .perform(
                post("/internal/checkin")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        checkinBody(userId, day, 90.0, 84.0, 80.0, 81.0, 8, 260)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(0, json(r2).path("code").asInt(), json(r2).toString());
    assertEquals(postId, json(r2).path("data").asLong());

    PostEntity post = posts.findById(postId).orElseThrow();
    assertEquals("checkin", post.getKind());
    assertEquals(day, post.getCheckinDate().toString());
    JsonNode snap = objectMapper.readTree(post.getCheckinSnapshot());
    assertEquals(2, snap.path("practice_count").asInt());
    assertEquals(90.0, snap.path("overall").asDouble());
    assertEquals(260, snap.path("duration_s").asInt());
  }

  @Test
  void checkin_requires_service_token() throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/internal/checkin")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"userId\":1,\"practiceDate\":\"2026-09-06\",\"snapshot\":{\"overall\":80.0}}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(401, r.getResponse().getStatus());
  }

  @Test
  void checkin_rejects_snake_case_and_missing_fields() throws Exception {
    // snake_case（user_id）→ userId null → @Valid 400（P0-6 教训的契约级回归）
    MvcResult bad =
        mockMvc
            .perform(
                post("/internal/checkin")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        ("{\"user_id\":1,\"practiceDate\":\"2026-09-06\",\"snapshot\":{\"overall\":80.0}}")
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(400, bad.getResponse().getStatus());
    assertTrue(bad.getResponse().getContentAsString().contains("userId"));
  }

  private static String checkinBody(
      long userId,
      String day,
      double overall,
      double pron,
      double gram,
      double flu,
      int turns,
      int dur) {
    return String.format(
        "{\"userId\":%d,\"practiceDate\":\"%s\",\"sessionId\":100,\"snapshot\":"
            + "{\"overall\":%.1f,\"pron\":%.1f,\"gram\":%.1f,\"fluency\":%.1f,\"turns\":%d,\"durationS\":%d}}",
        userId, day, overall, pron, gram, flu, turns, dur);
  }
}
