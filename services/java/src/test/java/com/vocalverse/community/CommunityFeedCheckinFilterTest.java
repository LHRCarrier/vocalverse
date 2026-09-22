package com.vocalverse.community;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
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
 * 社区流打卡卡可见性（2026-09-22 组长口径：**他人打卡不进流，只能看到自己的打卡**——他人打卡卡影响浏览体验）。
 *
 * <p>规则落在 {@code PostRepository.feed} 的 viewer 谓词（{@code kind <> 'checkin' OR author_id =
 * viewerId}）：普通帖不受影响；本人打卡卡保留（打卡入口/连续天数在流里可见）；「我的发帖」({@code mine=true}) 语义不变。
 */
@Transactional
class CommunityFeedCheckinFilterTest extends AbstractAdminApiTest {

  private static final String SERVICE_TOKEN = "change-me-internal-service-token";
  private static final int CODE_OK = 0;

  private String bearer(String token) {
    return "Bearer " + token;
  }

  private JsonNode json(MvcResult result) throws Exception {
    return objectMapper.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
  }

  private long createPost(String token, String body, String domain) throws Exception {
    MvcResult r =
        mockMvc
            .perform(
                post("/api/v1/community/posts")
                    .header("Authorization", bearer(token))
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"body\":\"%s\",\"kind\":\"article\",\"domain\":\"%s\"}",
                                body, domain)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    return root.path("data").path("id").asLong();
  }

  /** 经内部端点物化一张打卡卡（与 Python 手动打卡同链路），返回 postId。 */
  private long checkin(String username, String day) throws Exception {
    Long userId = users.findByUsernameIgnoreCase(username).orElseThrow().getId();
    MvcResult r =
        mockMvc
            .perform(
                post("/internal/checkin")
                    .header("Authorization", "Bearer " + SERVICE_TOKEN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(
                        String.format(
                                "{\"userId\":%d,\"practiceDate\":\"%s\",\"sessionId\":100,\"snapshot\":"
                                    + "{\"overall\":80.0,\"pron\":82.0,\"gram\":78.0,\"fluency\":79.0,"
                                    + "\"turns\":6,\"durationS\":200,\"practiceCount\":1}}",
                                userId, day)
                            .getBytes(StandardCharsets.UTF_8)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    return root.path("data").asLong();
  }

  private JsonNode feed(String token, String query) throws Exception {
    MvcResult r =
        mockMvc
            .perform(get("/api/v1/community/posts" + query).header("Authorization", bearer(token)))
            .andReturn();
    JsonNode root = json(r);
    assertEquals(CODE_OK, root.path("code").asInt(), root.toString());
    return root.path("data").path("items");
  }

  @Test
  void feed_excludesOthersCheckin_keepsOwnAndNormalPosts() throws Exception {
    String me = registerUser("chk_me");
    String other = registerUser("chk_other");
    createPost(other, "别人的普通帖", "teaching");
    long myCheckin = checkin("chk_me", "2026-09-20");
    long otherCheckin = checkin("chk_other", "2026-09-20");

    JsonNode items = feed(me, "?limit=10");
    boolean hasOtherCheckin = false;
    boolean hasMyCheckin = false;
    boolean hasNormal = false;
    for (JsonNode it : items) {
      long id = it.path("id").asLong();
      if (id == otherCheckin) hasOtherCheckin = true;
      if (id == myCheckin) hasMyCheckin = true;
      if ("article".equals(it.path("kind").asText())) hasNormal = true;
    }
    assertEquals(2, items.size(), items.toString());
    assertFalse(hasOtherCheckin, "他人打卡卡不应出现在社区流：" + items);
    assertTrue(hasMyCheckin, "自己的打卡卡应保留：" + items);
    assertTrue(hasNormal, "普通帖不受影响：" + items);
  }

  @Test
  void feed_otherViewerSeesOwnCheckinNotMine() throws Exception {
    registerUser("chk_a");
    String b = registerUser("chk_b");
    long aCheckin = checkin("chk_a", "2026-09-22");
    long bCheckin = checkin("chk_b", "2026-09-22");

    JsonNode items = feed(b, "?limit=10");
    assertEquals(1, items.size(), items.toString());
    assertEquals(bCheckin, items.get(0).path("id").asLong());
    assertNotEquals(aCheckin, items.get(0).path("id").asLong());
  }

  @Test
  void mineTrue_stillReturnsOwnCheckin() throws Exception {
    String me = registerUser("chk_mine");
    long myCheckin = checkin("chk_mine", "2026-09-21");

    JsonNode items = feed(me, "?mine=true&limit=10");
    assertEquals(1, items.size(), items.toString());
    assertEquals(myCheckin, items.get(0).path("id").asLong());
    assertEquals("checkin", items.get(0).path("kind").asText());
  }
}
