package com.vocalverse.console.content;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.content.LrcEntity;
import com.vocalverse.content.LrcRepository;
import com.vocalverse.content.SongEntity;
import com.vocalverse.content.SongRepository;
import com.vocalverse.support.AbstractConsoleApiTest;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;

/**
 * 运营改歌**不得打回参考旋律状态**（{@code ConsoleContentWriteController.applySong} 的回归测试）。
 *
 * <h2>这一条防的是什么</h2>
 *
 * <p>{@code songs.pitch_ref_status} 不是人填的列：它由离线音高提取任务驱动，控制台四个内容弹窗里 都没有对应输入框；而它同时是**上架前置条件**（{@code
 * PublishService.validateSong} 要求 {@code ready}） 与逐句跟唱评分的参考旋律来源。
 *
 * <p>曾经的实现把它写成与相邻字段同样的「缺省 = 回落默认值」形式 （{@code b.pitchRefStatus() == null ? "missing" :
 * b.pitchRefStatus()}）。因为 {@code applySong} 同时被 create 与 update 调用，后果是：**运营只改一个歌手名，也会把已就绪的参考旋律打回
 * missing**， 于是这首歌从此上不了架，且接口返回 200、没有任何报错线索 —— 属于"静默数据损坏 + 现象远离原因"。
 *
 * <p>本测试直接在**写路径**上钉住三条语义（前两条是缺陷本体，第三条是防矫枉过正）：
 *
 * <ol>
 *   <li>更新时省略 {@code pitchRefStatus} → 保留库里的值（且上架仍然通得过）；
 *   <li>新建时省略 → 落 {@code missing}（新建语义不变：参考旋律本来就没提取）；
 *   <li>显式传值 → 以传入值为准（不能为了让"省略=保留"成立就把这个字段变成只读）。
 * </ol>
 */
class SongPitchRefPreservationTest extends AbstractConsoleApiTest {

  @Autowired private SongRepository songs;
  @Autowired private LrcRepository lrcs;

  private JsonNode send(String method, String path, String token, String body) throws Exception {
    var req =
        ("PUT".equals(method) ? put(path) : post(path))
            .header("Authorization", bearer(token))
            .contentType(MediaType.APPLICATION_JSON)
            .content(body.getBytes(StandardCharsets.UTF_8));
    return json(mockMvc.perform(req).andReturn());
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

  /** 控制台表单实际发出的完整 SongUpsert 体：**没有** pitchRefStatus 这一项。 */
  private String formBody(String title) {
    return """
        {"title":"%s","artist":"Someone","level":1,"durationS":120,"bpm":120.5,
         "musicalKey":"C","audioUrl":"/api/v1/media/song.mp3","lrcUrl":null,"coverUrl":null,
         "interestTags":"[]","source":"demo_only","status":"draft"}
        """
        .formatted(title);
  }

  @Test
  void update_without_pitch_ref_status_keeps_ready_and_stays_publishable() throws Exception {
    String token = seedAdminAndLogin(uniqueName("csop"), "operator");
    Long songId = seedSong("draft", "ready");
    seedLrc(songId);

    // 运营改歌手名 —— 表单体里没有 pitchRefStatus（它在页面上根本没有输入框）
    JsonNode updated =
        send("PUT", "/api/v1/console/content/songs/" + songId, token, formBody("Renamed Song"));
    assertEquals(0, updated.path("code").asInt(), updated.toString());

    assertEquals(
        "ready",
        songs.findById(songId).orElseThrow().getPitchRefStatus(),
        "改歌不得把已就绪的参考旋律打回 missing（否则这首歌再也上不了架）");
    assertEquals(
        "ready",
        updated.path("data").path("pitchRefStatus").asText(),
        "响应体也应如实回传保留后的状态：" + updated);

    // 端到端：编辑之后上架仍然通得过（这才是运营真正感知到的结果）
    JsonNode published =
        send(
            "POST",
            "/api/v1/console/content/songs/" + songId + "/publish",
            token,
            "{\"status\":\"published\"}");
    assertEquals(0, published.path("code").asInt(), "改歌后上架不该被 46011 拦住：" + published);
    assertEquals("published", songs.findById(songId).orElseThrow().getStatus());
  }

  @Test
  void create_without_pitch_ref_status_defaults_to_missing() throws Exception {
    String token = seedAdminAndLogin(uniqueName("csoc"), "operator");

    JsonNode created =
        send("POST", "/api/v1/console/content/songs", token, formBody("Brand New Song"));
    assertEquals(0, created.path("code").asInt(), created.toString());

    Long id = created.path("data").path("id").asLong();
    assertTrue(id > 0, "新建应回传 id：" + created);
    assertEquals(
        "missing",
        songs.findById(id).orElseThrow().getPitchRefStatus(),
        "新建歌曲尚未提取参考旋律，初始状态必须是 missing（该列 NOT NULL，不能为 null）");
  }

  @Test
  void explicit_pitch_ref_status_is_honored() throws Exception {
    String token = seedAdminAndLogin(uniqueName("csoe"), "operator");
    Long songId = seedSong("draft", "ready");
    seedLrc(songId);

    // 显式传值时必须以传入值为准：离线任务回填、以及"LRC 换了要作废旧旋律"都依赖这条
    String body =
        formBody("Explicit Status")
            .replace(
                "\"status\":\"draft\"", "\"status\":\"draft\",\"pitchRefStatus\":\"building\"");
    JsonNode r = send("PUT", "/api/v1/console/content/songs/" + songId, token, body);
    assertEquals(0, r.path("code").asInt(), r.toString());
    assertEquals(
        "building",
        songs.findById(songId).orElseThrow().getPitchRefStatus(),
        "显式传入的 pitchRefStatus 必须生效");

    // 取值域仍受 @Pattern 约束（列上也有 CHECK）：写坏值要吃 42201，而不是静默落库
    String bad =
        formBody("Bad Status")
            .replace(
                "\"status\":\"draft\"", "\"status\":\"draft\",\"pitchRefStatus\":\"nonsense\"");
    JsonNode rejected = send("PUT", "/api/v1/console/content/songs/" + songId, token, bad);
    assertEquals(42201, rejected.path("code").asInt(), "非法取值应 42201：" + rejected);
    assertEquals(
        "building", songs.findById(songId).orElseThrow().getPitchRefStatus(), "被拒绝的请求不得改动该列");
  }
}
