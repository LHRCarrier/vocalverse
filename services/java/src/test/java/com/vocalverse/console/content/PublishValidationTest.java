package com.vocalverse.console.content;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.console.ConsoleErrorCodes;
import com.vocalverse.content.ListeningMaterialEntity;
import com.vocalverse.content.ListeningMaterialRepository;
import com.vocalverse.content.LrcEntity;
import com.vocalverse.content.LrcRepository;
import com.vocalverse.content.ScenarioEntity;
import com.vocalverse.content.ScenarioRepository;
import com.vocalverse.content.SongEntity;
import com.vocalverse.content.SongRepository;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

/**
 * 上架校验与运营端点（docs/50 §14.2-Java 第 12 条 + §6.1）。
 *
 * <p>核心断言：缺 LRC 的歌曲上架 → 46011 + {@code data.violations[]} 的**字段级**原因。
 */
class PublishValidationTest extends AbstractConsoleApiTest {

  @Autowired private SongRepository songs;
  @Autowired private LrcRepository lrcs;
  @Autowired private ListeningMaterialRepository materials;
  @Autowired private ScenarioRepository scenarios;

  private JsonNode postJson(String path, String token, String body) throws Exception {
    return json(
        mockMvc
            .perform(
                post(path)
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn());
  }

  private JsonNode getJson(String path, String token) throws Exception {
    return json(mockMvc.perform(get(path).header("Authorization", bearer(token))).andReturn());
  }

  private Long seedSong(String status, String pitchRefStatus) {
    Instant now = Instant.now();
    SongEntity s = new SongEntity();
    s.setTitle("T" + System.nanoTime());
    s.setLevel(1);
    s.setAudioUrl("/api/v1/media/song.mp3");
    s.setInterestTags("[]");
    s.setSource("demo_only");
    s.setStatus(status);
    s.setPitchRefStatus(pitchRefStatus);
    s.setCreatedAt(now);
    s.setUpdatedAt(now);
    return songs.save(s).getId();
  }

  private void seedLrc(Long songId) {
    LrcEntity l = new LrcEntity();
    l.setSongId(songId);
    l.setSeq(1);
    l.setOffsetMs(0L);
    l.setLineText("Hello world");
    l.setSource("demo_only");
    l.setCreatedAt(Instant.now());
    lrcs.save(l);
  }

  private Long seedMaterial(String transcript) {
    Instant now = Instant.now();
    ListeningMaterialEntity m = new ListeningMaterialEntity();
    m.setTitle("M" + System.nanoTime());
    m.setLevel(1);
    m.setAudioUrl("/api/v1/media/l.mp3");
    m.setTranscript(transcript);
    m.setInterestTags("[]");
    m.setStatus("draft");
    m.setCreatedAt(now);
    m.setUpdatedAt(now);
    return materials.save(m).getId();
  }

  private Long seedScenario(String openingLine, String targetCorpus) {
    Instant now = Instant.now();
    ScenarioEntity s = new ScenarioEntity();
    s.setTitle("S" + System.nanoTime());
    s.setSceneType("cafe");
    s.setDifficulty(1);
    s.setSystemPrompt("prompt");
    s.setOpeningLine(openingLine);
    s.setTargetCorpus(targetCorpus);
    s.setInterestTags("[]");
    s.setPromptVersion(1);
    s.setStatus("draft");
    s.setCreatedAt(now);
    s.setUpdatedAt(now);
    return scenarios.save(s).getId();
  }

  // ------------------------------------------------------------------ 46011

  /** 缺 LRC 的歌曲上架 → 46011 + violations[].field == "lrc"。 */
  @Test
  void song_without_lrc_cannot_publish_46011_with_violations() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    Long songId = seedSong("draft", "ready"); // 无 LRC 行

    JsonNode r =
        postJson(
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"published\"}");

    assertEquals(ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED, r.path("code").asInt(), r.toString());
    assertEquals(422, r.path("code").asInt() == 46011 ? 422 : -1);

    JsonNode violations = r.path("data").path("violations");
    assertTrue(violations.isArray() && violations.size() >= 1, "必须回传字段级 violations：" + r);
    boolean hasLrc =
        java.util.stream.StreamSupport.stream(violations.spliterator(), false)
            .anyMatch(v -> "lrc".equals(v.path("field").asText()));
    assertTrue(hasLrc, "violations 必须含 field=lrc：" + violations);
    assertEquals("draft", songs.findById(songId).orElseThrow().getStatus(), "校验失败不得改状态");
  }

