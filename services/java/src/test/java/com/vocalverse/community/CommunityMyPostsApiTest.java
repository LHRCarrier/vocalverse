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
 * 「我的发帖」feed 过滤（社区 S3 · docs/47 §5.1 · 2026-09-09 组长实测补）。
 *
 * <p>覆盖：mine=true 只回本人帖；mine=false/缺省不受影响（回归）；游标分页在作者过滤下仍单调； mine 与 domain 正交（本人帖 + 领域过滤）。
 */
@Transactional
class CommunityMyPostsApiTest extends AbstractAdminApiTest {

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

  private JsonNode feed(String token, String query) throws Exception {
    return json(
        mockMvc
            .perform(get("/api/v1/community/posts" + query).header("Authorization", bearer(token)))
            .andReturn());
  }

  @Test
  void mineTrue_onlyReturnsOwnPosts() throws Exception {
    String me = registerUser("mine_me");
    String other = registerUser("mine_other");
    createPost(me, "我的第一条", "teaching");
    createPost(other, "别人的一条", "teaching");

    JsonNode mine = feed(me, "?mine=true&limit=10");
    assertEquals(CODE_OK, mine.path("code").asInt());
    assertEquals(1, mine.path("data").path("items").size(), mine.toString());
    assertEquals("我的第一条", mine.path("data").path("items").get(0).path("body").asText());
    assertEquals(
        "mine_me", mine.path("data").path("items").get(0).path("author").path("nickname").asText());

    // 别人看自己的「我的发帖」只看得到自己那条（同一端点、不同 actor）
    JsonNode otherMine = feed(other, "?mine=true&limit=10");
    assertEquals(1, otherMine.path("data").path("items").size());
    assertEquals("别人的一条", otherMine.path("data").path("items").get(0).path("body").asText());
  }

  @Test
  void mineDefaultFalse_stillReturnsAll() throws Exception {
    String me = registerUser("mine_all");
    String other = registerUser("mine_all2");
    createPost(me, "A", "news");
    createPost(other, "B", "news");

    // 缺省 mine=false：全量（回归——新增参数不得改变既有 feed 语义）
    assertEquals(2, feed(me, "?limit=10").path("data").path("items").size());
    assertEquals(2, feed(me, "?mine=false&limit=10").path("data").path("items").size());
  }

  @Test
  void mineAndDomainAreOrthogonal() throws Exception {
    String me = registerUser("mine_domain");
    createPost(me, "教学帖", "teaching");
    createPost(me, "海外帖", "overseas");

    JsonNode teaching = feed(me, "?mine=true&domain=teaching&limit=10");
    assertEquals(1, teaching.path("data").path("items").size());
    assertEquals("教学帖", teaching.path("data").path("items").get(0).path("body").asText());

    JsonNode overseas = feed(me, "?mine=true&domain=overseas&limit=10");
    assertEquals(1, overseas.path("data").path("items").size());
    assertEquals("海外帖", overseas.path("data").path("items").get(0).path("body").asText());
  }

  @Test
  void mineWithCursor_paginatesMonotonically() throws Exception {
    String me = registerUser("mine_cursor");
    for (int i = 1; i <= 3; i++) {
      createPost(me, "p" + i, "news");
    }

    JsonNode first = feed(me, "?mine=true&limit=2");
    assertEquals(2, first.path("data").path("items").size());
    assertTrue(first.path("data").path("hasMore").asBoolean());
    String cursor = first.path("data").path("nextCursor").asText();
    assertTrue(!cursor.isBlank());

    JsonNode second = feed(me, "?mine=true&limit=2&cursor=" + cursor);
    assertEquals(1, second.path("data").path("items").size());
    assertEquals(false, second.path("data").path("hasMore").asBoolean());

    // 两页无重复（keyset 单调）
    String firstId = first.path("data").path("items").get(0).path("id").asText();
    String secondId = second.path("data").path("items").get(0).path("id").asText();
    assertTrue(!firstId.equals(secondId));
  }

  @Test
  void mineTrue_emptyForUserWithoutPosts() throws Exception {
    String fresh = registerUser("mine_empty");
    JsonNode mine = feed(fresh, "?mine=true&limit=10");
    assertEquals(0, mine.path("data").path("items").size());
    assertEquals(false, mine.path("data").path("hasMore").asBoolean());
  }
}
