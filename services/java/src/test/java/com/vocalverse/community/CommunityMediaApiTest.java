package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;

import com.fasterxml.jackson.databind.JsonNode;
import com.vocalverse.support.AbstractAdminApiTest;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

/**
 * 发帖 media 契约校验（社区 S3 · docs/47 §4.3 · docs/48 B11/B18）。
 *
 * <p>覆盖：合法多图/单视频落库 → 详情回带；外链拒绝；条数越界；视频多项；类型/尺寸/时长越界； 纯文本帖（media 为空）仍合法；kind=video 无 media
 * 仍合法（既有契约锁定，不回归）。
 */
@Transactional
class CommunityMediaApiTest extends AbstractAdminApiTest {

  private static final int CODE_OK = 0;
  private static final int CODE_INVALID = 42203;

  private String bearer(String token) {
    return "Bearer " + token;
  }

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private JsonNode create(String token, String body) throws Exception {
    return json(
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body.getBytes(StandardCharsets.UTF_8)))
            .andReturn());
  }

  private static String imageMedia(String... urls) {
    StringBuilder items = new StringBuilder();
    for (int i = 0; i < urls.length; i++) {
      if (i > 0) {
        items.append(',');
      }
      items
          .append("{\"url\":\"")
          .append(urls[i])
          .append("\",\"width\":800,\"height\":600,\"size\":102400,\"mimeType\":\"image/jpeg\"}");
    }
    return "{\"type\":\"image\",\"items\":[" + items + "]}";
  }

  @Test
  void createWithImages_persistsAndReturnsMedia() throws Exception {
    String token = registerUser("media_ok");
    JsonNode root =
        create(
            token,
            "{\"title\":\"图集\",\"body\":\"two photos\",\"kind\":\"article\",\"domain\":\"teaching\","
                + "\"media\":"
                + imageMedia("/api/v1/media/aaaa", "/api/v1/media/bbbb")
                + "}");
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    long id = root.path("data").path("id").asLong();
    assertEquals(2, root.path("data").path("media").path("items").size());

    // 详情回带（jsonb 落库 → 读取）
    JsonNode detail =
        json(
            mockMvc
                .perform(
                    get("/api/v1/community/posts/" + id).header("Authorization", bearer(token)))
                .andReturn());
    assertEquals(
        "/api/v1/media/aaaa",
        detail.path("data").path("media").path("items").get(0).path("url").asText());
  }

  @Test
  void createWithVideo_coverAndDuration() throws Exception {
    String token = registerUser("media_video");
    JsonNode root =
        create(
            token,
            "{\"body\":\"clip\",\"kind\":\"video\",\"domain\":\"overseas\",\"media\":"
                + "{\"type\":\"video\",\"items\":[{\"url\":\"/api/v1/media/cccc\",\"mimeType\":\"video/mp4\",\"size\":1048576}],"
                + "\"coverUrl\":\"/api/v1/media/dddd\",\"durationS\":12.5}}");
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    assertEquals(12.5, root.path("data").path("media").path("durationS").asDouble(), 0.001);
    assertEquals("/api/v1/media/dddd", root.path("data").path("media").path("coverUrl").asText());
  }

  @Test
  void plainTextPost_stillWorks() throws Exception {
    String token = registerUser("media_plain");
    JsonNode root =
        create(token, "{\"body\":\"no media\",\"kind\":\"article\",\"domain\":\"news\"}");
    assertEquals(CODE_OK, root.path("code").asInt());
    assertTrue(
        root.path("data").path("media").isMissingNode()
            || root.path("data").path("media").isNull());
  }

  @Test
  void videoWithoutMedia_stillLegal_existingContract() throws Exception {
    // CommunityApiTest.createPost_validation 已锁定该行为，这里显式回归（docs/48 B11）
    String token = registerUser("media_vnone");
    JsonNode root = create(token, "{\"body\":\"x\",\"kind\":\"video\",\"domain\":\"overseas\"}");
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
  }

  @Test
  void rejectsExternalUrl() throws Exception {
    String token = registerUser("media_ext");
    JsonNode root =
        create(
            token,
            "{\"body\":\"x\",\"kind\":\"article\",\"domain\":\"news\",\"media\":"
                + imageMedia("https://evil.example.com/x.jpg")
                + "}");
    assertEquals(CODE_INVALID, root.path("code").asInt(), root.toString());
  }

  @Test
  void rejectsProtocolRelativeAndInjectedUrl() throws Exception {
    String token = registerUser("media_ext2");
    for (String bad :
        new String[] {
          "//evil.example.com/x.jpg", "data:image/png;base64,AAAA", "javascript:alert(1)"
        }) {
      JsonNode root =
          create(
              token,
              "{\"body\":\"x\",\"kind\":\"article\",\"domain\":\"news\",\"media\":"
                  + imageMedia(bad)
                  + "}");
      assertEquals(CODE_INVALID, root.path("code").asInt(), bad);
    }
  }

  @Test
  void rejectsTooManyItems() throws Exception {
    String token = registerUser("media_many");
    String[] urls = new String[10];
    for (int i = 0; i < urls.length; i++) {
      urls[i] = "/api/v1/media/" + i;
    }
    JsonNode root =
        create(
            token,
            "{\"body\":\"x\",\"kind\":\"article\",\"domain\":\"news\",\"media\":"
                + imageMedia(urls)
                + "}");
    assertEquals(CODE_INVALID, root.path("code").asInt());
  }

  @Test
  void rejectsVideoWithMultipleItems() throws Exception {
    String token = registerUser("media_vmulti");
    JsonNode root =
        create(
            token,
            "{\"body\":\"x\",\"kind\":\"video\",\"domain\":\"news\",\"media\":"
                + "{\"type\":\"video\",\"items\":[{\"url\":\"/api/v1/media/a\"},{\"url\":\"/api/v1/media/b\"}]}}");
    assertEquals(CODE_INVALID, root.path("code").asInt());
  }

  @Test
  void rejectsBadShapeAndBounds() throws Exception {
    String token = registerUser("media_bad");
    String[] bads =
        new String[] {
          "{\"type\":\"audio\",\"items\":[{\"url\":\"/api/v1/media/a\"}]}", // type 非法
          "{\"type\":\"image\",\"items\":[]}", // 空 items
          "{\"type\":\"image\",\"items\":[{\"url\":\"\"}]}", // 空 url
          "{\"type\":\"image\",\"items\":[{\"url\":\"/api/v1/media/a\",\"width\":99999}]}", // 尺寸越界
          "{\"type\":\"image\",\"items\":[{\"url\":\"/api/v1/media/a\",\"size\":99999999999}]}", // 体积越界
          "{\"type\":\"video\",\"items\":[{\"url\":\"/api/v1/media/a\"}],\"durationS\":9999}", // 时长越界
          "{\"type\":\"image\",\"items\":[{\"url\":\"/api/v1/media/a\"}],\"coverUrl\":\"https://x/y\"}", // 封面外链
        };
    for (String media : bads) {
      JsonNode root =
          create(
              token,
              "{\"body\":\"x\",\"kind\":\"article\",\"domain\":\"news\",\"media\":" + media + "}");
      assertEquals(CODE_INVALID, root.path("code").asInt(), media);
    }
  }

  @Test
  void rejectsTraversalInMediaId() throws Exception {
    String token = registerUser("media_trav");
    JsonNode root =
        create(
            token,
            "{\"body\":\"x\",\"kind\":\"article\",\"domain\":\"news\",\"media\":"
                + imageMedia("/api/v1/media/../../etc/passwd")
                + "}");
    assertEquals(CODE_INVALID, root.path("code").asInt());
  }
}