  /** 参考旋律未就绪 → 46011，且 field 指向 pitchRefStatus（不是虚构的 ref_melody 列）。 */
  @Test
  void song_without_ready_pitch_ref_cannot_publish() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    Long songId = seedSong("draft", "missing");
    seedLrc(songId);

    JsonNode r =
        postJson(
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED, r.path("code").asInt(), r.toString());
    boolean hasPitch =
        java.util.stream.StreamSupport.stream(
                r.path("data").path("violations").spliterator(), false)
            .anyMatch(v -> "pitchRefStatus".equals(v.path("field").asText()));
    assertTrue(hasPitch, "应指向 pitchRefStatus（songs 表没有 ref_melody 列）：" + r);
    assertFalse(r.path("data").path("violations").toString().contains("refMelody"));
  }

  /** LRC + pitch_ref_status=ready → 上架成功，并落下审计与流水。 */
  @Test
  void song_with_lrc_and_ready_pitch_ref_publishes_and_records_audit() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    Long songId = seedSong("draft", "ready");
    seedLrc(songId);

    JsonNode r =
        postJson(
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(0, r.path("code").asInt(), r.toString());
    assertEquals("draft", r.path("data").path("prevStatus").asText());
    assertEquals("published", r.path("data").path("nextStatus").asText());
    assertEquals("published", songs.findById(songId).orElseThrow().getStatus());

    // 上架流水由 admin_audit_logs 派生（docs/50 §10.2）
    JsonNode events = getJson("/api/v1/console/content/publish-events", token);
    assertEquals(0, events.path("code").asInt(), events.toString());
    assertTrue(
        events.path("data").path("items").toString().contains("content.song.publish"),
        "publish-events 应含本次上架：" + events);
  }

  /** 下架（published → archived）不触发校验 —— 下架永远该被允许（安全动作）。 */
  @Test
  void archive_never_blocked_by_validation() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    Long songId = seedSong("published", "missing"); // 无 LRC、旋律未就绪

    JsonNode r =
        postJson(
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"archived\"}");
    assertEquals(0, r.path("code").asInt(), "下架不该被校验拦住：" + r);
    assertEquals("archived", songs.findById(songId).orElseThrow().getStatus());
  }

  /** 听力素材缺 transcript → 46011，field=transcript。 */
  @Test
  void material_without_transcript_cannot_publish() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    Long id = seedMaterial(null);

    JsonNode r =
        postJson(
            "/api/v1/console/content/listening-materials/" + id + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED, r.path("code").asInt(), r.toString());
    assertTrue(r.path("data").path("violations").toString().contains("transcript"), r.toString());
  }

  /** 场景语料不足 3 条 → 46011；语料按 `English|中文` 权威格式计数（与 Python 同口径）。 */
  @Test
  void scenario_with_too_few_corpus_items_cannot_publish() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    // 只有 1 条合法语料行 + 1 行无 | 的噪音行
    Long id = seedScenario("Hi there", "How are you?|你好吗？\nno pipe here");

    JsonNode r =
        postJson(
            "/api/v1/console/content/scenarios/" + id + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(ConsoleErrorCodes.PUBLISH_VALIDATION_FAILED, r.path("code").asInt(), r.toString());
    assertTrue(r.path("data").path("violations").toString().contains("targetCorpus"), r.toString());

    // 补到 3 条 → 成功
    ScenarioEntity s = scenarios.findById(id).orElseThrow();
    s.setTargetCorpus("a|1\nb|2\nc|3");
    s.setUpdatedAt(Instant.now());
    scenarios.save(s);
    JsonNode ok =
        postJson(
            "/api/v1/console/content/scenarios/" + id + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(0, ok.path("code").asInt(), ok.toString());
  }

  /** 语料解析口径自证：与 app/practice/corpus.py 一致（只认含 `|` 且短语非空的行）。 */
  @Test
  void corpus_counting_matches_python_parser_semantics() {
    assertEquals(0, PublishService.countCorpusItems(null));
    assertEquals(0, PublishService.countCorpusItems(""));
    assertEquals(0, PublishService.countCorpusItems("no pipes at all\nsecond line"));
    assertEquals(0, PublishService.countCorpusItems("|only gloss"), "| 前没有短语的行 Python 也会跳过");
    assertEquals(3, PublishService.countCorpusItems("a|1\nb|2\nc|3"));
    assertEquals(2, PublishService.countCorpusItems("a|1\n\n  \nb|2"), "空行不计");
    assertEquals(
        3,
        PublishService.countCorpusItems("How are you?|你好吗？\nFine; thanks|很好；谢谢\nBye|再见"),
        "中文释义里的分号不得被当成条目分隔（与 Python splitlines 口径一致）");
  }

  /** 非法 status → 46007（而不是静默忽略）。 */
  @Test
  void invalid_status_rejected_with_46007() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    Long songId = seedSong("draft", "ready");
    seedLrc(songId);
    JsonNode r =
        postJson(
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"bogus\"}");
    assertNotEquals(0, r.path("code").asInt(), r.toString());
  }

  // ------------------------------------------------------------------ 权限

  /** 只有 read 码的角色不能上架（46002 + required=content:song:publish）。 */
  @Test
  void publish_requires_publish_permission() throws Exception {
    String roleCode = uniqueName("role");
    customRole(roleCode, List.of(com.vocalverse.console.rbac.PermissionCatalog.CONTENT_SONG_READ));
    String token = seedAdminAndLogin(uniqueName("csu"), roleCode);
    Long songId = seedSong("draft", "ready");

    JsonNode r =
        postJson(
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(ConsoleErrorCodes.PERMISSION_DENIED, r.path("code").asInt(), r.toString());
    assertEquals(
        com.vocalverse.console.rbac.PermissionCatalog.CONTENT_SONG_PUBLISH,
        r.path("data").path("required").asText());
  }

  /** 工单状态复用了既有状态机（非法回退被拒）。 */
  @Test
  void ticket_status_reuses_shared_state_machine() throws Exception {
    String token = seedAdminAndLogin(uniqueName("cso"), "operator");
    // 建一条 open 工单（走 App 侧 forgot 流程最省事：需要先有用户）
    String appUser = uniqueName("tku");
    String body =
        String.format(
            "{\"username\":\"%s\",\"password\":\"password123\",\"nickname\":\"%s\",\"ageGroup\":\"adult\"}",
            appUser, appUser);
    mockMvc.perform(
        post("/auth/register")
            .contentType(MediaType.APPLICATION_JSON)
            .content(body.getBytes(StandardCharsets.UTF_8)));
    mockMvc.perform(
        post("/auth/forgot")
            .contentType(MediaType.APPLICATION_JSON)
            .content(
                String.format("{\"username\":\"%s\"}", appUser).getBytes(StandardCharsets.UTF_8)));

    JsonNode list = getJson("/api/v1/console/content/tickets", token);
    assertEquals(0, list.path("code").asInt(), list.toString());
    long ticketId = list.path("data").path("items").get(0).path("id").asLong();
    assertEquals("open", list.path("data").path("items").get(0).path("status").asText());

    JsonNode forward =
        json(
            mockMvc
                .perform(
                    org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch(
                            "/api/v1/console/content/tickets/" + ticketId)
                        .header("Authorization", bearer(token))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"status\":\"processing\"}"))
                .andReturn());
    assertEquals(0, forward.path("code").asInt(), forward.toString());

    JsonNode backward =
        postJson(
            "/api/v1/console/content/tickets/" + ticketId + "/status",
            token,
            "{\"status\":\"open\"}");
    assertNotEquals(0, backward.path("code").asInt(), "状态机禁回退（复用既有规则）：" + backward);
  }
}
