package com.vocalverse.content.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;

/**
 * /internal/song/{id}/pitch-status 契约测试（docs/21 §4 第三条 · 2026-09-09 唱歌 P0 D2）。
 *
 * <p>覆盖 service-token 鉴权、camelCase 键名（P0-6 教训的契约级回归）、状态枚举校验、 幂等语义（同值重复无害——Python 扫描补偿可放心重发）、404 分支。
 */
class InternalSongStatusApiTest extends AbstractAdminApiTest {

  private static final String SERVICE_TOKEN = "change-me-internal-service-token";

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private long createSongToken(String admin) throws Exception {
    String created =
        mockMvc
            .perform(
                post("/api/v1/admin/songs")
                    .header("Authorization", "Bearer " + admin)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        ("{\"title\":\"Old Mac\",\"level\":1,\"audioUrl\":\"/data/audio/oldmac.wav\","
                                + "\"source\":\"public_domain\",\"status\":\"published\"}")
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn()
            .getResponse()
            .getContentAsString();
    return objectMapper.readTree(created).path("data").path("id").asLong();
  }

  @Test
  void pitchStatus_flips_gate_and_is_idempotent() throws Exception {
    String admin = seedAdminAndLogin();
    long songId = createSongToken(admin);
    // 新歌恒 missing（SongUpsert 已移除客户端直写，D-G4）
    mockMvc
        .perform(get("/api/v1/admin/songs/{id}", songId).header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.pitchRefStatus").value("missing"));

    // Python 委托翻转 ready（camelCase；重复投递无恙——幂等）
    for (int i = 0; i < 2; i++) {
      MvcResult r =
          mockMvc
              .perform(
                  post("/internal/song/{id}/pitch-status", songId)
                      .header("Authorization", "Bearer " + SERVICE_TOKEN)
                      .contentType(MediaType.APPLICATION_JSON)
                      .content(
                          ("{\"songId\":"
                                  + songId
                                  + ",\"status\":\"ready\",\"version\":\"pyin-v1\"}")
                              .getBytes(StandardCharsets.UTF_8)))
              .andReturn();
      assertEquals(0, json(r).path("code").asInt(), json(r).toString());
      assertEquals(songId, json(r).path("data").asLong());
    }
    mockMvc
        .perform(get("/api/v1/admin/songs/{id}", songId).header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.pitchRefStatus").value("ready"));
  }

  @Test
  void pitchStatus_requires_service_token() throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/internal/song/1/pitch-status")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"songId\":1,\"status\":\"ready\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(401, r.getResponse().getStatus());
  }

  @Test
  void pitchStatus_rejects_snake_case_and_bad_status() throws Exception {
    // snake_case（song_id）→ songId null → @Valid 400（P0-6 教训的契约级回归）
    MvcResult snake =
        mockMvc
            .perform(
                post("/internal/song/1/pitch-status")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"song_id\":1,\"status\":\"ready\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(400, snake.getResponse().getStatus());
    assertTrue(snake.getResponse().getContentAsString().contains("songId"));

    // 非法状态枚举 → @Pattern 400
    MvcResult bad =
        mockMvc
            .perform(
                post("/internal/song/1/pitch-status")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"songId\":1,\"status\":\"paused\"}".getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(400, bad.getResponse().getStatus());
  }

  @Test
  void pitchStatus_song_not_found_is_404() throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/internal/song/99999999/pitch-status")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        "{\"songId\":99999999,\"status\":\"ready\"}"
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    assertEquals(404, r.getResponse().getStatus());
  }
}
