package com.vocalverse.content.controller;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

/** 内容库管理端（docs/06 §9.6）：场景/歌曲/LRC/听力素材 CRUD + 上下架 + 题库版本化。 */
class ContentAdminApiTest extends AbstractAdminApiTest {

  private String adminToken() throws Exception {
    return seedAdminAndLogin();
  }

  @Test
  void scenarioLifecycle() throws Exception {
    String admin = adminToken();
    // 创建
    String createBody =
        """
        {"title":"咖啡馆","sceneType":"cafe","difficulty":2,"systemPrompt":"你是咖啡店店员，温和耐心",
         "openingLine":"Welcome to our cafe!","targetCorpus":"order a coffee","interestTags":"[]",
         "estimatedTurns":6,"status":"published"}
        """;
    String created =
        mockMvc
            .perform(
                post("/api/v1/admin/scenarios")
                    .header("Authorization", "Bearer " + admin)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(createBody.getBytes(StandardCharsets.UTF_8)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.data.status").value("published"))
            .andReturn()
            .getResponse()
            .getContentAsString();
    long id = objectMapper.readTree(created).path("data").path("id").asLong();

    // 列表（含状态过滤）
    mockMvc
        .perform(
            get("/api/v1/admin/scenarios")
                .param("status", "published")
                .header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.items[0].title").value("咖啡馆"));

    // 更新 + 校验非法 scene_type → 400
    mockMvc
        .perform(
            put("/api/v1/admin/scenarios/{id}", id)
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    createBody
                        .replace("咖啡馆", "咖啡馆（改）")
                        .replace("\"published\"", "\"draft\"")
                        .getBytes(StandardCharsets.UTF_8)))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("draft"));
    mockMvc
        .perform(
            put("/api/v1/admin/scenarios/{id}", id)
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(createBody.replace("cafe", "classroom").getBytes(StandardCharsets.UTF_8)))
        .andExpect(status().isBadRequest());

    // 归档：不在 published 列表中出现
    mockMvc
        .perform(
            delete("/api/v1/admin/scenarios/{id}", id).header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("archived"));
  }

  @Test
  void songAndLrcRewriteResetsPitchRef() throws Exception {
    String admin = adminToken();
    String songBody =
        """
        {"title":"Twinkle","artist":"Public Domain","level":1,"durationS":60,"bpm":90.0,
         "audioUrl":"/data/audio/twinkle.wav","interestTags":"[]","source":"public_domain",
         "status":"published","pitchRefStatus":"ready"}
        """;
    String created =
        mockMvc
            .perform(
                post("/api/v1/admin/songs")
                    .header("Authorization", "Bearer " + admin)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(songBody))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    long songId = objectMapper.readTree(created).path("data").path("id").asLong();

    // 整首重写 LRC（seq 重排；source 继承 songs.source）
    mockMvc
        .perform(
            put("/api/v1/admin/songs/{id}/lrc", songId)
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"lines\":[{\"offsetMs\":0,\"lineText\":\"Twinkle twinkle\"},"
                        + "{\"offsetMs\":3000,\"endOffsetMs\":5000,\"lineText\":\"little star\"}]}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data[0].seq").value(1))
        .andExpect(jsonPath("$.data[1].seq").value(2))
        .andExpect(jsonPath("$.data[0].source").value("public_domain"));

    // pitch_ref_status 被重置为 missing（触发 Python 离线重提取，docs/10 §3.2-2）
    mockMvc
        .perform(get("/api/v1/admin/songs/{id}", songId).header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.pitchRefStatus").value("missing"));

    // LRC 读回
    mockMvc
        .perform(
            get("/api/v1/admin/songs/{id}/lrc", songId).header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.length()").value(2));
  }

  @Test
  void listeningMaterialAndQuestionBank() throws Exception {
    String admin = adminToken();
    // 听力素材
    mockMvc
        .perform(
            post("/api/v1/admin/listening-materials")
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"title\":\"Morning News\",\"level\":2,\"audioUrl\":\"/data/audio/news.wav\","
                        + "\"transcript\":\"Good morning\",\"status\":\"published\",\"source\":\"demo_only\"}"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("published"));

    // 题库：空表默认 revision=0 → 返回空
    mockMvc
        .perform(
            get("/api/v1/admin/placement-questions").header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.length()").value(0));

    // 建 2 题；重复 (revision, item_index) → 409
    mockMvc
        .perform(
            post("/api/v1/admin/placement-questions")
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"examRevision\":1,\"itemIndex\":1,\"kind\":\"read\",\"prompt\":\"Say it\"}"))
        .andExpect(status().isOk());
    mockMvc
        .perform(
            post("/api/v1/admin/placement-questions")
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"examRevision\":1,\"itemIndex\":2,\"kind\":\"qa\",\"prompt\":\"What is this?\",\"referenceAnswer\":\"a pen\"}"))
        .andExpect(status().isOk());
    mockMvc
        .perform(
            post("/api/v1/admin/placement-questions")
                .header("Authorization", "Bearer " + admin)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"examRevision\":1,\"itemIndex\":1,\"kind\":\"read\",\"prompt\":\"dup\"}"))
        .andExpect(status().isConflict());

    // 按版本读取
    mockMvc
        .perform(
            get("/api/v1/admin/placement-questions")
                .param("examRevision", "1")
                .header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.length()").value(2));

    // 归档（软删）
    String list =
        mockMvc
            .perform(
                get("/api/v1/admin/placement-questions")
                    .param("examRevision", "1")
                    .header("Authorization", "Bearer " + admin))
            .andReturn()
            .getResponse()
            .getContentAsString();
    long qid = objectMapper.readTree(list).path("data").get(0).path("id").asLong();
    mockMvc
        .perform(
            delete("/api/v1/admin/placement-questions/{id}", qid)
                .header("Authorization", "Bearer " + admin))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.data.status").value("archived"));
  }
}
